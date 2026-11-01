#!/usr/bin/env python3
"""Clean-room model of the ``avm_dect`` transport/control boundary.

The model follows ``notes/avm_dect.md``, ``notes/avm_dect_boundary.md`` and
``include/avm_dect_boundary.h``. It is deliberately small:

* ``avm_dect_if_init/deinit/tx`` and the DECT-to-host callback;
* the special primitive ``0x2fba`` path;
* the 0x1000-byte control buffer and ``RxTxCallback``;
* PCM mail length/checksum handling and the observed activity notification;
* UOTA audio-slot open/close through the pcmlink mock.

It does not model the full DECT protocol, the PCM state machine, or the
QCA TDM/DMA path. Those remain hardware/runtime work.
"""
from __future__ import annotations

import errno
import struct
from dataclasses import dataclass, field
from typing import Callable, Optional

AVM_DECT_MEMPOOL_SIZE = 0x40000
AVM_DECT_CONTROL_BUFFER_SIZE = 0x1000
AVM_DECT_UOTA_BUFFER_SIZE = 0x1450
AVM_DECT_PCM_MAIL_MAX = 0xFC
AVM_DECT_PCM_MAIL_MIN = 8
AVM_DECT_FRAME_SYNC = 0xAA
AVM_DECT_PRIMITIVE_SPECIAL = 0x2FBA
AVM_DECT_TX_CHANNEL = 0x14
AVM_DECT_MAX_AUDIO_SLOTS = 7
AVM_DECT_ACTIVITY_MASK = 0x100000

# Task/route bytes observed around pcm_Task().
PCM_ROUTE_PCM = 0x22
PCM_ROUTES = frozenset({0x02, 0x15, 0x22, 0x23})
PCM_SOURCE_TASKS = frozenset({0x22, 0x23, 0x25})


class AvmDectError(RuntimeError):
    pass


class PcmMailError(ValueError):
    pass


@dataclass
class PcmMail:
    """Observed PCM mail frame.

    Layout recovered from AllocateMailPacket2(), pcm_Task() and
    pcmdrv_enqueue_tx():

        +0x00  u16le payload_length
        +0x02  u8    source task
        +0x03  u8    route/task selector (name is not proven)
        +0x04  payload; first u16le is the message primitive

    ``total = payload_length + 4``. The original pcmdrv_enqueue_tx() rejects
    a total length above 0xFC.
    """

    source_task: int
    route: int
    payload: bytes

    @property
    def length(self) -> int:
        return len(self.payload)

    @property
    def total_length(self) -> int:
        return self.length + 4

    @property
    def primitive(self) -> Optional[int]:
        if len(self.payload) < 2:
            return None
        return struct.unpack_from("<H", self.payload, 0)[0]

    def to_bytes(self) -> bytes:
        if not 0 <= self.source_task <= 0xFF:
            raise PcmMailError("source task does not fit in one byte")
        if not 0 <= self.route <= 0xFF:
            raise PcmMailError("route does not fit in one byte")
        return struct.pack("<HBB", self.length, self.source_task,
                           self.route) + self.payload

    @classmethod
    def from_bytes(cls, frame: bytes) -> "PcmMail":
        if len(frame) < 4:
            raise PcmMailError("mail shorter than the 4-byte header")
        length, source_task, route = struct.unpack_from("<HBB", frame, 0)
        if len(frame) != length + 4:
            raise PcmMailError(
                f"mail length {length} does not match frame size {len(frame)}")
        return cls(source_task=source_task, route=route, payload=frame[4:])


@dataclass
class PcmMailRouter:
    """Observed PCM task/RX dispatch, without the byte-stream parser."""

    owner: "AvmDectMock"
    tx_queue: list[PcmMail] = field(default_factory=list)
    rx_forwarded: list[tuple[str, PcmMail]] = field(default_factory=list)
    rejected: list[tuple[str, str]] = field(default_factory=list)
    remote_status_enabled: bool = False

    # ---- pcm_Task ------------------------------------------------------
    def pcm_task(self, frame: bytes) -> bool:
        try:
            mail = PcmMail.from_bytes(frame)
        except PcmMailError as exc:
            self.rejected.append(("length", str(exc)))
            return False
        if mail.total_length > AVM_DECT_PCM_MAIL_MAX:
            self.rejected.append(("length", "mail exceeds 0xfc"))
            return False
        if mail.route not in PCM_ROUTES:
            self.rejected.append(("route", f"route 0x{mail.route:02x}"))
            return False
        if mail.source_task not in PCM_SOURCE_TASKS:
            self.rejected.append(
                ("task", f"source task 0x{mail.source_task:02x}"))
            return False
        # Observed branch: a 0xfff1 remote-status mail is dropped while the
        # corresponding state flag is clear.
        if mail.primitive == 0xFFF1 and not self.remote_status_enabled:
            self.rejected.append(("primitive", "remote status disabled"))
            return False
        if self.owner.pcmlink is not None:
            self.owner.pcmlink.activity(0, AVM_DECT_ACTIVITY_MASK, 1)
        self.tx_queue.append(mail)
        return True

    # ---- pcmdrv_check_rx_mails ----------------------------------------
    def check_rx(self, frame: bytes) -> str:
        try:
            mail = PcmMail.from_bytes(frame)
        except PcmMailError as exc:
            self.rejected.append(("rx", str(exc)))
            return "drop"
        if mail.total_length < AVM_DECT_PCM_MAIL_MIN:
            self.rejected.append(("rx", "mail shorter than 8 bytes"))
            return "drop"
        primitive = mail.primitive
        if primitive == 0xF625:
            kind = "pcm_status"
        elif primitive == 0xFFF1:
            kind = "remote_status"
        elif primitive == 0x242:
            kind = "test_cfm"
        else:
            kind = "raw"
        self.rx_forwarded.append((kind, mail))
        return kind

    # ---- pcmdrv_checksum_valid ---------------------------------------
    @staticmethod
    def checksum_valid(frame: bytes) -> bool:
        """Reproduce pcmdrv_checksum_valid().

        length  = u16le(frame[0:2])
        sum     = sum(frame[0 : length+4]) & 0xffff
        stored  = u16le(frame[length+4 : length+6])
        """
        if len(frame) < 6:
            return False
        length = struct.unpack_from("<H", frame, 0)[0]
        end = length + 4
        if len(frame) < end + 2:
            return False
        total = sum(frame[:end]) & 0xFFFF
        stored = struct.unpack_from("<H", frame, end)[0]
        return total == stored

    def rx_stream(self, data: bytes) -> list[bytes]:
        """Record raw bytes from pcm_rx_tx_handler().

        The exact 0xAA state machine is not reproduced; only the marker and
        the raw payload are observable enough to model safely.
        """
        self.owner.control_streams.append(bytes(data))
        return [bytes(data)] if AVM_DECT_FRAME_SYNC in data else []


class AvmDectMock:
    """Minimal model of the avm_dect.ko boundary."""

    def __init__(self, pcmlink=None) -> None:
        self.pcmlink = pcmlink
        self.handler: Optional[Callable[[bytes], None]] = None
        self.audio_handler: Optional[Callable[[bytes], None]] = None
        self.control_active = False
        self.control_buffer = bytearray(AVM_DECT_CONTROL_BUFFER_SIZE)
        self.control_truncated = False
        self.control_streams: list[bytes] = []
        self.upper_tx: list[tuple[int, int, bytes]] = []
        self.special_allocations: list[bytes] = []
        self.freed_messages: list[bytes] = []
        self.mempool_used = 0
        self.thread_wakeups = 0
        self.initialized = False
        self.dect_handle: Optional[int] = None
        self.dect_slot_count = 0
        self.uota_slots: dict[int, int] = {}
        self.pcm = PcmMailRouter(self)

    # ---- module init/cleanup ------------------------------------------
    def init(self, host_handler: Optional[Callable[[bytes], None]] = None,
             pcmlink_started: bool = True) -> None:
        if self.initialized:
            raise AvmDectError("already initialized")
        if host_handler is not None:
            self.handler = host_handler
        if self.pcmlink is not None:
            if pcmlink_started:
                self.pcmlink.start_isdn()
            handle, slots = self.pcmlink.register_dectcontrol(self.rxtx_callback)
            self.dect_handle = handle
            self.dect_slot_count = slots
            self.pcmlink.config_dectcontrol(handle)
        self.control_active = True
        self.initialized = True

    def cleanup(self) -> None:
        self.control_active = False
        if self.pcmlink is not None and self.dect_handle is not None:
            self.pcmlink.release_dectcontrol(self.dect_handle)
        self.dect_handle = None
        self.initialized = False
        self.if_deinit()
        self.if_audio_deinit()

    # ---- exported avm_dect_if_* ---------------------------------------
    def if_init(self, handler: Callable[[bytes], None]) -> None:
        self.handler = handler

    def if_deinit(self) -> None:
        self.handler = None

    def if_audio_init(self, handler: Callable[[bytes], None]) -> None:
        self.audio_handler = handler

    def if_audio_deinit(self) -> None:
        self.audio_handler = None

    def if_tx(self, frame: bytes) -> int:
        """Model avm_dect_if_tx().

        Input is ``[channel][u16le primitive][payload...]``. The original
        returns -EIO if no dect_io callback is registered.
        """
        if self.handler is None:
            raise OSError(errno.EIO, "avm_dect handler is not registered")
        if len(frame) < 3:
            raise ValueError("avm_dect frame shorter than channel+primitive")
        channel = frame[0]
        primitive = struct.unpack_from("<H", frame, 1)[0]
        payload = frame[3:]
        if primitive == AVM_DECT_PRIMITIVE_SPECIAL:
            self._mempool_alloc(len(payload), special=True)
            self.special_allocations.append(payload)
        self._mempool_alloc(len(frame) - 1)
        self.upper_tx.append((channel, primitive, payload))
        self.thread_wakeups += 1
        return 0

    # ---- DECT -> host --------------------------------------------------
    def uicp_send_mail_to_host(self, message: bytes) -> None:
        """Model UicpSendMailToHost(): callback plus mempool free."""
        if self.handler is not None:
            self.handler(message)
        self.freed_messages.append(bytes(message))
        self._mempool_free(len(message) + 2)

    def rxtx_callback(self, data: bytes) -> bool:
        """Model RxTxCallback() from pcmlink's DECT-control path."""
        if not self.control_active:
            return False
        n = min(len(data), len(self.control_buffer))
        self.control_buffer[:n] = data[:n]
        if n < len(data):
            self.control_truncated = True
        if self.pcm is not None:
            self.pcm.rx_stream(data)
        return True

    # ---- PCM/UOTA helpers ---------------------------------------------
    def pcm_task(self, frame: bytes) -> bool:
        return self.pcm.pcm_task(frame)

    def open_uota_slot(self, slot: int,
                       callback: Callable[[bytes], None]) -> int:
        if not 1 <= slot <= AVM_DECT_MAX_AUDIO_SLOTS:
            raise AvmDectError(f"audio slot {slot} outside 1..7")
        if self.pcmlink is None:
            raise AvmDectError("pcmlink is not attached")
        handle = self.pcmlink.openslots(1 << slot, callback, 1)
        self.uota_slots[slot] = handle
        return handle

    def close_uota_slot(self, slot: int) -> None:
        handle = self.uota_slots.pop(slot, None)
        if handle is None:
            raise AvmDectError(f"audio slot {slot} is not open")
        if self.pcmlink is not None:
            self.pcmlink.closeslots(handle)

    # ---- memory accounting --------------------------------------------
    def _mempool_alloc(self, size: int, special: bool = False) -> None:
        if self.mempool_used + size > AVM_DECT_MEMPOOL_SIZE:
            raise OSError(errno.ENOMEM, "gDectMemPool exhausted")
        self.mempool_used += size

    def _mempool_free(self, size: int) -> None:
        self.mempool_used = max(0, self.mempool_used - size)
