# FON-E1 summary — cross-block CR16 dataflow and indirect PCM search

> **Status: offline research completed to a new evidence boundary.**
> No router or firmware execution was performed.

## 1. New tooling

- `tools/cr16_dataflow.py`: conservative CFG fixed-point scan with
  cross-block register/pair constants, exact-agreement joins, provenance, and
  call/indirect state kills.  E2 added call-continuation edges and an explicit
  convergence status; see `fon-e2-summary.md`.
- Reports:
  - `tools/reports/cr16-dataflow-normal.json`
  - `tools/reports/cr16-dataflow-p2test.json`
  - `tools/reports/cr16-indirect-candidates.json`
  - `tools/reports/cr16-pcm-candidates.json`
- `tools/fon-slot5-protocol` now has a separate raw-DMA transformation:
  `fon_slot5_frame_to_raw()` / `fon_slot5_raw_to_frame()`.
- The CR16 oracle was rebuilt offline from the local binutils 2.44 tarball.

## 2. Metrics

| Image | Blocks | Stateful blocks | New resolved | Outside known ranges |
|---|---:|---:|---:|---:|
| normal | 5 454 | 750 | **239** | 10 |
| p2test | 5 170 | 894 | **239** | 3 |

Unknown reduction:

```text
normal: READ/UNKNOWN 1403 -> 1331; WRITE 1205 -> 1175; RMW 204 -> 177
p2test: READ/UNKNOWN 1238 -> 1132; WRITE 1215 -> 1164; RMW 178 -> 163
```

The 10/3 out-of-range rows are flagged as data/code false-positive candidates,
not MMIO.

## 3. EOR #2

The ARM `strh` address XOR 2 is now resolved:

> it swaps adjacent 16-bit slots inside each 32-bit DMA word.

Raw order for logical
`[0, fefe, fefe, fefe, 5555, control, a6, a7]` is
`[fefe, 0, fefe, fefe, control, 5555, a7, a6]`.

The logical slot-5 word is raw index 4 / byte `0x08`.  The raw memory model is
proven; the DMA presentation/physical wire order remains UNKNOWN.

## 4. PCM result

- PCM candidate accesses remain **34 per image**; no new slot-5 buffer or
  peripheral path.
- No `0x4000`/`0x5555` immediate.
- No proven indirect/IRQ dispatcher to a PCM handler.
- 382/396 indirect edges and 5 639/5 668 table-like 16-bit matches remain
  candidates, not proof.
- `0x01000000 + 2*index` still has no resolved reader and is **not** named a
  PCM buffer.

## 5. Q status

| Q | Status |
|---|---|
| Q16 TX slot-5 | Linux mapping complete; SC14448 side **open** |
| Q17 RX slot-5 | Linux mapping complete; physical bits **open** |
| Q46 `0x01000000` | **open**: loader/copy vs runtime buffer not decided |
| Q53 unreachable code | **open**; cross-block coverage improved but not closed |
| Q54 indirect dispatcher | **open**: candidates only |
| Q55 symbolic store/read | **open**; no resolved reader |
| Q57 address aliases | **open**; no new proof |
| Q74 EOR #2 | **partial → raw order resolved; physical wire order open** |
| Q75 firmware slot-5 consumer | **open**: no handler found |

## 6. Honest boundary

E1 increased coverage and resolved the memory-level `EOR #2`, but it did not
find a slot-5 handler.  The remaining paths are:

1. cross-call register passing (calls kill state);
2. table/vector dispatch (candidates only);
3. indexed `r12/r13` accesses;
4. IRQ handlers reading a hardware FIFO rather than a RAM buffer;
5. data/code ambiguity.

The result is a bounded negative result, not proof of absence.
