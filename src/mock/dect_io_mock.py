#!/usr/bin/env python3
"""Clean-room userspace mock for the FRITZ!Box 7530 /dev/dect_io ABI.

This models the ABI documented in ../../notes/dect_io.md and ../../include/
dect_io_abi.h. It is a test harness, not the original driver and not a DECT
hardware implementation.
"""
from __future__ import annotations

import errno
import os
import struct
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Optional


DECT_IO_IOCTL_GET_TIME = 1
DECT_IO_IOCTL_DEBUG_PRINT = 2
DECT_IO_WRITE_TAG = 0x8052
DECT_IO_READ_TAG = 0x8053
DECT_IO_CHANNEL = 0x14
DECT_IO_MAX_WRITE = 0x3040
DECT_IO_MIN_WRITE = 7
DECT_IO_HZ = 250

POLLIN = 0x001
POLLOUT = 0x004
POLLRDNORM = 0x040
POLLWRNORM = 0x100
POLL_EMPTY = POLLOUT | POLLWRNORM                 # 0x104
POLL_DATA = POLLIN | POLLRDNORM | POLLOUT | POLLWRNORM  # 0x145

ERESTARTSYS = 512


class DectIoMock:
    """One-open, framed character-device model."""

    def __init__(self) -> None:
        self.opened = False
        self.nonblock = False
        self.queue: Deque[dict] = deque()
        self.ppos = 0
        self.tx_frames: list[bytes] = []
        self.debug_prints: list[str] = []
        self.fasync_enabled = False
        self.jiffies = 0
        self._cond = threading.Condition()
        self.transport_tx = None

    # ---- lifecycle -----------------------------------------------------
    def open(self, flags: int = os.O_RDWR) -> int:
        if self.opened:
            raise OSError(errno.EBUSY, "client already registered")
        if flags & os.O_APPEND:
            raise OSError(errno.EFAULT, "open O_APPEND not supported")
        self.opened = True
        self.nonblock = bool(flags & os.O_NONBLOCK)
        return 1

    def close(self) -> None:
        self.opened = False
        self.nonblock = False
        self.fasync_enabled = False
        with self._cond:
            self._cond.notify_all()

    def fasync(self, enabled: bool = True) -> None:
        # The original registers fasync but never imports/calls kill_fasync.
        self.fasync_enabled = enabled

    # ---- userspace -> DECT --------------------------------------------
    def write(self, frame: bytes) -> int:
        if len(frame) <= 3 or len(frame) > DECT_IO_MAX_WRITE:
            raise OSError(errno.EIO, "write length out of range")
        if len(frame) <= 6:
            raise OSError(errno.EIO, "write length too short")
        length, tag = struct.unpack_from("<HH", frame, 0)
        if length + 4 != len(frame):
            raise OSError(errno.EIO, "ill length")
        forwarded = frame[4:]
        self.tx_frames.append(forwarded)
        if self.transport_tx is not None:
            try:
                # AVM avm_dect_if_tx errors are logged but not propagated.
                self.transport_tx(forwarded)
            except Exception:
                pass
        return len(frame)

    # ---- DECT -> userspace --------------------------------------------
    def transport_rx(self, message: bytes) -> None:
        """Deliver a DECT message: u16 primitive + payload."""
        if not self.opened:
            return
        if len(message) <= 1:
            return
        length = len(message) + 1  # status byte + message
        data = struct.pack("<HHB", length, DECT_IO_READ_TAG, 0) + message
        with self._cond:
            self.queue.append({"data": data, "pos": 0})
            self._cond.notify_all()

    # ---- DECT -> user read --------------------------------------------
    def read(self, count: int, block: bool = True, timeout: Optional[float] = None) -> bytes:
        if count == 0:
            return b""
        if not self.opened:
            raise OSError(errno.EBADF, "not open")
        with self._cond:
            if not self.queue:
                if self.nonblock or not block:
                    raise BlockingIOError(errno.EAGAIN, "resource temporarily unavailable")
                if not self._cond.wait(timeout):
                    raise TimeoutError("DECT read timed out")
            entry = self.queue[0]
            data = entry["data"]
            chunk = min(count, len(data) - entry["pos"])
            out = data[entry["pos"]:entry["pos"] + chunk]
            entry["pos"] += chunk
            if entry["pos"] == len(data):
                self.queue.popleft()
                self.ppos = 0
            else:
                self.ppos += chunk
            return out

    def poll(self) -> int:
        return POLL_DATA if self.queue else POLL_EMPTY

    # ---- ioctl ---------------------------------------------------------
    def ioctl(self, cmd: int, arg=None):
        if cmd == DECT_IO_IOCTL_GET_TIME:
            return struct.pack("<II", self.jiffies, DECT_IO_HZ)
        if cmd == DECT_IO_IOCTL_DEBUG_PRINT:
            if arg is None:
                arg = b""
            if isinstance(arg, str):
                arg = arg.encode()
            buf = bytearray(256)
            n = min(len(arg), 256)
            buf[:n] = arg[:n]
            if 0 not in buf:
                buf[253:255] = b".."
                buf[255] = 0
            else:
                # Keep the first NUL, as the kernel string view does.
                end = buf.index(0)
                buf[end] = 0
            text = bytes(buf[:buf.index(0)]).decode("latin1", "replace")
            self.debug_prints.append(text)
            return 0
        raise OSError(errno.EFAULT, "invalid ioctl command")

    # ---- helpers for tests --------------------------------------------
    def make_write_frame(self, primitive: int, payload: bytes = b"",
                         tag: int = DECT_IO_WRITE_TAG,
                         channel: int = DECT_IO_CHANNEL) -> bytes:
        body = bytes([channel]) + struct.pack("<H", primitive) + payload
        return struct.pack("<HH", len(body), tag) + body

    def front_read_header(self) -> tuple[int, int, int]:
        """If a complete queued entry exists, return (length, tag, status)."""
        if not self.queue:
            raise BlockingIOError(errno.EAGAIN, "no queued entry")
        data = self.queue[0]["data"]
        return struct.unpack_from("<HHB", data, 0)
