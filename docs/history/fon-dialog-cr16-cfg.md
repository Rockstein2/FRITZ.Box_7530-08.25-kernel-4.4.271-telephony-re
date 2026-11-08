# SC14448 firmware: CR16 control-flow graph

> **Status: historical analysis.**
> This document records the reasoning and evidence as of the date it was
> written.  Some of its `UNKNOWN` / `UNVERIFIED` markers have since been
> answered.
> - Current confirmed facts: `../fon-known-facts.md`
> - Current open questions: `../fon-open-questions.md`
> - This file is kept for the reasoning trail, not as a status report.

Status: **offline static analysis.**  This document supersedes the earlier
"global CFG" statistics.  Run `tools/cr16_cfg.py` and
`tools/tests/test_cr16_cfg.py` to reproduce every number below.

Image: `firmware/dectfw_secondlevel_441.hex` unless stated otherwise.
Toolchain: CR16 binutils 2.44, built locally at
`/tmp/opencode/cr16/build/binutils/objdump`; the decoder arithmetic is in
`tools/cr16_branch.py` and is documented in `fon-dialog-cr16-branches.md`.

---

## 1. What changed in this iteration

1. **`dispe9` decoded correctly and used by the tools.**  `0x25FA8`
   (`49 1f`) targets `0x25F9A` and `0x25FB4` (`1d 1f`) targets `0x25FAE`;
   the decoder, the CFG and the tests share one implementation and agree
   with binutils on every one of the 2 076 + 1 934 occurrences (zero
   mismatches, `tools/reports/cr16-branch-validation.json`).
2. **Branch statuses are explicit**: MATCH / MISMATCH / UNSUPPORTED /
   INVALID / ORACLE_UNAVAILABLE; nothing is excluded from the mismatch
   count.
3. **Counter loop resolved from ISA semantics**: 511 writes, not 512
   (see `fon-dialog-peripheral-init.md` §1.2).
4. **`abs20` operand field identified**: `((byte0 & 0x0F) << 16) | word1`,
   so `0x000F6400`, `0x000F6002` and `0x000F5402` really are 18/20-bit
   absolute addresses with no segment extension.
5. **`br` reclassified as an unconditional jump** in this iteration: it has
   no link register and no fall-through, and 615 false fall-through edges
   were removed (§2.2).

## 2. Edge categories

| Category | Meaning |
|---|---|
| `DIRECT_RESOLVED` | decoded from the bytes, target on an instruction boundary inside a run |
| `DIRECT_UNSUPPORTED` | known control-transfer form whose encoding is not implemented |
| `INDIRECT_REGISTER` | `jump (rp)`, `jal (rp)` — target in a register |
| `INDIRECT_TABLE_RESOLVED` | target recovered from a located table (none yet) |
| `INDIRECT_UNRESOLVED` | indirect with no recovered table |
| `FALLTHROUGH_UNRESOLVED` | next address is not a decoded instruction start |
| `OUTSIDE_LOADED_IMAGE` | direct target outside every loaded run |
| `TARGET_NOT_INSTRUCTION` | direct target inside a run but not on a boundary |

### 2.1 Fallthrough rules

| Instruction | Edges |
|---|---|
| `bal` | call target **and** next address (return site) |
| conditional (`beq`, `bne`, `bhi`, `bcc`, …) | branch target **and** next address |
| `br` (unconditional relative branch) | target only — **no** fall-through |
| `jump`, `jmp` (register-indirect) | none: the target is unknown |
| `popret`, `retx` | none |
| everything else | next address |

`br` shares the `dispe9`/`disps17` encoding with the conditionals (it is
condition code `0xE` of the Bcond family), but its semantics are an
unconditional jump: it stores no return address and execution continues only
at the target.  Treating it as a conditional used to add 615 false
fall-through edges; that was corrected and is covered by a test.

### 2.2 Statistics, second-level image

| Quantity | Value |
|---|---|
| Runs | 9 |
| Decoded instructions | 19 570 |
| `DIRECT_RESOLVED` | 22 244 |
| `DIRECT_UNSUPPORTED` | 0 |
| `INDIRECT_REGISTER` | 382 |
| `INDIRECT_TABLE_RESOLVED` | 0 |
| `INDIRECT_UNRESOLVED` | 0 |
| `FALLTHROUGH_UNRESOLVED` | 9 |
| `OUTSIDE_LOADED_IMAGE` | 4 |
| `TARGET_NOT_INSTRUCTION` | 30 |
| **Total** | 22 669 |

(`p2test`: 20 931 edges, 20 502 resolved, 0 unsupported, 396 indirect,
1 outside, 22 off-boundary.)

**All branch forms now decode.**  The 113 formerly unsupported cases were
112 backward `disps17` conditionals and 1 `disps25`; both are implemented
from `cr16-dis.c` (`disps17`: 16-bit magnitude mask, `disps25`: 24-bit), so
`DIRECT_UNSUPPORTED` is 0 and the four `OUTSIDE_LOADED_IMAGE` edges are the
two genuine out-of-image targets reached from both ends of their branches.

## 3. Reachability modes

The three modes are **different experiments**, not three confidence levels of
the same path:

| Mode | Starts | What it answers | Reached (normal) |
|---|---|---|---|
| **A** | candidate `0x1602` | what can be reached if `0x1602` is an entry | **8 340** |
| **B** | 403 heuristic candidates | what could be reached from any likely function root | **17 546** |
| **C** | verified entries | what is proven to run at reset | 0 (none verified) |

None of them is evidence that the SC14448 executes this code — see §8.

Mode A is smaller than in the previous iteration because `br` no longer
contributes a fall-through edge (615 false edges removed) and because the
branches were corrected earlier; both changes only *remove* wrong paths.

### 3.1 The chain to `0x25F90`

All links are instruction boundaries and every one is in mode A.

```text
0x1602  00 c0 f6 23  bal -> 0x39F8
0x3A2C  02 c0 8c 25  bal -> 0x25FB8
0x25FBA ff c0 d7 ff  bal -> 0x25F90
0x25F9E fd c0 1d c6  bal -> 0x25BA   (loop body)
0x25FA8 49 1f       bhi -> 0x25F9A   (backward, condition true)
0x25FAA fd c0 af c5  bal -> 0x2558   (after the loop)
0x2570  00 c0 1c 17  bal -> 0x3C8C   (inside 0x2558)
0x257E  ff c0 7b ff  bal -> 0x24F8   (same function, see 3.2)
```

### 3.2 Function boundaries of `0x2558` … `0x25B8`

The region is **one function** with a single entry and a single exit:

| Address | Instruction | SP effect |
|---|---|---|
| `0x2558` | `push RA` | −2 |
| `0x255A` | `addd $0xfffe,(sp)` | −2 |
| `0x2570` | `bal 0x3C8C` | call/return balanced |
| `0x257E` | `bal 0x24F8` | call/return balanced |
| `0x25B4` | `storw $0,(r1,r0)` | — |
| `0x25B6` | `addd $0x2,(sp)` | +2 |
| `0x25B8` | `popret RA` | +2, returns |

Between `0x257C` and `0x257E` there is no return and no jump: the code runs
straight on.  No `bal` in either image targets `0x257E`, so the earlier
statement “`0x257E` is a separate function” is withdrawn: it is a basic
block of the function that starts at `0x2558`.

The two-byte scratch slot created at `0x255A` receives the word returned by
`0x3C8C`; `0x2574`/`0x2578` read it back as `r3 = low byte`, and
`0x257A`/`0x257C` shift right by 8 to get `r2 = high byte`.  Both are live
until `0x257E` passes `r2` to `0x24F8`; the slot itself is released at
`0x25B6`.

## 4. Indirect calls

Every register-indirect transfer is one of:

* `jump (ra)` — 260 sites, returning to the caller's address;
* `jump (r8,r7)` — one site (`e6 0a`);
* `jal (rp)` — 121 sites, e.g. `d7 00`.

No **dispatch table** (a table of code addresses indexed by a register) was
found: none of the 382 sites reads a pointer from memory before the indirect
jump.  That is a statement about what was found, **not** a proof that no
indirect dispatch exists anywhere.

**11 230 instructions** are not reached from mode A (19 570 decoded −
8 340).  This is arithmetic on a linear disassembly, not a count of code:
the sweep decodes every aligned byte of a run, so constants, strings and
jump tables are decoded as instructions too.  The real amount of *executed,
unreached code* is unknown and is at most this number.  Two things can hide
there: code reachable only through a dispatch the analysis has not found,
and the data that mis-decodes into the off-boundary and unsupported
categories.

---

## 5. What is still unknown

| Item | Level reached |
|---|---|
| is `0x1602` the reset entry? | no loader or vector table read; Q47 |
| what `0x000F6002` / `0x000F6400` physically are | `abs20` addressing is established (L2); the register functions are not |
| what value `1` in `0x000F6002` means | L2 only, no hardware observation |
| is `0x01000000` the PCM buffer? | not part of any loaded run |
| meaning of `0x1001` | L2 only |
| `br` as an indirect dispatcher | 382 register-indirect sites, no table found |
| unsupported branch forms | **0** — all 113 former cases now decode from `cr16-dis.c` |

Status summary, so that this document cannot be read as stronger than the
evidence: the decoder is L2 and validated; the loop of `0x25F90` and the
sequence `0x2558`–`0x25B8` are L3 and L4; **no register meaning in this
document reaches L5**.

**Next step:** the static picture is consistent and no longer promises a
hidden dispatch table.  The informative next stage is the controlled load of
the original SC14448 firmware so that the register meanings (`0x01000000`,
`0x000F6002`, `0xFF6006`) can be observed.

## 6. Evidence levels for this document

| Level | Applies to |
|---|---|
| L1 BYTES | every address and byte quoted in §2 and §3.1 |
| L2 DECODE | the branch forms and the `abs20` operand, validated against binutils (7 807 matches over both images: 4 039 normal + 3 768 p2test; 0 mismatches) |
| L3 CFG | the edges, the reachability counts and the function boundaries of `0x2558`–`0x25B8` |
| L4 SEMANTICS | the loop count of `0x25F90` (see `fon-dialog-peripheral-init.md`) |
| L5 HARDWARE | **nothing in this document** |

L2 does not prove that an instruction executes, L3 does not establish what a
register does, and L4 is a statement about the algorithm under the ISA
assumptions, not about the chip.  Two independent implementations agreeing
here would still share binutils as their origin, so agreement between them
is not extra evidence.
