#!/usr/bin/env python3
"""Intel HEX -> Piglet firmware image builder (documented format)."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable


class HexError(ValueError):
    pass


def parse_hex(path: str | Path) -> dict[int, int]:
    mem: dict[int, int] = {}
    upper = 0
    for lineno, line in enumerate(Path(path).read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        if not line.startswith(":"):
            raise HexError(f"line {lineno}: not an Intel HEX record")
        raw = bytes.fromhex(line[1:])
        if len(raw) < 5:
            raise HexError(f"line {lineno}: short record")
        n, addr, typ = raw[0], (raw[1] << 8) | raw[2], raw[3]
        data, check = raw[4:4 + n], raw[4 + n]
        if (sum(raw[:-1]) + check) & 0xFF:
            raise HexError(f"line {lineno}: bad checksum")
        if typ == 0:
            base = upper + addr
            for i, b in enumerate(data):
                if base + i in mem:
                    raise HexError(f"line {lineno}: duplicate address")
                mem[base + i] = b
        elif typ == 1:
            break
        elif typ == 2:
            upper = ((data[0] << 8) | data[1]) << 4
        elif typ == 4:
            upper = ((data[0] << 8) | data[1]) << 16
        else:
            raise HexError(f"line {lineno}: unsupported record type {typ}")
    if not mem:
        raise HexError("empty image")
    return mem


def contiguous_blocks(mem: dict[int, int]) -> list[tuple[int, bytes]]:
    addrs = sorted(mem)
    blocks: list[tuple[int, bytes]] = []
    start = prev = addrs[0]
    buf = bytearray([mem[start]])
    for a in addrs[1:]:
        if a == prev + 1:
            buf.append(mem[a])
        else:
            blocks.append((start, bytes(buf)))
            start = a
            buf = bytearray([mem[a]])
        prev = a
    blocks.append((start, bytes(buf)))
    return blocks


def build_image(hex_path: str | Path, mode: int) -> tuple[bytes, dict]:
    """mode 0 = first-level u16 header, mode 1 = second-level u32 header."""
    if mode not in (0, 1):
        raise ValueError("mode must be 0 or 1")
    mem = parse_hex(hex_path)
    blocks = contiguous_blocks(mem)
    payload = b"".join(
        int(addr).to_bytes(4, "big") + int(len(data)).to_bytes(4, "big") + data
        for addr, data in blocks
    )
    hdrlen = 2 if mode == 0 else 4
    header = len(payload).to_bytes(hdrlen, "big")
    checksum = 0
    for b in payload:
        checksum ^= b
    image = header + payload + bytes([checksum])
    return image, {
        "blocks": blocks,
        "payload_len": len(payload),
        "header_len": hdrlen,
        "checksum": checksum,
        "image_len": len(image),
    }
