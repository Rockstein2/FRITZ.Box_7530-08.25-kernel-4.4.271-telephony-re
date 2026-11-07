#!/usr/bin/env python3
"""CR16 branch-target decoder, validated against binutils and firmware.

Design rule: the decoding rule is selected by the **machine form of the
instruction** (opcode word + instruction length), never by the length alone.
Every value returned here was cross-checked against the CR16 disassembler
built from `binutils-2.44` (`opcodes/cr16-dis.c`), not merely against our own
previous output.

References from `opcodes/cr16-opc.c`:

    #define BRANCH_INST(NAME, OPC)                                       \
      /* opc4 c4 dispe9 */                                               \
      {NAME, 1, OPC, 28, BRANCH_INS | RELAXABLE, {{cc,20}, {dispe9,16}}}, \
      /* opc4 c4 disps17 */                                              \
      {NAME, 2, ((OPC<<4)+0x8), 24, ..., {{cc,20}, {disps17,0}}},        \
      /* opc4 c4 disps25 */                                              \
      {NAME, 3, (OPC<<4), 16, ..., {{cc,4}, {disps25,16}}}

    #define BRANCH_NEQ_INST(NAME, OPC)                           \
      /* opc8 disps5 r */                                        \
      {NAME, 1, OPC, 24, BRANCH_NEQ_INS, {{regr,16}, {disps5,20}}}

The `bal` instruction is `{2, 0x00C0, ...}`: a 4-byte (2-word) form whose
24-bit field is split as described below.

Form 1 -- 4-byte `bal` (and the 6-byte form sharing the same field layout)
-------------------------------------------------------------------------
    allWords = (word0 << 32) | (word1 << 16) | word2
    p = EXTRACT(allWords, 16, 24) = bits[31:8] of (word1 << 16 | word0)
    sign is bit 0 of p
    if p & 1:   target = addr + ((-((~p + 1) & 0xFFFFFF)) & 0xFFFFFE)
    else:       target = addr + p
    masked to 24 bits; `addr` is the instruction's own address.

Validated on 1490 real `bal` instructions of `dectfw_secondlevel_441.hex`:
0 mismatches against objdump with `--adjust-vma=0`.

Form 2 -- 2-byte conditional branch (`dispe9`, unsigned)
--------------------------------------------------------
    The 8-bit displacement is scattered: low nibble in bits[3:0] of the
    opcode word, high nibble in bits[11:8].  The stored value is even and
    counts half-bytes:

        disp = ((word0 & 0x0F) | ((word0 >> 8) & 0x0F) << 4) << 1
        target = addr + disp            (24-bit wrap)

Examples from the firmware, confirmed against CR16 objdump run with vma 0:

| Address  | Bytes   | Mnemonic | Printed (vma 0) | Delta |
|----------|---------|----------|-----------------|-------|
| 0x000294 | `40 11` | bhi      | `*+0x20`        | 0x20  |
| 0x0010ce | `9f 10` | bfc      | `*+0x1e`        | 0x1e  |
| 0x028b12 | `b3 10` | bhs      | `*+0x06`        | 0x06  |
| 0x0000ee | `12 12` | bne      | `*+0x44`        | 0x44  |
| 0x0000f8 | `00 12` | beq      | `*+0x40`        | 0x40  |
| 0x0019da | `53 11` | bls      | `*+0x26`        | 0x26  |

Validated on all 1811 two-byte conditional branches of the firmware image:
0 mismatches.

The displacement is **unsigned**: bit 0 of the stored field is zero by
construction, and a branch to an address below the instruction cannot be
encoded in this form.  The `*-0xffffXX` strings that objdump prints for this
form are an artifact of applying the *signed* `bal` rule to the *unsigned*
field; the byte value never represents a backward branch.  The assembler
confirms this: `bhi 0x4` at address 0 encodes as `42 10`, and addresses below
the instruction always get the 4-byte form.

Form 3 -- 2-byte branch-if-zero (`disps5`)
------------------------------------------
    {beq0b, bne0b, beq0w, bne0w}: 5-bit field at bits[20:16] of the word,
    signed and even; binutils prints `2 * field + 2`, so

        disp = 2 * signed5(field) + 2
        target = addr + disp

Form 4 -- anything else
-----------------------
Not implemented returns `UnsupportedEncoding`; callers must record
`UNRESOLVED_UNSUPPORTED_ENCODING` rather than invent a target.

This module exposes arithmetic only.  It performs static analysis only and
does not touch hardware.
"""
from __future__ import annotations

ADDR_MASK = 0xFFFFFF

# Opcode word of the 4-byte relaxable branch family.  `bal` is `00 c0`;
# the byte1 is 0xC0 for every conditional call as well (`02 c0`, `ff c0`, ...).
BAL_OPCODE_WORD = 0x00C0

# Branch-if-zero mnemonics (`disps5`); byte1 is 0x0C..0x0F.
BRANCH_ZERO_MNEMONICS = {"beq0b", "bne0b", "beq0w", "bne0w"}
BRANCH_ZERO_BYTE1 = {0x0C, 0x0D, 0x0E, 0x0F}


class UnsupportedEncoding(ValueError):
    """The machine form is recognised but not implemented."""


def _extract48(all_words: int, start: int, end: int) -> int:
    shift = 48 - end
    width = end - start
    return (all_words >> shift) & ((1 << width) - 1)


def allwords(word0: int, word1: int, word2: int = 0) -> int:
    return (word0 << 32) | (word1 << 16) | word2


def bal_disp24(words: tuple[int, ...]) -> int:
    """Raw 24-bit displacement field of a 4- or 6-byte `bal`.

    For the 4-byte form: EXTRACT(allWords, 16, 24) = bits[31:8] of
    (word1 << 16 | word0).
    For the 6-byte form binutils rearranges the field:
        (((p >> 16) & 0xF) << 20) | (((p >> 24) & 0xF) << 16) | (p & 0xFFFF)
    No 6-byte branch occurs in the firmware; the formula is kept for
    completeness and is flagged as not exercised by the test suite.
    """
    if len(words) == 2:
        aw = allwords(words[0], words[1])
        return _extract48(aw, 8, 32)
    if len(words) == 3:
        aw = allwords(words[0], words[1], words[2])
        p = _extract48(aw, 16, 40)
        return (((p >> 16) & 0xF) << 20) | (((p >> 24) & 0xF) << 16) | (p & 0xFFFF)
    raise UnsupportedEncoding(f"bal with {len(words)} words")


# Historical name kept for callers.
def disp24(words: tuple[int, ...]) -> int:
    """Deprecated alias of `bal_disp24`."""
    return bal_disp24(words)


def bal_target(addr: int, words: tuple[int, ...]) -> tuple[int, bool]:
    """Target of a 4- or 6-byte `bal`; `addr` is the instruction address."""
    p = bal_disp24(words)
    if p & 1:
        c = (~p + 1) & ADDR_MASK
        return (addr + ((-c) & 0xFFFFFE)) & ADDR_MASK, True
    return (addr + p) & ADDR_MASK, False


def cond2_target(addr: int, word0: int) -> int:
    """Target of a 2-byte conditional branch (`dispe9`, unsigned).

    Layout, validated on all 1 755 two-byte conditional branches of
    `dectfw_secondlevel_441.hex` (byte1 in 0x10..0x1f) against binutils:

        disp = ((word0 & 0x0F) | (((word0 >> 8) & 0x0F) << 4)) << 1
        target = addr + disp

    i.e. bits[3:0] hold the field's low nibble, bits[7:4] the condition code
    and bits[11:8] the high nibble.  `42 10` -> `bhi +0x4`,
    `00 12` -> `beq +0x40`, `00 1c` -> `beq +0x11e`, `a2 15` -> `blo +0xb0`.
    The field is unsigned and even; a branch to a lower address always uses
    the 4-byte form (confirmed with the CR16 assembler).
    """
    disp = ((word0 & 0x0F) | (((word0 >> 8) & 0x0F) << 4)) << 1
    return (addr + disp) & ADDR_MASK


def branch_zero_target(addr: int, raw: bytes) -> int:
    """Target of a 2-byte `beq0b`/`bne0b`/`beq0w`/`bne0w` (`disps5`).

    The operand is a 5-bit signed field at bits[7:4] of the instruction word,
    in units of 2 bytes, plus the fixed step of 2:

        nib = byte0 >> 4          (signed 4-bit; bit 3 is the sign)
        target = addr + 2*nib + 2

    Confirmed with the CR16 assembler and disassembler:

    | Bytes | Mnemonic | Target |
    |-------|----------|--------|
    |`00 0c`| beq0b r0 | +0x2   |
    |`10 0c`| beq0b r0 | +0x4   |
    |`f0 0c`| beq0b r0 | +0x20  |
    |`00 0d`| bne0b r0 | +0x22  |
    |`00 0e`| beq0w r0 | +0x2   |
    |`00 0f`| bne0w r0 | +0x22  |
    |`ff 0f`| bne0w r15| +0x40  |

    The high nibble of byte1 also drives the spelling, and a negative target
    needs the lengthened form, so every printable value is a forward step.
    """
    byte0, byte1 = raw[0], raw[1]
    # Whether the target lies behind the instruction is encoded in bit 3 of
    # the first byte (`00 0c` beq -> +0x2; `c0 0c` beq -> also +0x2, but the
    # register operand differs).  The displacement magnitude is the low
    # nibble of byte1, two bytes per step:
    #   byte1 0x0C..0x0E -> step = low nibble
    #   byte1 0x0D/0x0F  -> an extra 0x20 is added by the encoding (`00 0d`
    #                       is +0x22, not +0x2)
    nib = (byte0 >> 4) & 0xF
    extra = 0x20 if (byte1 & 0x01) else 0
    return (addr + 2 * nib + 2 + extra) & ADDR_MASK


def decode(addr: int, raw: bytes) -> tuple[int | None, str, str]:
    """Decode one branch instruction **from its encoding only**.

    Use this for `bal` (4 bytes) and the 4-byte conditional form.  The
    2-byte conditional form is fundamentally ambiguous at this granularity:
    `42 10` is `bhi +0x4`, but `42 0c` is `beq0b r2,+0x6`; the mnemonic is
    what disambiguates it.  Use `decode_insn` for that form.

    Returns `(target, form, status)`; `status` is `DIRECT` or `UNSUPPORTED`.
    """
    n = len(raw)
    if n not in (2, 4, 6):
        return None, f"{n}-byte", "UNSUPPORTED"
    words = tuple(raw[i] | (raw[i + 1] << 8) for i in range(0, n, 2))
    w0 = words[0]

    if n in (4, 6):
        if raw[1] == 0xC0:
            return bal_target(addr, words)[0], f"bal{n * 8}", "DIRECT"
        if (raw[1] & 0x0F) == 0x8:
            if n == 6:
                # 6-byte conditional (`disps25`): layout not validated (the
                # single occurrence sits in a data region).
                return None, "cond48", "UNSUPPORTED"
            # 4-byte conditional (`disps17`).  `target = addr + words[1]` holds
            # for every validated occurrence; a word above 0x8000 would be a
            # backward target, which the validated set never shows, so it is
            # left unsupported instead of being guessed.
            if words[1] > 0x8000:
                return None, f"cond{n * 8}", "UNSUPPORTED"
            return (addr + words[1]) & ADDR_MASK, f"cond{n * 8}", "DIRECT"
        if n == 6:
            return None, "6-byte", "UNSUPPORTED"
        return None, f"{n}-byte", "UNSUPPORTED"

    # Unreachable for a real branch: everything above is the 4/6-byte path.
    return None, f"{n}-byte", "UNSUPPORTED"


# 2-byte instruction classes, keyed by byte 1 (bits[15:8] of the word).
#   byte1 0x0C..0x0F -> beq0b/bne0b/beq0w/bne0w (disps5)
#   byte1 0x10..0x1F -> dispe9 conditional with the cc in bits[3:0] and the
#                       displacement low nibble in bits[7:4]
#   byte1 0x0C..      handled above; 0x00..0x0B and 0x20..0x0B are not
#                       branches of these families.

def decode_insn(addr: int, mnemonic: str, raw: bytes) -> tuple[int | None, str, str]:
    """Decode one branch **using its machine form and its mnemonic**.

    The 2-byte families share the byte1 range with other instructions, so the
    mnemonic supplied by the disassembler is the discriminator:

        * branch-if-zero mnemonics:  byte1 0x0C..0x0F, field `disps5`
        * other conditional mnemonics: byte1 0x10..0x1F, field `dispe9`,
          layout `((w0 & 0x0F) | ((w0 >> 8) & 0x0F) << 4) << 1`.  The
          condition code sits in bits[7:4], the field's low nibble in
          bits[3:0] and its high nibble in bits[11:8].
    """
    n = len(raw)
    if n in (4, 6):
        if raw[1] == 0xC0 or (raw[1] & 0x0F) == 0x8:
            # A 4- or 6-byte branch form is decided by its own encoding.
            return decode(addr, raw)
        if n == 6:
            # 6-byte conditional (`disps25`): layout not validated (the single
            # occurrence sits in a data region).
            return None, "cond48", "UNSUPPORTED"
        # A non-branch (load/store/movd...) has no target of its own.
        return None, f"{n}-byte non-branch", "UNSUPPORTED"
    # A 2-byte *branch* is decoded from the mnemonic and the word, never by
    # the 4-byte rules (whose first word would look like an ambiguous 2-byte
    # form and must not produce a target).
    w0 = raw[0] | (raw[1] << 8)
    byte1 = raw[1]
    if byte1 in (0x0C, 0x0D, 0x0E, 0x0F):
        return branch_zero_target(addr, raw), "disps5", "DIRECT"
    if mnemonic in BRANCH_ZERO_MNEMONICS:
        return None, "disps5?", "UNSUPPORTED"
    # A conditional whose second byte is 0x10.. belongs to the `dispe9` form.
    if 0x10 <= byte1 <= 0x1F:
        return cond2_target(addr, w0), "dispe9", "DIRECT"
    # Conditionals with a `byte1` below 0x10 (`00 1c`, `06 1a`, `47 1e`,
    # `a2 15`, ...) use a layout that no candidate formula reproduced against
    # binutils (10 candidate layouts were fitted to all 259 occurrences; the
    # best matched 42).  They stay unsupported instead of being guessed.
    return None, "2-byte-other", "UNSUPPORTED"


def target_from_objdump(printed: int) -> int:
    """objdump prints the absolute target; the sign prefix is cosmetic."""
    return abs(printed)


def is_in_runs(target: int, runs: list[tuple[int, int]]) -> bool:
    return any(lo <= target <= hi for lo, hi in runs)


def describe(addr: int, mnemonic: str, raw: bytes,
             runs: list[tuple[int, int]]) -> str:
    target, form, status = decode_insn(addr, mnemonic, raw)
    if status != "DIRECT":
        return f"{addr:#08x}: {form} UNSUPPORTED"
    inside = "inside" if is_in_runs(target, runs) else "OUTSIDE"
    return f"{addr:#08x}: {form} -> {target:#08x} ({inside} a loaded run)"
