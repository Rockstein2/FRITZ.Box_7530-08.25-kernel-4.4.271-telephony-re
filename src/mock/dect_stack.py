#!/usr/bin/env python3
"""Wired userspace model of the dect_io -> avm_dect -> pcmlink chain."""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from avm_dect_mock import AvmDectMock
from dect_io_mock import DectIoMock
from pcmlink_mock import PcmlinkMock


@dataclass
class DectStackMock:
    """A complete, userspace-only model of the observed kernel boundary."""

    io: DectIoMock = field(default_factory=DectIoMock)
    pcmlink: PcmlinkMock = field(default_factory=PcmlinkMock)
    dect: AvmDectMock = field(init=False)
    started: bool = False

    def __post_init__(self) -> None:
        self.dect = AvmDectMock(self.pcmlink)
        # dect_io.ko installs dect_uicp_from_dect through avm_dect_if_init().
        self.io.transport_tx = self.dect.if_tx
        self.dect.if_init(self.io.transport_rx)

    def start(self, open_io: bool = True) -> None:
        if self.started:
            raise RuntimeError("DECT stack already started")
        self.dect.init(host_handler=self.io.transport_rx)
        if open_io:
            self.io.open()
        self.started = True

    def stop(self) -> None:
        self.dect.cleanup()
        self.io.close()
        self.pcmlink.stop_isdn()
        self.started = False

    # ---- convenience paths --------------------------------------------
    def userspace_write(self, primitive: int, payload: bytes = b"",
                        channel: int = 0x14) -> int:
        """Write one framed userspace message to /dev/dect_io."""
        return self.io.write(self.io.make_write_frame(primitive, payload,
                                                      channel=channel))

    def userspace_read(self, count: int = 4) -> bytes:
        return self.io.read(count)

    def dect_to_userspace(self, primitive: int, payload: bytes = b"") -> None:
        """Inject a DECT-to-host message as avm_dect would deliver it."""
        self.dect.uicp_send_mail_to_host(struct.pack("<H", primitive) + payload)
