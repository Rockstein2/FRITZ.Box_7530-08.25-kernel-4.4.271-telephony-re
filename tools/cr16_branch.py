#!/usr/bin/env python3
"""CR16 branch-target decoder, validated against binutils and firmware.

The rules come from `binutils-2.44/opcodes/cr16-dis.c`:

  allWords = (word0 << 32) | (word1 << 16) | word2
  makelongparameter(allWords, start, end) = EXTRACT(allWords, 48-end, end-start)
  for a 2-word `bal` the field is 24 bits from bit 8:
      p = EXTRACT(allWords, 16, 24)
  the sign is in bit 0, not the top bit:
      if p & 1: p = (~p + 1) & 0xFFFFFF      (sign flag)
  the printed target is
      target = addr + ((-p) & 0xFFFFFE)   with the sign flag
      target = addr + p                   otherwise
  masked to 24 bits, where `addr` is the address of the instruction itself.

Empirical confirmation that objdump prints the **absolute target** (not a
relative displacement):

| Instruction | Printed by objdump | Target found |
|---|---|---|
| `0x0AF0` `ff c0 a7 f9` | `*-0x496` | `0x496`, which begins with `push $0x7,r7,RA` — a function prologue |
| `0x257E` `ff c0 7b ff` | `*-0x24f8` | `0x24F8`, the start of the enclosing block |
| `0x2570` `00 c0 1c 17` | `*+0x3c8c` | `0x3C8C`, inside the same run |

A prologue cannot sit in the middle of a function, so `0x496` is a real
entry, which only works if the printed value is the target and not
`addr - value`.

This module exposes the arithmetic only.
"""
from __future__ import annotations

ADDR_MASK = 0xFFFFFF


def _extract48(all_words: int, start: int, end: int) -> int:
    shift = 48 - end
    width = end - start
    return (all_words >> shift) & ((1 << width) - 1)


def allwords(word0: int, word1: int, word2: int = 0) -> int:
    return (word0 << 32) | (word1 << 16) | word2


def disp24(words: tuple[int, ...]) -> int:
    """Raw displacement field of a CR16 branch."""
    if len(words) == 2:
        aw = allwords(words[0], words[1])
        return _extract48(aw, 8, 32)
    if len(words) == 3:
        aw = allwords(words[0], words[1], words[2])
        p = _extract48(aw, 16, 40)
        return (((p >> 16) & 0xF) << 20) | (((p >> 24) & 0xF) << 16) | (p & 0xFFFF)
    raise ValueError("unsupported instruction length")


def branch_target(addr: int, words: tuple[int, ...]) -> tuple[int, bool]:
    """Return (target, sign_flag); `addr` is the instruction's own address."""
    p = disp24(words)
    if p & 1:
        c = (~p + 1) & ADDR_MASK
        return (addr + ((-c) & 0xFFFFFE)) & ADDR_MASK, True
    return (addr + p) & ADDR_MASK, False


def target_from_objdump(printed: int) -> int:
    """objdump prints the absolute target; the sign prefix is cosmetic."""
    return abs(printed)


def is_in_runs(target: int, runs: list[tuple[int, int]]) -> bool:
    return any(lo <= target <= hi for lo, hi in runs)


def describe(addr: int, words: tuple[int, ...],
             runs: list[tuple[int, int]]) -> str:
    target, sign = branch_target(addr, words)
    inside = "inside" if is_in_runs(target, runs) else "OUTSIDE"
    return (f"{addr:#08x}: raw={disp24(words):#08x} sign={int(sign)} "
            f"-> {target:#08x} ({inside} a loaded run)")
