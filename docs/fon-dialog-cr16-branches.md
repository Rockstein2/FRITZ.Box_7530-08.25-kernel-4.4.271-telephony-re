# CR16 branch decoding — rules, validation, and the remaining unknowns

Status: **decoder fixed and validated against binutils for every branch
instruction of both images; zero mismatches.**
Static analysis only; no hardware was touched.

Implementation: `tools/cr16_branch.py`.
Tests and report: `tools/tests/test_cr16_branch.py --json <file>`;
the checked-in summary is `tools/reports/cr16-branch-validation.json`.

Reference implementations: `binutils-2.44/opcodes/cr16-dis.c` and
`cr16-opc.c` (from the OpenWrt build tree) and the git master copies (the
CR16 code is identical), plus the CR16A Programmer's Reference Manual,
Appendix A (freely available; the bit-field appendix is authoritative for
the formats and was used for the flag semantics as well).

---

## 1. Why the previous version disagreed with itself

Earlier iterations recorded that `objdump` shows the loop head of `0x25F90`
as `49 1f  bhi *-0x25f9a`, while the Python decoder said `0x2619A`.  The
cause was misreading the printed text:

`cr16-dis.c` computes

```c
number = (relative ? memaddr : 0)
       + (sign_flag ? ((- a->constant) & 0xffffffe) : a->constant);
```

and prints `*-X` whenever `sign_flag` is set — the `-` is the **sign of the
displacement**, and the number printed is still the absolute target
`memaddr + displacement`.  So `*-0x25f9a` at address `0x25FA8` means
“target `0x25F9A`, reached by a negative displacement”, not
“`0x25FA8 - 0x25F9A`”.  The decoder was applying the right arithmetic but
the documentation was re-reading the printed text as a subtraction.

Proof that the print path adds `memaddr`: the same two bytes at base 0 print
the displacement itself.

```text
base 0x000000  49 1f -> *-0xfffff2:s        ( = -0x0E as a 24-bit value )
base 0x001000  49 1f -> *-0xff2:s           ( = 0x1000 - 0x0E )
base 0x025fa8  49 1f -> *-0x25f9a:s         ( = 0x25FA8 - 0x0E )
```

## 2. `dispe9`, field by field

Three independent sources agree on the field placement:

| Source | Statement |
|---|---|
| `cr16-opc.c` | `BRANCH_INST`: `{{cc,20},{dispe9,16}}`, `match_bits` 28 |
| `cr16-dis.c` | `case 8: p = makelongparameter(allWords,0,start_bits)` then `((p & 0xF00) >> 4) \| (p & 0x0F)` |
| assembler round trip | changing bits 7..4 changes only the mnemonic, never the printed displacement |

In machine bytes `[b0, b1]` of a 2-byte instruction:

```text
d1..d4 = b0 & 0x0F        low nibble of the FIRST byte
d5..d8 = b1 & 0x0F        low nibble of the SECOND byte
cc     = b1 >> 4          condition code
constant  = (b1 & 0x0F) << 4 | (b0 & 0x0F)
longdisp  = constant << 1
sign      = longdisp & 0x100
target    = addr + (-((~longdisp + 1) & 0xFF))   if sign
            addr + (longdisp & 0xFF)            otherwise
```

`tools/cr16_branch.py` implements exactly this in `cond2_disp()` and
`cond2_target()`; the CFG and the tests call those two functions and hold no
second copy of the rule.

Worked values:

| Site | Bytes | constant | sign | displacement | target |
|---|---|---|---|---|---|
| `0x25FA8` | `49 1f` | `0x0E` | 1 | −0x0E | `0x25F9A` |
| `0x25FB4` | `1d 1f` | `0x06` | 1 | −0x06 | `0x25FAE` |
| `0x25E64` | `4d 19` | `0xC6` | 1 | −0xC6 | `0x25D9E` |
| `0x28C00` | `3a 1f` | `0x0C` | 1 | −0x0C | `0x28BF4` |
| `0x000EE` | `12 12` | `0x22` | 0 | +0x44 | `0x00132` |
| `0x00294` | `40 11` | `0x10` | 0 | +0x20 | `0x002B4` |

Boundaries: the displacement is an 8-bit even signed value, so the range is
−254..+254 and the target is masked to 24 bits (`cond2_target(0xFFFF00,
0x0010) == 0xFFFF00`; a backward branch from `0x10` wraps to `0xFFFFF2`).

## 3. Other branch forms

| Form | Rule | Status |
|---|---|---|
| `bal`, 4 bytes, byte1 `0xC0` | 24-bit field over bits[31:8], sign in bit 0 | validated, 2 863 matches |
| 4-byte conditional, byte1 low nibble `0x8` | `addr + word1` (forward); a word above `0x8000` is not decoded | 459 matches, 112 unsupported |
| `beq0b/bne0b/beq0w/bne0w` | `2*(byte0>>4) + 2 (+0x20 if byte1 & 1)` | validated, 475 matches |
| 6-byte conditional, byte1 `0x06` | not implemented | 1 unsupported (`0x92FC`, in a data region) |
| `jump (rp)`, `jal (rp)` | no immediate | not a branch: 778 instructions |

`objdump` prints the branch-if-zero family as `2*offset + 2` (a
displacement), so the test converts that number by adding the instruction
address before comparing.

## 4. Full validation (machine-readable)

`tools/reports/cr16-branch-validation.json` holds every case that is not a
match; the full tables are reproduced by rerunning the test.

| Image | sha256 (first 16) | form | MATCH | UNSUPPORTED | INVALID | MISMATCH |
|---|---|---|---|---|---|---|
| normal | `7cac33c72b222246` | bal32 | 1 490 | 0 | 0 | 0 |
| normal | | dispe9 | 2 076 | 0 | 0 | 0 |
| normal | | disps5 | 245 | 0 | 0 | 0 |
| normal | | cond32 | 228 | 45 | 0 | 0 |
| normal | | cond48 | 0 | 1 | 0 | 0 |
| normal | | register-indirect | 0 | 0 | 382 | 0 |
| p2test | `6361384d0e3b717e` | bal32 | 1 373 | 0 | 0 | 0 |
| p2test | | dispe9 | 1 934 | 0 | 0 | 0 |
| p2test | | disps5 | 230 | 0 | 0 | 0 |
| p2test | | cond32 | 231 | 67 | 0 | 0 |
| p2test | | register-indirect | 0 | 0 | 396 | 0 |

`ORACLE_UNAVAILABLE` is 0 in both images.  “INVALID” here means “not a
branch instruction”, not “malformed”.

## 5. What remains open

* 45 (normal) and 67 (`p2test`) four-byte conditionals whose second word is
  above `0x8000`.  The assembler produces `40 18` + a forward word for a
  forward target; no backward case could be assembled, so the encoding of a
  backward 4-byte conditional is still unknown (Q51).
* one 6-byte conditional at `0x92FC` inside a data region.
* the CR16A manual places `d1..d4` in bits 4..0 and `cc` in bits 8..5, one
  bit away from what binutils implements and what all firmware evidence
  supports.  The CR16C/B manuals could not be read offline, so the difference
  is recorded, not explained (Q50).
