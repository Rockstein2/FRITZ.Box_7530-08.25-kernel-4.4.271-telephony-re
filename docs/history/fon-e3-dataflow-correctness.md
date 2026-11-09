# FON-E3 — dataflow correctness and interprocedural proof audit

> **Status: offline soundness audit.**  No firmware execution.

## 1. Why E2 was not strong enough

E2's `make_summary()` walked basic blocks in address order and accumulated
global `written` and `reads` sets.  A register could look preserved even if a
different CFG path wrote it first, and a call argument could be approved without
proving that the value reaches the specific use.

E3 replaces that with a per-function may-write analysis:

- forward fixed point over the function's intraprocedural CFG;
- `may_in`/`may_out` are unions of registers that can have been written;
- `before[addr]` is the union before each instruction;
- a pair is preserved to a use only if neither half is in `before[use]`;
- a call, an indirect call or a register-list memory form writes all modelled
  registers;
- an external predecessor into a non-entry block makes the incoming set
  unknown, never empty;
- an entry inside a basic block is marked `INFERRED_MID_BLOCK` and cannot
  produce a PROVEN argument.

A use is PROVEN only when:

1. the caller block-entry state and instruction prefix give one known 32-bit
   pair value on all modelled paths;
2. the call is a direct resolved `call`;
3. the caller function entry/path is complete;
4. the callee is complete;
5. the pair is absent from the callee's may-write set at that memory operand.

Unknown calls, stack-passed arguments and return values remain outside the
model.

## 2. E2 proof audit

The E2 baseline is commit `89599db` and its reports are read from that commit.
E3 re-ran every E2 PROVEN argument:

| Image | E2 PROVEN | still PROVEN | downgraded | INVALID |
|---|---:|---:|---:|---:|
| normal | 25 | 21 | 4 | 0 |
| p2test | 10 | 8 | 2 | 0 |

Downgraded normal cases:

- `0x021a30` — caller entry/path incomplete;
- `0x0228ba` — caller and callee incomplete, pair may be written before use;
- `0x023ca4`, `0x024348` — caller entry/path incomplete.

Downgraded p2test cases:

- `0x0243b0`, `0x024754` — caller entry/path incomplete.

The E3 audit matches each old memory use by instruction address and effective
address, not only by `(call_site, callee, pair, constant)`.  A missing or
changed use makes the old proof `INVALID`; the current 25/10 records all match
their old use addresses.

The priority case remains:

```text
0x028a5c  movd $0x00ff4000,(r3,r2)   definition
0x028a62  bal 0x0289b0               call
0x0289b0  loadw 0x0:(r3,r2)          use
0x028a48  storw r5,0x0:(r3,r2)       second use in callee
```

No write to `r3`/`r2` occurs on any modelled path before either use.  The
address is `0x00ff4000`, a peripheral address, not a slot-5 PCM word.

The corrected analyzer reports 91 normal / 42 p2test PROVEN records and
82/92 CANDIDATE records.  The increase is explained by the per-use criterion:
a callee that writes the pair **after** the use no longer invalidates the
argument, while any possible write **before** the use still does.

## 3. E3 table correctness

The E2 report declared `entry_widths_checked=[16,20,24,32]` and both endian
orders.  E3 removes those claims.  The report now states:

- no table entry width, stride, index bound or endianness was decoded;
- a candidate requires a def-use link to the register actually consumed by
  the indirect instruction;
- the nearby linked loads are 32-bit accesses, but that is not a table-entry
  width;
- a link is not a table proof, so the confidence remains `CANDIDATE` or
  `UNRESOLVED`.

Corrected counts:

| Image | Indirect | CANDIDATE | UNRESOLVED | PROVEN |
|---|---:|---:|---:|---:|
| normal | 382 | 6 | 376 | 0 |
| p2test | 396 | 17 | 379 | 0 |

## 4. E3 IRQ reporting correction

`irq_paths()` previously read `s.get("indirect_sites")` even though the summary
stored it under `possible_call_targets`.  The field is now read from the actual
summary structure and checked against it in regression tests.  The corrected
count is zero in both images for the current model, but it is now derived from
the correct source rather than silently dropping indirect calls.

The IRQ report also stores a transitive tree: handler → direct callee →
nested callee, with each handler's own memory operations separate from its
children.

## 5. Convergence and exit status

`cr16_dataflow.py` now:

- exits 0 on a converged run;
- exits 1 on `NON_CONVERGED`;
- writes `cr16-dataflow-<image>.incomplete.json`;
- leaves the last confirmed `cr16-dataflow-<image>.json` untouched;
- does not overwrite the combined indirect/PCM reports with a partial set.

`cr16_interproc.py` and `cr16_e3.py` apply the same fail-closed rule to their
normal reports and write `.incomplete.json` diagnostics instead.

A regression test runs with `--max-iterations 1` and checks all three
properties.

## 6. Limitations

- stack spills/reloads are not modelled;
- only direct register-pair arguments are accepted;
- return values are unknown;
- indirect calls and `loadm/loadmp/storm/stormp` are whole-register clobbers;
- a function reached through an unresolved table has no complete entry;
- data decoded as code can still create false blocks.
