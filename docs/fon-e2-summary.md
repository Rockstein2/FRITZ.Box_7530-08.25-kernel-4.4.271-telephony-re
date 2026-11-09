# FON-E2 summary — interprocedural CR16 analysis, indirect dispatch and IRQ paths

> **Status: offline research completed to a new evidence boundary.**
> No router, firmware execution, MMIO, DMA, reset or ringing was performed.
> K1/K2 remain **NO-GO**.

## 1. What changed

E1 stopped dataflow at every call.  E2 restores the call continuation, adds a
limited interprocedural summary layer, and examines indirect/table consumers,
IRQ vectors, indexed accesses and the `0x01000000` writer.

New tool:

- `tools/cr16_interproc.py` — function summaries, direct argument
  propagation, table-consumer candidates and IRQ callgraphs.

Updated tool:

- `tools/cr16_dataflow.py` — direct call → callee and call → continuation
  edges, explicit fixed-point status, and a forced-cap diagnostic.  A
  non-converged run now reports `NON_CONVERGED` and marks every new
  `RESOLVED` row as `CANDIDATE`, never `PROVEN`.

New reports:

- `tools/reports/cr16-interproc-normal.json`
- `tools/reports/cr16-interproc-p2test.json`
- `tools/reports/cr16-table-dispatch.json`
- `tools/reports/cr16-irq-paths.json`
- `tools/reports/cr16-fon-handler-candidates.json`

## 2. E2-A — CFG and convergence

`blocks_and_successors()` now adds a direct call's callee entry **and** its
continuation after return.  A `RETS` block has no normal successor.  The
state transfer at a call still clears caller state; continuation coverage is
therefore restored without pretending that the call preserves registers.
This is a conservative call/return CFG, not a stack-sensitive return matcher
and not a proof that every callee returns.

The fixed-point loop is capped at 1 000 iterations.  If the cap is reached:

- `analysis_status` is `NON_CONVERGED`;
- `converged` is `false`;
- the iteration count and maximum are recorded;
- newly resolved rows are labelled `CANDIDATE`.

A regression test forces `max_iters=1` and verifies that the corpus is not
reported as converged.  Normal execution converges in four iterations.

## 3. Metrics

| Metric | normal | p2test |
|---|---:|---:|
| Decoded blocks | 5 454 | 5 170 |
| Direct call edges | 1 489 | 1 371 |
| Return blocks | 243 | 250 |
| Stateful blocks | 750 | 894 |
| Newly resolved accesses | 115 | 165 |
| Outside known internal ranges | 10 | 3 |
| Fixed-point status | CONVERGED | CONVERGED |
| Iterations | 4 | 4 |
| Indirect edges | 382 | 396 |
| Table-dispatch candidates (E3-corrected) | 6 | 17 |
| Table-dispatch unresolved (E3-corrected) | 376 | 379 |
| Function entries with summaries | 432 | 403 |
| E2 initial direct argument records | 146 | 116 |
| E2 initial PROVEN call arguments (audited in E3) | 25 | 10 |
| E3 corrected direct argument records | 173 | 134 |
| E3 corrected PROVEN call arguments | 91 | 42 |
| E3 retained old PROVEN arguments | 21 | 8 |
| IRQ vectors | 31 | 31 |

The E1 cross-block counts changed slightly because the restored call
continuation adds blocks: **115/165** new resolved accesses and **750/894**
stateful blocks now replace the earlier 119/171 and 777/916.  The earlier
values were not silently retained.

## 4. E2-B — interprocedural summaries

A summary records:

- blocks reachable inside the function;
- registers read before a proven write;
- registers written, including a whole-register clobber for an indirect call;
- direct call sites;
- return blocks;
- memory operations with their existing provenance;
- indirect sites.

The direct-call analysis propagates a constant only when:

1. the caller writes a register pair immediately before the call;
2. the callee reads both pair members before a proven write;
3. the callee uses the pair in a constant-displacement memory operand.

If the callee writes either pair member anywhere, the result is downgraded to
`CANDIDATE`.  Indirect and unknown calls clobber all registers.  Register-list
memory forms (`loadm`, `loadmp`, `storm`, `stormp`) are not decoded and are
treated as a whole-register clobber, so they cannot promote an argument.
Stack-passed arguments and return values are **not** reconstructed.

Examples of proven direct-call propagation:

| Image | Call site | Callee | Pair | Constant |
|---|---|---|---|---:|
| normal | `0x28a62` | `0x289b0` | `r3:r2` | `0x00ff4000` |
| normal | `0x714` | `0x028d3c` | `r3:r2` | `0x00010842` |
| normal | `0x812` | `0x001196` | `r8:r7` | `0x00010a78` |
| p2test | `0x9fca` | `0x009f18` | `r3:r2` | `0x00ff4000` |
| p2test | `0x660` | `0x000c0a` | `r8:r7` | `0x00010a6c` |

The `0x00ff4000` case proves that the mechanism works for a peripheral
address, but `0x00ff4000` is not a slot-5 PCM register and is not renamed
PCM here.  Most other proven arguments land in data/table regions.

## 5. E2-C — table-aware indirect dispatch

E2 applies a stricter criterion than E1's address-word matches.  A target is
`PROVEN` only with a complete chain:

```text
table base -> index/offset -> table load -> address transform
           -> indirect call/jump -> valid instruction boundary
```

The report records the indirect site, nearest preceding table-like load,
entry width, index bounds, consumer reason, provenance and confidence.

Result:

E2 initially reported 87/78 candidates and 295/318 unresolved sites.  E3's
stricter def-use check corrects this to:

- normal: 382 indirect sites; 6 `CANDIDATE`, 376 `UNRESOLVED`, **0 PROVEN**;
- p2test: 396 indirect sites; 17 `CANDIDATE`, 379 `UNRESOLVED`, **0 PROVEN**.

The 5 639/5 668 16-bit address-like words from E1 remain a raw candidate set.
They are not promoted by a normal/p2test address coincidence, and no
runtime-initialised dispatch table was proven.

## 6. E2-D — IRQ callgraph

Both images have 31 vector entries.  Three handlers contain memory accesses:

| Vector | normal | p2test | Observed accesses |
|---|---|---|---|
| `tim1_int` | `0x028996` | `0x02772a` | counter read/write; `0xF5402 = 0x100` |
| `dip_int` | `0x028cd0` | `0x027c88` | counter; **read `0xF6006`**; **write `0xF5402 = 0x400`** |
| `dsp_int` | `0x028a94` | `0x027914` | counter; symbolic indexed accesses; calls two helpers |

`dip_int` is the closest IRQ candidate: it reads `0xF6006` and writes
`0xF5402`, the same control/status neighborhood seen in the polled path.  It
does **not** prove a slot-5 consumer.  No vector has an indirect callback in
this report, and no handler computes an 8 kHz cadence.  No handler is named
`PCM` or `slot 5`.

The other vector entries are either stubs (`nop; retx`), have no resolved
memory operation, or remain limited by the same indirect/data ambiguity.

## 7. E2-E — indexed accesses

E1's indexed categories remain:

| Image | READ/INDEXED | WRITE/INDEXED | RMW/INDEXED |
|---|---:|---:|---:|
| normal | 249 | 280 | 20 |
| p2test | 195 | 186 | 15 |

E2 did not promote any of these to a single chosen address.  They remain
`SYMBOLIC` or `UNKNOWN`; `BOUNDED_RANGE` is not claimed without proven loop
bounds and table stride.  The priority set for the next stage is the indexed
accesses inside `dsp_int` and the unresolved callers of the `0x01000000`
writer.

## 8. E2-F — `0x01000000`

The 511 indexed writes at `0x01000000 + 2*index` remain:

- a resolved **writer** path;
- without a resolved reader;
- without a proven runtime lifetime;
- without a call/return proof that the base survives into a PCM consumer.

E2 classifies the region as `LOADER_OR_RAM_INIT_CANDIDATE`, with its runtime
role still `UNKNOWN`.  It is **not** named a PCM buffer.  The exact missing
fact is a resolved reader (direct or indexed) and a periodic relation to the
TDM/PCM control word.

## 9. E2-H — EOR #2 scope and audio slots

The ARM `EOR #2` model is confirmed for the directly decoded halfword stores
and reads in `TxDMA`/`PutRxDMA`.  The separate `generic_slotinterleave` path
also uses `EOR #2` for its audio-slot stores, so the same raw adjacent-pair
swap applies to the audio words too.

What this does **not** prove:

- the physical wire order;
- the sample packing/endianness inside an audio halfword;
- whether the receive path has the same sample order as transmit.

The library raw API is therefore still a **raw memory model**, not a
physical-wire specification.  `fon_slot5_frame_to_raw(buf, buf)` and
`fon_slot5_raw_to_frame(buf, buf)` now support in-place operation through
temporary variables; a golden test covers the overlap case.

## 10. E2-G — slot-5 handler search

No slot-5 consumer was proven.  E2 expanded coverage compared with E1:

- call continuations are now reachable;
- 146/116 E2 direct-call argument records were examined; E3 records 173/134;
- 382/396 indirect sites were tied to their nearest table-like consumer;
- all 31 IRQ vectors were reconstructed in both images;
- indexed accesses in the IRQ path were inspected;
- `0x01000000` was traced only to its writer.

Remaining concrete paths:

1. indirect sites with `UNRESOLVED` targets: 376 normal / 379 p2test;
2. indexed `r12/r13` accesses: 549 normal / 396 p2test, mostly symbolic;
3. IRQ handlers that may read a hardware FIFO instead of RAM;
4. stack-passed arguments not modelled by E2;
5. data/code ambiguity outside the loaded ranges.

This is a bounded negative result, not proof that no handler exists.

## 11. Q status

| Q | Status after E2 |
|---|---|
| Q16 TX slot-5 | Linux mapping complete; SC14448 side **open** |
| Q17 RX slot-5 | Linux mapping complete; physical bits **open** |
| Q46 `0x01000000` | **open**: loader/RAM-init candidate; no reader |
| Q53 unreachable code | **open**; call continuations covered, indirect/data ambiguity remains |
| Q54 indirect dispatcher | **open**; 0 proven targets |
| Q55 symbolic store/read | **open**; no resolved reader |
| Q57 address aliases | **open**; no new proof |
| Q74 EOR #2 | **partial**: raw memory and audio pair-swap model; physical wire order open |
| Q75 firmware slot-5 consumer | **open**: no proven handler |

## 12. Commands and reproducibility

```sh
python3 tools/cr16_dataflow.py --objdump /tmp/opencode/cr16/build/binutils/objdump
python3 tools/cr16_interproc.py --objdump /tmp/opencode/cr16/build/binutils/objdump
python3 tools/tests/test_cr16_dataflow.py
python3 tools/tests/test_cr16_interproc.py
```

The reports include the firmware source path, SHA256, tool version, CFG
counts, unresolved edges, provenance and limitations.  The tool does not
write to hardware and does not load a kernel module.
