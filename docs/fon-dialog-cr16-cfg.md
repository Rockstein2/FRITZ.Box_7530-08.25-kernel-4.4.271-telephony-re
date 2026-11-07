# SC14448 firmware: CR16 control-flow graph

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
   absolute addresses with no segment extension (§5).

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
| conditional (`beq`, `bne`, `bhi`, `br`, `bcc`, …) | branch target **and** next address |
| unconditional `jump`, `jmp` | target only |
| `popret`, `retx` | none |
| everything else | next address |

`br` is the objdump mnemonic for the `dispe9` form and is classified with
the conditionals.

### 2.2 Statistics, second-level image

| Quantity | Value |
|---|---|
| Runs | 9 |
| Decoded instructions | 19 570 |
| `DIRECT_RESOLVED` | 22 815 |
| `DIRECT_UNSUPPORTED` | 46 |
| `INDIRECT_REGISTER` | 382 |
| `INDIRECT_TABLE_RESOLVED` | 0 |
| `INDIRECT_UNRESOLVED` | 0 |
| `FALLTHROUGH_UNRESOLVED` | 9 |
| `OUTSIDE_LOADED_IMAGE` | 2 |
| `TARGET_NOT_INSTRUCTION` | 30 |
| **Total** | 23 284 |

(`p2test`: 21 503 edges, 21 007 resolved, 67 unsupported, 396 indirect,
1 outside, 22 off-boundary.)

## 3. Reachability modes

| Mode | Starts | Status | Reached (normal) |
|---|---|---|---|
| **A** | `0x1602` | *candidate*, never verified | **9 042** |
| **B** | 386 heuristic candidates | research only | **17 600** |
| **C** | verified entries | empty: no loader or vector table read | 0 |

Mode A is smaller than before because it now follows the corrected branches
instead of the ones that used to leak into unrelated code.

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

There is **no table dispatch**.  Every indirect edge is one of:

* `jump (ra)` — tail call to the caller's return address, 260 sites;
* `jump (r8,r7)` — one site, register-pair dispatch (`e6 0a`);
* `jal (rp)` — 121 sites, all with a register pair operand, e.g. `d7 00`.

Consequently the earlier hope that a table would hide the PCM RX handler is
not supported.  The remaining unexamined code is whatever is unreachable from
mode A (8 840 instructions) — a research target, not a dispatch table.

---

## 5. What is still unknown

| Item | Why |
|---|---|
| is `0x1602` the reset entry? | no vector table exists at a fixed address; Q47 |
| what `0x000F6002` / `0x000F6400` physically are | the `:m` 16-bit address has no proven extension; Q44 |
| what value `1` in `0x000F6002` means | no dynamic observation |
| is `0x01000000` the PCM buffer? | not part of any loaded run |
| loop count and poll semantics of `0x25F90` | two conditionals decode outside the function |
| 260 two-byte conditionals with a `byte1 < 0x10` | second `dispe9` layout, not fully resolved |

**Next step with the best information/risk ratio:** the static picture no
longer promises a hidden dispatch table.  The productive next move is the
controlled load of the original SC14448 firmware so that the register
meanings can be observed, as planned in the runbook; as a purely offline
interlude, resolve the byte-level contradiction in `0x25F90` §1.2.
