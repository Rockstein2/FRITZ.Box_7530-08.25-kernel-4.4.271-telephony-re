# FON-E3 summary — CR16 soundness audit and focused DSP/PCM trace

> **Status: offline research completed to a new evidence boundary.**
> No router, firmware execution, MMIO, DMA, reset, UART or ringing occurred.
> K1/K2 remain **NO-GO**.

> **E3.2 correction:** abs20 fields above `0xEFFFF` expand to `0x00FFxxxx`
> on CR16Cplus.  Thus the old `0x000F6006` / `0x000F5402` / `0x000F6002`
> labels are encoded operands, not separate effective addresses.  See
> `fon-e32-summary.md` and `history/fon-e32-q57-investigation.md`.

## 1. What E3 changed

E3 does not run another broad immediate/table scan.  It first audits the E2
interprocedural claims, then follows the two known IRQ handlers backwards to
their data sources and forwards to their memory sinks.

New tool:

- `tools/cr16_e3.py` — E2-proof audit, focused `dsp_int`/`dip_int` traces,
  call-site audit and slot-5 candidate boundary.

Corrected tools:

- `tools/cr16_interproc.py` — path-sensitive may-write analysis, per-use
  preservation proofs, corrected IRQ indirect count, transitive IRQ callgraph,
  and table candidates that require a def-use link to the indirect register.
- `tools/cr16_dataflow.py` — `NON_CONVERGED` now returns a non-zero exit code,
  writes only an `.incomplete.json` diagnostic and does not overwrite the last
  confirmed report.
- `tools/cr16_peripheral_xrefs.py` — immediate `addd/subd` pair forms are now
  modelled for the focused pointer/offset arithmetic.

## 2. E3-A — E2 PROVEN audit

E2 reported 25 normal / 10 p2test PROVEN direct arguments.  E3 re-ran each one
with the per-use path criterion.

| Image | E2 PROVEN audited | still PROVEN | downgraded to CANDIDATE | INVALID |
|---|---:|---:|---:|---:|
| normal | 25 | 11 | 3 | 11 |
| p2test | 10 | 3 | 2 | 5 |

Changed/removed old uses include `0x000714`, `0x000812`, `0x0008a6`, `0x00093a`, `0x0009ce`, `0x000a62`, `0x002f44`, `0x003a1e`, `0x0224a6`, `0x0228ba`, `0x0261fa` normal; `0x000660`, `0x0006fe`, `0x00079c`, `0x020414`, `0x027138` p2test.  Reasons are incomplete caller
entry/path or a possible callee write before the use.  The stricter audit now
matches instruction address, effective address, operation and known
displacement.  It also removed false E2 memory uses that were actually
`movd (pair),(pair)` register moves; those records become `INVALID`.  Full
instruction-level records are in `cr16-e3-soundness-audit.json` and
`cr16-e3-callsite-audit.json`.

The new analyzer reports **43 normal / 22 p2test** `PROVEN` records under its
explicit criterion, plus 58/69 `CANDIDATE`.  This is not a re-labeling of the
old set: a callee that writes a pair **after** the memory use no longer makes
the argument unprovable, while a possible write **before** the use still does.

The priority control case remains valid:

```text
normal: 0x028a62 -> 0x0289b0, r3:r2 = 0x00ff4000
        definition 0x028a5c, call 0x028a62
        callee reads/writes 0x00ff4000 at 0x0289b0/0x028a48
        no clobber on any modelled path to the use
p2test: 0x009fca -> 0x009f18, same pair/value shape
```

`0x00ff4000` is a peripheral address in that proof, but it is **not** a slot-5
PCM register and is not renamed PCM.

## 3. E3-A — convergence and entry completeness

The per-function may-write analysis marks:

- a function entry inside a basic block as `INFERRED_MID_BLOCK`;
- an external predecessor into a non-entry block as potentially all-register
  clobbered;
- a non-converged function analysis as incomplete.

Only `CONFIRMED_BLOCK_START`, complete-path functions can contribute a
`PROVEN` argument.  A missing CFG predecessor is never treated as proof of a
single path.

`cr16_dataflow.py --max-iterations 1` now exits **1**, creates
`cr16-dataflow-*.incomplete.json`, and leaves the last confirmed JSON
untouched.  `cr16_interproc.py` and `cr16_e3.py` use the same fail-closed
pattern: on `NON_CONVERGED` they write only `*.incomplete.json` and do not
promote the normal reports.  This is covered by regression tests.

## 4. E3-B — table and IRQ reporting corrections

The E2 table report claimed 16/20/24/32-bit widths and both endian orders.
That was not implemented.  E3 removes the claim:

- no table entry width, stride, index bound or endianness is decoded;
- a candidate now requires a def-use link from a nearby load to the register
  actually consumed by the indirect instruction **and** no nearer write that
  clobbers that register;
- the nearby loads observed in the linked candidates are 32-bit accesses, but
  that is not a table-entry width;
- a link alone is still only `CANDIDATE`; no full consumer chain is proven.

Results:

| Image | Indirect sites | `CANDIDATE` | `UNRESOLVED` | `PROVEN` |
|---|---:|---:|---:|---:|
| normal | 382 | 0 | 382 | 0 |
| p2test | 396 | 11 | 385 | 0 |

The E2 `irq_paths()` bug was fixed: the IRQ report now reads
`possible_call_targets.indirect_sites` and the value is cross-checked against
the function summary.  Both images have **0** indirect IRQ callbacks in the
current model.  A transitive callgraph is now included per vector, keeping the
handler's own memory operations separate from nested callees.

## 5. E3-C — `dsp_int`

`dsp_int` is at `0x028a94` normal / `0x027914` p2test.

The data source is:

```text
loadd 0xD6 -> pointer 0x01027F80 (static image value)
addd 0x58 -> 0x01027FD8
loadw/storw 0x0 at that pointer
```

Important correction to E2: the apparent fields `+0`, `+0x0e`, `+0x10` do
**not** share one base.  The first is `0xD6` pointer + `0x58`; the counters are
at:

- normal: `0x2C4 + 0x0e = 0x2D2`, `0x2C4 + 0x10 = 0x2D4`;
- p2test: `0x224 + 0x0e = 0x232`, `0x224 + 0x10 = 0x234`.

Other observed operations:

- byte flag at `0x93CB` normal / `0x9512` p2test;
- bit set at `0x93C8` normal / `0x950E` p2test;
- event bits 2 and 3 invoke helpers;
- normal helpers `0x3B28` and `0x3B38`;
- p2test helpers `0x27744` and `0x27754`;
- `0x00FF5402 = 0x2000` acknowledgement candidate (encoded abs20 form
  `0x000F5402`).

`dsp_int` is classified **DSP_EVENT_OR_SOFTWARE_QUEUE_CANDIDATE** in the
standalone E3 report.  The SC14480 datasheet raises this to a stronger
related-device hypothesis: `0x01027FD8` is **`DSP_INT_REG`**, a write-one-to-
clear Gen2DSP vector register (printed p177).  That explains the read/test/
write shape, but does not prove SC14448 identity.  The `dsp_int` helpers and
the `0xD6` runtime writers remain unresolved.  No TDM/slot-5 source is proven;
it is not named PCM.

## 6. E3-D — `dip_int`

`dip_int` is at `0x028cd0` normal / `0x027c88` p2test.

Observed flow:

```text
loadw encoded 0xF6006 -> r0   ; effective 0x00FF6006
movb r0,r2          ; only the low byte is kept
movw 0x400,r0       ; r0 is overwritten
storw r0,encoded 0xF5402     ; effective 0x00FF5402, write 0x0400
bal callee          ; callee receives r2 as an input
```

Normal callee: `0x028732`; p2test callee: `0x025d74`.  The normal callee is a
small table/event routine; the p2test callee is a much larger routine.  Their
structural equivalence is not proven, so E3 does not describe them as the same
handler body.

The E3.2 address-extension result removes the old address-space conflict:
encoded `0xF6006` expands to effective `0x00FF6006`, so the read and the
`0x00FF6006` pulse reach the same architectural address.  The polled encoded
`0xF6002` path (`0x25FAE` normal / `0x26764` p2test) expands to
`0x00FF6002`; it remains a separate candidate because the full pulse → poll →
read → acknowledgement sequence is **not proven**.

`dip_int` is classified **EVENT_STATUS_ACK_CANDIDATE**.  SC14480 printed
p196–197 gives `0x00FF5402` `RESET_INT_PENDING_REG` with bit 10 `DIP_INT_PEND`
and bit 13 `DSP_INT_PEND`, which matches the `0x0400`/`0x2000` values
semantically.  E3 printed the write as **`0x000F5402`**, but that is the
encoded abs20 field; E3.2 expands it to effective **`0x00FF5402`**.  The
address-space conflict is therefore resolved; the physical register identity
remains `CANDIDATE_RELATED_DEVICE_MAP`.  `dip_int` is not a proven slot-5 or
PCM consumer, and no 8 kHz period is claimed.

## 7. E3-E — `0x01000000`

The 511 writes are **one static indexed store** executed over 511 iterations,
not 511 distinct static instructions:

```text
normal:  control 0x25F90, store 0x25D0, iterations 1…511
p2test: control 0x26750, store 0x1E8C, iterations 1…511
base:    0x01000000 + 2*index
```

`0x01000000` is outside the 24-bit range (`0xFFFFFF` maximum).  Its effective
address-space/bank mechanism is **UNRESOLVED**; it is not automatically a
normal 24-bit absolute address.  The DIP payload `0x1001` is `01 10`; in
SC14480 Table 10, little-endian reads as `BR` and big-endian as `BR_B0`, so
either byte order is a branch, but the parameter/target and validity are
still unproved.

The `dsp_int` pointer target is `0x01027FD8`, outside the 511-word fill range
`0x01000002…0x010003FE`.  Thus the region contains at least two distinct
address ranges: a fill/init range and a pointer/state candidate.  Neither is
proven to be a PCM buffer.

SC14480 printed p131–132 gives a much stronger related-device hypothesis:
`0x01000000–0x010003FF` is 512×16 **DIP Sequencer RAM**, and execution starts
at `0x01000002`.  The E3 fill range exactly starts at that second word.  The
payload is constant `0x1001`; its DIP opcode/byte order is not decoded, so the
loop is a **DIP-RAM fill candidate**, not a proven valid DIP program.

Classification: **`UNRESOLVED`** for the region as a whole, with
`DIP_RAM_FILL_CANDIDATE` for the 511-word range and
`STATIC_POINTER_CANDIDATE` for the `0xD6`/`DSP_INT_REG` target.  It is not a
PCM buffer.

## 8. E3-F — slot-5 handler boundary

No slot-5 consumer was found.  The focused runtime paths do not establish a
source-to-sink chain for the Linux control word.

Remaining concrete unknowns:

1. writers/runtime relocation of the `0xD6` pointer cell;
2. source and semantics of the 16-bit event word at pointer+0x58;
3. bit-level meaning and read-to-clear behavior of `0x00FF6006`;
4. callee event-code processing (normal and p2test differ in size);
5. 382/385 unresolved indirect sites;
6. indexed accesses in `dsp_int`/callees;
7. stack-passed arguments;
8. address-space/bank mechanism for `0x01000000`.

This is a bounded negative result, not a complete-image proof of absence.

## 9. Q status

| Q | Status after E3 |
|---|---|
| Q16 TX slot-5 | Linux mapping complete; SC14448 side **open** |
| Q17 RX slot-5 | Linux mapping complete; physical bits **open** |
| Q40 `0x2558` dispatch key | **open**; fill/init path identified, dispatch key not proven |
| Q46 `0x01000000` | **open**: SC14480 makes DIP RAM the leading hypothesis; payload `0x1001` undecoded; not PCM |
| Q53 unreachable code | **open**; call paths improved, indirect/data ambiguity remains |
| Q54 indirect dispatcher | **open**; 0 proven targets, 0/11 linked candidates after kill check |
| Q55 symbolic store/read | **open**; pointer from `0xD6` found; DIP-RAM fill candidate, reader/payload still unresolved |
| Q44 / Q57 address translation | **address-space part closed by E3.2**: abs20 fields above `0xEFFFF` expand to `0x00FFxxxx`; physical SC14448 register identity remains CANDIDATE |
| Q74 EOR #2 | **partial**: raw/audio model; physical wire order open |
| Q75 firmware slot-5 consumer | **open**: no proven handler |

## 10. Tests

All offline checks passed:

- `python3 tools/tests/test_cr16_dataflow.py` — 0 failures/skips;
- `python3 tools/tests/test_cr16_interproc.py` — 0 failures/skips;
- `python3 tools/tests/test_cr16_e3.py` — 0 failures/skips;
- `python3 tools/tests/test_cr16_address_spaces.py` — 0 failures/skips;
- `python3 tools/tests/test_docs_consistency.py` — 0 failures/skips;
- `make -C tools/fon-slot5-protocol test` — 0 failures;
- all CR16 regression tests — 0 failures;
- `sh tools/verify-workspace.sh` — 64 passed, 0 failed;
- `git diff --check` — clean;
- E3 report reproducibility — replay matches the committed JSON;
- E3.2 address reports replay from raw firmware bytes and the CR16 oracle.

No hardware action was authorized or performed.
