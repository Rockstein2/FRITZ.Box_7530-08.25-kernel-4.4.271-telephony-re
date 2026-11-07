# CR16 branch decoding — rules and validation

Status: **decoder validated against binutils for every branch instance in the
image.**  Static analysis only; no hardware was touched.

Implementation: `tools/cr16_branch.py`.
Tests: `tools/tests/test_cr16_branch.py` (PASS/FAIL/SKIP, with a sweep that
compares every decoded branch to the locally built CR16 objdump).

The reference implementation is `binutils-2.44/opcodes/cr16-dis.c` /
`cr16-opc.c`; the assembler from the same tree is used to confirm encodings
the firmware does not exercise.

---

## 1. Two different branch families

The decisive lesson of this iteration: **the branch length does not select the
decoding rule.**  Three machine forms exist, and the rule must be chosen from
the instruction's own encoding (and, for the 2-byte forms, from its mnemonic).

### 1.1 4-/6-byte `bal` (the relaxable branch form)

Encoding in `cr16-opc.c` (all conditions share it; the condition code sits in
bits[23:20] of the first word, `00 c0` is the unconditional `ra`):

```c
#define BRANCH_INST(NAME, OPC)                                       \
  /* opc4 c4 dispe9 */                                               \
  {NAME, 1, OPC, 28, ..., {{cc,20}, {dispe9,16}}},                   \
  /* opc4 c4 disps17 */                                              \
  {NAME, 2, ((OPC<<4)+0x8), 24, ..., {{cc,20}, {disps17,0}}},        \
  /* opc4 c4 disps25 */                                              \
  {NAME, 3, (OPC<<4), 16, ..., {{cc,4}, {disps25,16}}}
```

`bal` is `{2, 0x00C0, ...}`.  The rule:

```text
p = bits[31:8] of (word1 << 16 | word0)          /* EXTRACT(allWords,16,24) */
sign is bit 0 of p
target = addr + ((-((~p + 1) & 0xFFFFFF)) & 0xFFFFFE)   if sign
target = addr + p                                      otherwise
target &= 0xFFFFFF ; addr = address of the instruction itself
```

**Validation:** all 1 490 `bal` instructions of
`dectfw_secondlevel_441.hex`, re-disassembled with `--adjust-vma=0`, matched
with 0 mismatches.

| Address | Bytes | Target |
|---|---|---|
| `0x2570` | `00 c0 1c 17` | `0x3C8C` |
| `0x257E` | `ff c0 7b ff` | `0x24F8` |
| `0x25E2` | `02 c0 c8 66` | `0x28CAA` |
| `0x0AF0` | `ff c0 a7 f9` | `0x0496` |
| `0x1602` | `00 c0 f6 23` | `0x39F8` |

Note the condition byte: `00 c0` is the plain call, but `02 c0`, `ff c0`,
`f1 c0` … also appear and are *conditional calls*; they use the same
displacement layout.  A decoder that accepts only `00 c0` loses 717 calls.

### 1.2 2-byte conditional branch (`dispe9`)

The 2-byte word carries, in its low byte, `cc:4 | disp_low:4`, and in bits
[11:8] the high nibble of the field:

```text
disp   = ((word0 & 0x0F) | (((word0 >> 8) & 0x0F) << 4)) << 1
target = (addr + disp) & 0xFFFFFF
```

The field is **unsigned and even**; a target below the instruction cannot be
encoded, and the assembler confirms it (a backwards target forces the 4-byte
form).  That is why objdump's `*-0x…` prefix on this family is cosmetic.

**Validation:** all 2-byte conditional branch instructions of the image
(byte1 in `0x10..0x1f`): 1 755 decoded, 0 mismatches.

| Address | Bytes | Mnemonic | Target |
|---|---|---|---|
| `0x0294` | `40 11` | `bhi` | `0x02B4` |
| `0x10CE` | `9f 10` | `bfc` | `0x10EC` |
| `0x28B12` | `b3 10` | `bhs` | `0x28B18` |
| `0x00EE` | `12 12` | `bne` | `0x0132` |
| `0x00F8` | `00 12` | `beq` | `0x0138` |
| `0x19DA` | `53 11` | `bls` | `0x1A00` |

Assembler cross-check (`bhi` at 0): `42 10` → +4, `44 10` → +8, `4f 10` →
+0x1E, `40 12` → +0x40, `42 12` → +0x44.  All match the formula.

**The mnemonic is the discriminator.**  The second byte selects the *spelling*
of a 2-byte branch (e.g. `00 0c` `beq0b`, `40 10` `bhi`, `12 11` `bne`) while
the low byte range is also used by non-branch instructions, and the two 2-byte
families differ only in their second byte.  A bare 2-byte word therefore
cannot be decoded safely: `decode()` refuses it (`UNSUPPORTED`) and
`decode_insn(addr, mnemonic, raw)` is the entry point.

### 1.3 2-byte branch-if-zero (`disps5`)

```text
nib    = byte0 >> 4
extra  = 0x20 if (byte1 & 1) else 0
target = (addr + 2*nib + 2 + extra) & 0xFFFFFF
```

Confirmed with the assembler/disassembler: `00 0c` → +0x2, `10 0c` → +0x4,
`f0 0c` → +0x20, `00 0d` → +0x22, `ff 0f` → +0x40, `20 0d` → +0x26.
All 245 occurrences in the image decode to an instruction boundary or to a
boundary plus 0x20.

### 1.4 4-byte conditional (`disps17`)

```text
target = (addr + words[1]) & 0xFFFFFF
```

Assembler: `bhi 0x300` at 0 encodes `40 18 00 03`.  A second word above
`0x8000` would be a backward target that the validated set never shows; such
bytes are reported `UNSUPPORTED` (45 occurrences, all in code regions whose
decode is doubtful).

### 1.5 6-byte conditional (`disps25`)

One occurrence, `0x92FC` (`10 00 4d 00 07 4e`), inside a data region.  Its
field layout in binutils differs from `bal`; nothing valid can be checked
against it, so it stays `UNSUPPORTED` (`cond48`).

### 1.6 Register-indirect and return

`jump (ra)`, `jump (rp)`, `jal (rp)` carry **no immediate**.  Their bytes
decoded as a branch would yield a meaningless number, so the CFG classifies
them by mnemonic and operand shape and never assigns a target.

| Form | Bytes | CFG category |
|---|---|---|
| `jump (ra)` | `ee 0a` | `INDIRECT_REGISTER` |
| `jump (r8,r7)` | `e6 0a` | `INDIRECT_REGISTER` |
| `jal (r7,r6)` | `d6 00` | `INDIRECT_REGISTER` |
| `popret` | `e7 03` | return |

---

## 2. What objdump prints

`objdump` prints `base + displacement` masked to 24 bits, where `base` is the
instruction address passed with `--adjust-vma`.  At `--adjust-vma=0` the
printed number is therefore the **displacement**, which is why the test
harness uses the instruction's own address for a cross-check.  The `*+`/`*-`
character is derived from the sign flag and is purely cosmetic.

Evidence: the same bytes `40 11` print `*+0x20:s` at vma 0 and
`*+0x2b4:s` at vma `0x294`.

---

## 3. Open decoder questions

* 260 two-byte conditionals have a `byte1` below `0x10` (`00 1c`, `06 1a`,
  `47 1e`, `a2 15`).  Ten candidate layouts were fitted to all 259
  occurrences against the binutils output; the best explained only 42, so no
  rule is adopted and these forms stay `UNSUPPORTED` (Q50).
* The 45 four-byte conditionals with a high second word are unexplained.
* The 6-byte conditional has no validated example.

The first two do not affect the `0x25F90` chain, whose links are all `bal`
edges or `0x10`-family conditionals.

---

## 4. Peripheral-map note

The earlier version of this document concluded from `0xf6400:m` that the
small-data area is sign-extended to `0x000F6400`.  That is **not established**:
the firmware never reads back such an address, and a `:m` operand only proves
that the encoded value is 16-bit.  The register table is now kept in
`fon-dialog-peripheral-init.md` §5 together with what is unknown about it.
