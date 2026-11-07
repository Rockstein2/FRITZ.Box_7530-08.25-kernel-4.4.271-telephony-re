# First-level hand-off branches: decoding

Status: **offline analysis.**  The three branches that end the loader's
control flow are examined here against the CR16 branch encodings.

---

## 1. The encodings involved

From `opcodes/cr16-opc.c` (`BRANCH_INST`):

```text
{NAME, 1, OPC,            28, BRANCH_INS, {{cc,20}, {dispe9,16}}}   /* 2-byte */
{NAME, 2, (OPC<<4)+0x8,   24, BRANCH_INS, {{cc,20}, {disps17,0}}}   /* 4-byte */
{NAME, 3, (OPC<<4),       16, BRANCH_INS, {{cc,4},  {disps25,16}}}  /* 6-byte */
```

and `cr16_optab`:

```text
{16, arg_c, OP_EVEN|OP_UNSIGNED},   /* disps17 */
{24, arg_c, OP_EVEN|OP_UNSIGNED},   /* disps25 */
```

`OP_EVEN` is checked **only by the assembler**
(`gas/config/tc-cr16.c:1975`, `if (value % 2) return OP_NOT_EVEN`); the
disassembler does not apply it.

`arg_c` for a branch (`cr16-dis.c`, `case arg_c`):

```c
longdisp = constant;
mask = (1 << size) - 1;
switch (size) {
  case 8:  longdisp <<= 1; if (longdisp & (1<<size)) { sign; negate; } break;
  case 16: case 24: if (longdisp & 1) { sign; negate; } break;
  default: "Wrong offset ..."
}
constant = longdisp & mask;
number = memaddr + (sign ? -constant : constant);
```

For `disps17` the field size is 16 with `start_bits = 0`, so it is `word1`
of the instruction, and the sign is carried in **bit 0 of that field**.

## 2. Validation of the formula against the assembler

| Source | Bytes | Field (`word1`) | Result |
|---|---|---|---|
| `br *+0x12c:m` | `e0 18 2c 01` | `0x012c` | +300 ✔ |
| `br *+0x3e8:m` | `e0 18 e8 03` | `0x03e8` | +1000 ✔ |
| `bne` forward over 400 nops | `10 18 00 00` | `0x0000` | +0 at the branch, correct ✔ |

The assembler **cannot emit a backward `disps17`**: building a loop of 400
`nop`s and branching back produces `e0 18 00 00` with the forward sign.
The backward form in this firmware was therefore hand-coded, and gas is not
an independent oracle for it.

## 3. The three branches

| Site | Bytes | Field | Sign bit | Magnitude | Target |
|---|---|---|---|---|---|
| `0x1017C` | `e0 18 85 ff` | `0xFF85` | 1 (negative) | −123 | **`0x010101`** |
| `0x10298` | `e0 18 69 fe` | `0xFE69` | 1 (negative) | −407 | **`0x010101`** |
| `0x10250` (`bne`) | `10 18 b1 fe` | `0xFEB1` | 1 (negative) | −335 | **`0x010101`** |

### What `0x010101` is

`0x010101` is **odd**, and the assembler would reject it (`OP_EVEN`), so the
address is not a legal branch-displacement value.  The even address one bit
below it, `0x010100`, **is** an instruction and a basic-block leader:

```text
0x10100  movb $0x2:s,r2      <- retry loop entry
0x10102  bal 0x102C6         <- send
0x10106  bal 0x1029C         <- receive
```

So the displacements are one too large, in magnitude, by exactly one.  This
is consistent with the low bit of the field being a **flag** rather than
part of a signed magnitude, i.e. the true displacement is `-(word1 >> 1)`
with a separate sign indication — but that reading does not fit the
forward cases (`0x012c >> 1 = 0x96`, not `0x12c`).

**Status: UNRESOLVED.**  The three branches are still reported by the
current decoder as `DIRECT_UNSUPPORTED`, and that is correct: the target
`0x010101` is not an instruction, so a decoder that accepted it would be
wrong.  The plausible target is `0x010100`, but the encoding rule that
produces it is not established.

### The 6-byte form at `0x10284`

`10 00 ef 0e 85 fd` is the `disps25` form.  Applying the same `arg_c` path
gives a value far outside the image, so the rule for that field is not
established either.  **UNSUPPORTED.**

## 4. What the branches mean in the control flow

Whatever the exact target, the three sites sit at:

| Site | Where it is | Where it goes (by role) |
|---|---|---|
| `0x1017C` | after `movb $0x15,r2` and four `bal 0x102C6` | the "zero header / end of transfer" path |
| `0x10298` | after `movb $0x15,r2` and `movb r3,r2` | the **error** path (sends `0x15` = NAK, then `r3`) |
| `0x10250` (`bne`) | after a failed ACK check | back to the retry loop |

The `bne` at `0x10250` decodes with the same rule to the same value, and its
role in the code is clearly "the peer did not answer `0x06`, start over" —
which matches `0x10100`.  That gives the `0x10100` reading independent
support from the control-flow structure.

## 5. The consequence for the hand-off

The loader's own code never branches into the loaded image by a decodable
instruction:

* `0x1017C` is on the **success/zero-length** path and targets the retry
  loop or an unresolved address;
* `0x10284` follows `CFG` bit 8 being set — the strongest candidate for a
  hand-off — but its target is unresolved;
* `0x10298` is the error path.

So the hand-off, if it exists as a branch, is the `0x10284` instruction,
whose target this analysis cannot compute.

## 6. What would settle it

1. A CR16C branch-encoding table for `disps17`/`disps25` from Dialog or
   Renesas (no offline copy).
2. A capture of the loader running: the address the CPU fetches after
   `0x10284`.
3. A disassembly of any other image built from the same toolchain that
   contains an unconditional branch over a known distance, which would give
   a second data point for the field layout.
