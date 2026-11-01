#!/usr/bin/env python3
"""Clean-room model of the pcmlink DECT-control/audio-slot boundary.

This models only the interface that ``avm_dect.ko`` uses. It is not a TDM or
DMA emulator and it does not model the QCA/IPQ4019 hardware path.

Facts encoded here come from ``notes/pcmlink.md`` and
``include/pcmlink_boundary.h``:

* DECT control registration returns a handle and a slot count/mask.
* ``pcmlink_ul_config_dectcontrol(handle, 0x1000, 0x1000)`` is the observed
  call from ``avm_dect_init``.
* Audio slots use a link mask with at most seven audio channels; link-mask
  bit 0 is the control channel and is not accepted for audio.
* ``pcmlink_ul_activity(0, 0x100000, 1)`` is the observed PCM/DECT activity
  notification.
* ``pcmlink_ul_openslots``/``closeslots`` bracket a UOTA audio slot.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

PCMLINK_MAX_AUDIO_CHANNELS = 7
PCMLINK_DECTCTRL_DEFAULT_SLOT_COUNT = 0x1000
PCMLINK_DECTCTRL_DEFAULT_START = 0x1000
PCMLINK_DECTCTRL_DEFAULT_COUNT = 0x1000
PCMLINK_ACTIVITY_MASK = 0x100000
PCMLINK_AUDIO_LINKMASK = 0xFE  # bits 1..7


class PcmlinkError(RuntimeError):
    """The caller violated the observed pcmlink state machine."""


class PcmlinkInvalidArgument(ValueError):
    """A slot/link-mask argument is outside the observed limits."""


@dataclass
class DectControl:
    handle: int
    callback: Callable[[bytes], None]
    slot_count: int
    start: int = 0
    count: int = 0
    configured: bool = False
    released: bool = False
    notifications: int = 0


@dataclass
class AudioSlot:
    handle: int
    linkmask: int
    callback: Callable[[bytes], None]
    mode: int
    closed: bool = False
    notifications: int = 0


@dataclass
class PcmlinkMock:
    """Minimal userspace stand-in for the exported pcmlink boundary."""

    started: bool = False
    dect_control: Optional[DectControl] = None
    audio_slots: dict[int, AudioSlot] = field(default_factory=dict)
    activity_calls: list[tuple[int, int, int]] = field(default_factory=list)
    status_calls: list[tuple[int, int, int]] = field(default_factory=list)
    _next_handle: int = 1

    # ---- lifecycle -----------------------------------------------------
    def start_isdn(self) -> None:
        """Mark the ISDN/pcmlink upper manager as present."""
        self.started = True

    def stop_isdn(self) -> None:
        self.started = False
        self.dect_control = None
        for slot in self.audio_slots.values():
            slot.closed = True
        self.audio_slots.clear()

    # ---- DECT control channel -----------------------------------------
    def register_dectcontrol(
        self,
        callback: Callable[[bytes], None],
        slot_count: int = PCMLINK_DECTCTRL_DEFAULT_SLOT_COUNT,
    ) -> tuple[int, int]:
        """Model pcmlink_ul_register_dectcontrol().

        Returns ``(handle, slot_count)``. The original function also probes
        control slots 0xc..0xf through pcmlink_ul_status(); those probes are
        recorded in ``status_calls``.
        """
        if not self.started:
            raise PcmlinkError("ISDN driver is not started")
        if self.dect_control is not None and not self.dect_control.released:
            raise PcmlinkError("DECT control already registered")
        if slot_count <= 0:
            raise PcmlinkInvalidArgument("slot_count must be positive")
        handle = self._alloc_handle()
        self.dect_control = DectControl(handle=handle, callback=callback,
                                        slot_count=slot_count)
        # Observed in pcmlink_ul_register_dectcontrol: query slots 0xc..0xf.
        for slot in range(0xC, 0x10):
            self.status_calls.append((5, slot, 0))
        return handle, slot_count

    def config_dectcontrol(
        self,
        handle: int,
        start: int = PCMLINK_DECTCTRL_DEFAULT_START,
        count: int = PCMLINK_DECTCTRL_DEFAULT_COUNT,
    ) -> None:
        """Model pcmlink_ul_config_dectcontrol()."""
        ctl = self._require_control(handle)
        if ctl.configured:
            raise PcmlinkError("DECT control already configured")
        ctl.start = start
        ctl.count = count
        ctl.configured = True

    def release_dectcontrol(self, handle: int) -> None:
        ctl = self._require_control(handle)
        ctl.released = True
        ctl.configured = False
        self.dect_control = None

    def notify_dect_control(self, data: bytes) -> bool:
        """Deliver one control-channel buffer to the registered callback."""
        ctl = self.dect_control
        if ctl is None or ctl.released or not ctl.configured:
            return False
        ctl.notifications += 1
        ctl.callback(bytes(data))
        return True

    # ---- audio slots ---------------------------------------------------
    def openslots(
        self,
        linkmask: int,
        callback: Callable[[bytes], None],
        mode: int = 1,
    ) -> int:
        """Model pcmlink_ul_openslots().

        The observed implementation accepts 16-bit audio slots only, rejects
        link-mask bit 0, and allows at most seven audio channels.
        """
        if not self.started:
            raise PcmlinkError("ISDN driver is not started")
        if linkmask & ~PCMLINK_AUDIO_LINKMASK:
            raise PcmlinkInvalidArgument(
                f"linkmask 0x{linkmask:x} uses a non-audio channel")
        bits = linkmask.bit_count()
        if bits == 0:
            raise PcmlinkInvalidArgument("linkmask selects no audio channel")
        if bits > PCMLINK_MAX_AUDIO_CHANNELS:
            raise PcmlinkInvalidArgument("too many audio channels")
        handle = self._alloc_handle()
        self.audio_slots[handle] = AudioSlot(handle=handle,
                                             linkmask=linkmask,
                                             callback=callback,
                                             mode=mode)
        return handle

    def closeslots(self, handle: int) -> None:
        slot = self.audio_slots.get(handle)
        if slot is None or slot.closed:
            raise PcmlinkError(f"unknown or closed audio slot {handle}")
        slot.closed = True
        del self.audio_slots[handle]

    def notify_slot_data(self, handle: int, data: bytes) -> bool:
        slot = self.audio_slots.get(handle)
        if slot is None or slot.closed:
            return False
        slot.notifications += 1
        slot.callback(bytes(data))
        return True

    # ---- activity/status ----------------------------------------------
    def activity(self, link: int = 0, mask: int = PCMLINK_ACTIVITY_MASK,
                 on: int = 1) -> None:
        self.activity_calls.append((link, mask, on))

    def status(self, link: int, slot: int, value: int) -> None:
        self.status_calls.append((link, slot, value))

    # ---- helpers -------------------------------------------------------
    def _alloc_handle(self) -> int:
        handle = self._next_handle
        self._next_handle += 1
        return handle

    def _require_control(self, handle: int) -> DectControl:
        ctl = self.dect_control
        if ctl is None or ctl.released:
            raise PcmlinkError("DECT control is not registered")
        if ctl.handle != handle:
            raise PcmlinkError(f"bad DECT control handle {handle}")
        return ctl
