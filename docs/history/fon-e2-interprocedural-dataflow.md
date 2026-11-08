# FON-E2 — interprocedural dataflow and call/return CFG

> **Status: offline research.**  No firmware execution and no hardware.

This document records the reasoning behind the E2 changes to
`tools/cr16_dataflow.py` and the new `tools/cr16_interproc.py`.

## 1. E1 limitation

E1 intentionally stopped at a `CALLS` instruction:

```text
call site -> (no continuation)
```

That prevented both the callee and the natural continuation after return from
being explored.  It was conservative for register values but lost control-flow
coverage.

## 2. E2 call/return CFG

A direct call now produces two CFG edges:

```text
call site
   |-- call ------> callee entry
   |-- fallthrough -> continuation after return
```

The dataflow transfer at the call still clears caller state.  This means the
continuation is reachable but starts with no inherited constants.  It does not
pretend that the callee preserved any register.  `RETS` blocks have no normal
successor.

This is not a stack-sensitive return matcher: a `noreturn` callee cannot be
proven from the instruction alone, so its continuation is kept as a
conservative possibility.  That can add a false path, but it cannot hide a
real return path.

## 3. Fixed-point convergence

The loop has an explicit cap (`MAX_ITERS = 1000`) and records:

```json
{
  "analysis_status": "CONVERGED",
  "converged": true,
  "iterations": 4,
  "max_iterations": 1000
}
```

If the cap is reached before two consecutive fixed states, the report says
`NON_CONVERGED`, keeps the iteration details and marks every new `RESOLVED`
row as `CANDIDATE`.  The tool no longer emits a completed-looking report after
a silent iteration limit.

The transfer/merge domain is still finite and exact-agreement based:

- a register/pair is kept only when every modelled incoming state agrees;
- an unknown predecessor or an indirect edge clears the value;
- a call clears caller state;
- values carry instruction provenance.

The full scan was retained because it converges in four iterations on both
images; a worklist would not change these results, but the convergence status
is now explicit.

## 4. Interprocedural summaries

`cr16_interproc.py` builds a summary for each direct-call target and vector
entry:

```text
reads_before_write
written
calls
returns
indirect_sites
memory_operations
```

A direct-call constant is propagated only when the caller sets a pair
immediately before the call, the callee reads both pair members before any
proven write, and the callee consumes them in a constant-displacement memory
operand.  If the callee writes either half, the result is `CANDIDATE`.

Indirect or unknown calls clobber all registers.  The register-list forms
`loadm`, `loadmp`, `storm` and `stormp` are not decoded by the xref parser;
they are treated as a whole-register clobber, so they cannot produce a
`PROVEN` argument.  Stack-passed arguments, register-pair return values and
recursion contexts are not reconstructed.  This is deliberately weaker than
symbolic execution.

## 5. Results

| Metric | normal | p2test |
|---|---:|---:|
| Direct call edges | 1 489 | 1 371 |
| Return blocks | 243 | 250 |
| Function summaries | 432 | 403 |
| Direct argument records | 146 | 116 |
| Proven direct arguments | 25 | 10 |
| Newly resolved accesses | 115 | 165 |
| Stateful blocks | 750 | 894 |

Examples:

- `0x28a62 -> 0x289b0`, pair `r3:r2 = 0x00ff4000`;
- `0x714 -> 0x028d3c`, pair `r3:r2 = 0x00010842`;
- `0x812 -> 0x001196`, pair `r8:r7 = 0x00010a78`.

The first proves the mechanism reaches a peripheral address, but it is not a
PCM/slot-5 address.  The others resolve data/table cells.  No direct-call
argument was proven to select a slot-5 control word.

## 6. Tests

`tools/tests/test_cr16_dataflow.py` now checks:

- direct-call metadata is present;
- the normal run converges;
- a forced `max_iters=1` run is `NON_CONVERGED`;
- forced non-convergence cannot mark new rows `PROVEN`.

`tools/tests/test_cr16_interproc.py` checks the summary/report counts, that
table candidates are not promoted, and that no IRQ handler is named PCM.

## 7. Remaining limits

- no stack argument model;
- no return-value summary;
- indirect calls are whole-register clobbers;
- function boundaries are intraprocedural approximations;
- data decoded as code can still inflate summaries;
- recursion and context explosion are deliberately capped by the direct-call
  model rather than solved.
