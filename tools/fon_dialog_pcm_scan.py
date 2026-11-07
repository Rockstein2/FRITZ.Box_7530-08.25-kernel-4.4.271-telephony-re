#!/usr/bin/env python3
"""Scan the SC14448 DECT firmware images for peripheral register accesses.

Offline tool.  It parses the Intel HEX images and decodes every
`movd $imm32:l,(r1,r0)` immediate, which is how the firmware addresses its
on-chip peripherals.  The decoder is validated against a known-good snippet
from reports/fon-dialog-firmware.txt rather than assumed.

Usage:
    python3 tools/fon_dialog_pcm_scan.py firmware/dectfw_secondlevel_441.hex ...
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "mock"))
from piglet_image import parse_hex  # noqa: E402

MOVD_LO = 0x70
MOVD_HI = 0x00

WATCH = {
    0xFF4812: "GPIO",
    0xFF481E: "GPIO",
    0xFF4830: "GPIO port data",
    0xFF4836: "GPIO direction",
    0xFF4838: "GPIO",
    0xFF4856: "GPIO",
    0xFF4858: "GPIO",
    0xFF4860: "GPIO",
    0xFF4900: "UART",
    0xFF4902: "UART",
    0xFF4904: "UART",
    0xFF4906: "UART",
    0xFF4960: "UART/data",
    0xFF5400: "interrupt controller",
    0xFF5402: "interrupt controller",
    0xFF5802: "timer/platform",
    0xFF6006: "PCM/DMA",
    0xFF600E: "PCM/DMA",
    0xFF7052: "radio/analog",
    0xFF7056: "radio/analog",
}


def decode_imm(data: bytes, i: int) -> int:
    """Decode the 32-bit immediate of `movd $imm:l,(r1,r0)` at offset i.

    CR16 stores the immediate as two 16-bit words, each little-endian, and
    the stream holds the LOW word first.  Validated on 0x2582 where the
    bytes `ff 00 06 60` must decode to 0xff6006.
    """
    b = data[i + 2:i + 6]
    return (b[1] << 24) | (b[0] << 16) | (b[3] << 8) | b[2]


def scan(path: str) -> None:
    mem = parse_hex(path)
    data = bytes(mem.get(a, 0xff) for a in range(0, max(mem) + 1))
    print(f"=== {path} ({len(data)} bytes of address space) ===")
    hits = []
    for i in range(len(data) - 5):
        if data[i] != MOVD_LO or data[i + 1] != MOVD_HI:
            continue
        val = decode_imm(data, i)
        hits.append((i, val))
    print(f"  movd immediates: {len(hits)}")
    grouped: dict[int, list[int]] = {}
    for off, val in hits:
        grouped.setdefault(val, []).append(off)
    for val in sorted(grouped):
        offs = grouped[val]
        label = WATCH.get(val, "")
        mark = " *" if label else ""
        print(f"  {val:#010x} x{len(offs):<3} {label}{mark}")
        print("        at " + ", ".join(f"{o:#06x}" for o in offs[:8]))


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    for path in argv[1:]:
        scan(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
