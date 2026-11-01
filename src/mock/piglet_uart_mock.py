#!/usr/bin/env python3
"""Clean-room model of the documented Piglet DECT UART upload.

This is a protocol test model, not a bit-accurate emulator of the DECT chip.
It follows the state transitions recorded in notes/piglet.md:

  reset -> STX -> SOH + length -> ACK -> data -> checksum -> ACK/NACK

HELLO mode is also modelled. The model deliberately keeps the image checksum
out of the host data stream; the chip returns it for comparison.
"""
from __future__ import annotations

from dataclasses import dataclass, field


STX = 0x02
SOH = 0x01
ACK = 0x06
NACK = 0x15
HELLO = b"HELLO DCX81"
HELLO_REPLY = bytes([0x11, 0xBA, 0x5E, 0xBA])


class UartProtocolError(RuntimeError):
    pass


def xor_checksum(data: bytes) -> int:
    c = 0
    for b in data:
        c ^= b
    return c


class DectChipUartModel:
    """State machine for the DECT side of the loader protocol."""

    def __init__(self, header_len: int = 2, fast: bool = False):
        if header_len not in (2, 4):
            raise ValueError("header_len must be 2 or 4")
        self.header_len = header_len
        self.fast = fast
        self.state = "idle"
        self.out = bytearray()
        self._header = bytearray()
        self._data = bytearray()
        self._length = 0
        self.result = None

    def reset(self) -> bytes:
        self.state = "hello" if self.fast else "stx"
        self.out.clear()
        self._header.clear()
        self._data.clear()
        self._length = 0
        self.result = None
        if not self.fast:
            self.out.append(STX)
        return bytes(self.out)

    def _emit(self, data: bytes) -> None:
        self.out.extend(data)

    def feed(self, data: bytes) -> bytes:
        """Consume host bytes, return newly produced chip bytes."""
        self.out.clear()
        for b in data:
            self._byte(b)
        return bytes(self.out)

    def _byte(self, b: int) -> None:
        if self.state == "hello":
            self._header.append(b)
            if len(self._header) < len(HELLO):
                return
            if bytes(self._header) != HELLO:
                self.state = "error"
                raise UartProtocolError("HELLO mismatch")
            self._emit(HELLO)
            self._emit(HELLO_REPLY)
            self._header.clear()
            self.state = "length"
            return

        if self.state == "stx":
            if b != SOH:
                self.state = "error"
                raise UartProtocolError("expected SOH")
            self._header.clear()
            self.state = "length"
            return

        if self.state == "length":
            self._header.append(b)
            if len(self._header) < self.header_len:
                return
            self._length = int.from_bytes(self._header, "big")
            if self._length <= self.header_len:
                self.state = "error"
                raise UartProtocolError("invalid image length")
            self._data.clear()
            self._emit(bytes([ACK]))
            self.state = "data"
            return

        if self.state == "data":
            self._data.append(b)
            # The last image byte is the checksum, supplied by the chip.
            if len(self._data) == self._length:
                self._emit(bytes([xor_checksum(self._data)]))
                self.state = "checksum_ack"
            return

        if self.state == "checksum_ack":
            if b == ACK:
                self.state = "done"
                self.result = "ok"
            elif b == NACK:
                self.state = "error"
                self.result = "nack"
            else:
                self.state = "error"
                raise UartProtocolError("expected ACK/NACK")
            return

        if self.state in ("idle", "done", "error"):
            raise UartProtocolError(f"unexpected byte 0x{b:02x} in {self.state}")

    @property
    def complete(self) -> bool:
        return self.state == "done"


@dataclass
class UploadResult:
    ok: bool
    checksum: int
    expected_checksum: int
    chip_state: str
    response: bytes = field(default=b"")


class PigletUploadHostModel:
    """Host-side model for the normal (STX) path and HELLO path."""

    def __init__(self, fast: bool = False):
        self.fast = fast

    def upload(self, image: bytes, header_len: int = 2) -> UploadResult:
        if len(image) < header_len + 2:
            raise ValueError("image too short")
        chip = DectChipUartModel(header_len=header_len, fast=self.fast)
        response = bytearray()
        response += chip.reset()

        if self.fast:
            response += chip.feed(HELLO)
            # The modelled chip returns HELLO + the four observed reply bytes.
            if not response.endswith(HELLO + HELLO_REPLY):
                raise UartProtocolError("HELLO response mismatch")
            response += chip.feed(image[:header_len])
        else:
            if not response.startswith(bytes([STX])):
                raise UartProtocolError("missing STX")
            response += chip.feed(bytes([SOH]) + image[:header_len])

        if not response.endswith(bytes([ACK])):
            raise UartProtocolError("missing ACK after length")
        for byte in image[header_len:-1]:
            response += chip.feed(bytes([byte]))
        expected = image[-1]
        if len(response) < 1:
            raise UartProtocolError("missing checksum")
        checksum = response[-1]
        if checksum == expected:
            response += chip.feed(bytes([ACK]))
            return UploadResult(True, checksum, expected, chip.state, bytes(response))
        response += chip.feed(bytes([NACK]))
        return UploadResult(False, checksum, expected, chip.state, bytes(response))
