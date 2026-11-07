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

Three claims from the previous version were **wrong or overstated** and are
corrected here:

1. **"2 706 unresolved indirect edges".**  That counter lumped together
   register-indirect jumps, unimplemented direct encodings, off-image targets
   and fall-through gaps.  The categories are now separate (§2) and the
   register-indirect count is **382**.
2. **"404 candidate entries, 8 178 reachable".**  Root detection did not
   exclude fall-through predecessors correctly, and reachability used the
   historical one-hop walk.  Mode A (`0x1602`) now reaches **10 730**
   instructions of 19 570.
3. **"512 words at `0x01000000`" and "poll until ready".**  The two
   conditionals in `0x25F90` decode **forward, out of the function**
   (`0x25FA8 → 0x2619A`, `0x25FB4 → 0x261AE`).  The loop count and the poll
   are therefore unproven; see `fon-dialog-peripheral-init.md` §1.2.

---

## 2. Edge categories

`cr16_cfg.py` assigns exactly one category to every edge:

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
| `bal` / `jal (ra),…` | call target **and** next address (return site) |
| conditional (`beq`, `bne`, `bhi`, `br`, `bswaplo`, …) | branch target **and** next address |
| unconditional `jump`, `jmp` | target only |
| `popret`, `retx`, `ret` | none |
| everything else | next address |

The objdump mnemonic `br` is printed for the `dispe9` form
(`ee 10` → `*+0x20`), so it is classified with the conditionals, not with the
plain jumps.  Contribution lines of a 6-byte instruction are merged before
classification, so they can never appear as instructions or as fall-through
targets (tested).

### 2.2 Statistics, second-level image

| Quantity | Value |
|---|---|
| Runs (blocks) | 9 |
| Decoded instructions | 19 570 |
| `DIRECT_RESOLVED` | 22 714 |
| `DIRECT_UNSUPPORTED` | 46 |
| `INDIRECT_REGISTER` | 382 |
| `INDIRECT_TABLE_RESOLVED` | 0 |
| `INDIRECT_UNRESOLVED` | 0 |
| `FALLTHROUGH_UNRESOLVED` | 9 |
| `OUTSIDE_LOADED_IMAGE` | 42 |
| `TARGET_NOT_INSTRUCTION` | 91 |
| **Total edges** | 23 284 |

`DIRECT_UNSUPPORTED` = 45 four-byte conditionals whose second word exceeds
`0x8000` (with no validated backward case) + 1 six-byte conditional at
`0x92FC` (inside a data region).

`INDIRECT_REGISTER` = 260 `jump (ra)`, 1 `jump (e6 0a)` and 121 `jal (rp)`
forms.  All of them are tail calls or dispatch stubs; no call table was found.

## 3. Reachability modes

`run_modes()` returns three independent results:

| Mode | Starts | Status | Instructions reached |
|---|---|---|---|
| **A** | `0x1602` only | *candidate*, never "verified" | **10 730** |
| **B** | 386 heuristic candidates (call targets that are not fall-through targets and not mid-instruction) | research only | **17 652** |
| **C** | verified entries | **empty** — no loader or vector table has been read | 0 |

Mode C is empty on purpose: `verified=True` is never set heuristically.

### 3.1 The chain to `0x25F90`

Every link is an instruction boundary and is reachable in mode A.

```text
0x1602  00 c0 f6 23  bal -> 0x39F8
0x3A2C  02 c0 8c 25  bal -> 0x25FB8
0x25FBA ff c0 d7 ff  bal -> 0x25F90
0x25F9E fd c0 1d c6  bal -> 0x25BA   (fill helper, loop body)
0x25FAA fd c0 af c5  bal -> 0x2558   (after the loop)
0x2570  00 c0 1c 17  bal -> 0x3C8C   (inside 0x2558)
0x257E  ff c0 7b ff  bal -> 0x24F8   (next function, run-off entry)
```

Inside `0x25F90` the two conditionals are backward branches:
`0x25FA8` `49 1f` → `0x25F9A`, `0x25FB4` `1d 1f` → `0x25FAE` (both confirmed
with binutils at the instruction's own address).  That makes
`0x25F9A`–`0x25FA8` a loop and `0x25FAE`–`0x25FB4` a wait loop.

`0x2558` does **not** call `0x257E`: its `bal` goes to `0x3C8C`.  `0x257E`
directly follows `0x2558`'s last instruction and is entered only by running
off its end; no `bal` in the image targets it.  The chain
`0x25FAA → 0x2558 → 0x257E → 0x24F8` printed in earlier reports is therefore a
sequence of *code addresses*, not of call edges.

A limit of linear-sweep decoding that the CFG does not model: a `bal` target
can also be reached by falling into another function's body, which is what
happens between `0x2558` and `0x257E`.

### 3.2 Functions whose status changed

| Address | Previous status | Now |
|---|---|---|
| `0x1602` | "candidate top level / root" | candidate only; reached by fall-through from `0x15FE`, so **not** a heuristic root |
| `0x25F90` | "512-word fill then poll" (unproven) | loop decoded and confirmed with binutils; 512 words, 7 links checked |
| `0x2558` | "same function as `0x257E`" | own function; calls `0x3C8C`; no caller of `0x257E` exists |
| `0x24F8` | "recursive re-entry" | not recursive; returns when `r2 == 0` |
| 404 roots | candidate entries | 386 heuristic candidates, all `verified=False` |

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
