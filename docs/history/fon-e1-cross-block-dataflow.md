# FON-E1 — cross-block CR16 dataflow

> **Status: offline analysis.**  No router, firmware execution, MMIO, DMA,
> GPIO, clock, reset or analog line was touched.

Tool: `tools/cr16_dataflow.py`.  It reuses the existing CR16 CFG/disassembler
and the operand helpers from `cr16_peripheral_xrefs.py`.  The CR16 oracle was
rebuilt from the local `binutils-2.44` tarball.

---

## 1. Soundness model

The analysis is deliberately conservative:

- state is keyed by 16-bit register or 32-bit register pair;
- only a **constant** loaded by `movd $imm:l,(rp)` or `movw $imm,rN`, and a
  constant sum from `addd`, are propagated;
- at a CFG join a key survives only when **every** predecessor has the exact
  same value; different constants collapse to UNKNOWN;
- calls clear the state; indirect control flow is not followed;
- memory loads and unknown writes invalidate the destination;
- `DISP_RP` with a known pair is resolved as `pair + displacement`;
- `DISP_R` with a known 16-bit register is resolved; `r12/r13` remain
  INDEXED; `ra` remains PC-relative;
- no symbolic index is converted into a constant;
- every resolved row keeps the defining instruction chain as `provenance`.

The merge is intentionally lossy.  It is not a claim that every surviving
constant is a runtime value; it is a proof that the value is the same on all
modelled paths.

## 2. Metrics

| Image | Blocks | Blocks with entry state | Newly resolved | Outside known ranges |
|---|---:|---:|---:|---:|
| normal | 5 454 | 750 | **115** | 10 |
| p2test | 5 170 | 894 | **165** | 3 |

Comparison with E0:

| Image | `READ/UNKNOWN` | `WRITE/UNKNOWN` | `RMW/UNKNOWN` |
|---|---:|---:|---:|
| normal E0 | 1 403 | 1 205 | 204 |
| normal E1 | **1 331** | **1 175** | **177** |
| p2test E0 | 1 238 | 1 215 | 178 |
| p2test E1 | **1 132** | **1 164** | **163** |

The 10/3 addresses outside the known internal ranges are explicitly flagged
`address outside the known internal range`; they are data/code false-positive
candidates and must not be treated as MMIO.

## 3. Example cross-block result

`0x0010cc` was `UNKNOWN` in E0.  The block at `0x0010b6` establishes:

```text
base = 0x00010800
...
0x0010cc: tbitw 0x0001080e
```

The E1 row is:

```text
instruction 0x0010cc
operation   READ
address     0x0001080e
provenance  0x0010b6
```

This is a real cross-block constant, but it is a **data address**, not a PCM
peripheral.  It shows that the propagation works without turning all indexed
accesses into constants.

## 4. PCM result

The candidate-peripheral list is unchanged: **34 accesses in each image**.
The new resolved rows are data cells, GPIO/interrupt addresses, and the
flagged out-of-range false positives; no new `0x000F60xx`/`0x00FF60xx` slot-5
access appeared.

The cross-block coverage still does not find a firmware consumer of slot 5.
The remaining unknowns are:

- 1 331 `READ/UNKNOWN` and 1 175 `WRITE/UNKNOWN` in normal;
- 1 132 / 1 164 in p2test;
- all indexed `r12/r13` accesses;
- indirect call/table paths (reported separately).

## 5. Q46/Q55 candidate range

The 511 writes to `0x01000000 + 2*index` remain:

- no resolved reader of the range;
- no proof that it is a runtime PCM buffer;
- still consistent with a loader/copy/initialisation region;
- not the same address space as the IPQ4019 TLMM `0x01000000`.

No name "PCM buffer" is assigned.

## 6. Limitations

- calls kill state, so a constant passed in a register to a callee is lost;
- returns are not modelled as value-producing;
- loops converge to the empty join when the back-edge is not constant;
- no full table-value propagation;
- no vector/IRQ entry analysis in this tool;
- data misidentified as code can produce the flagged false positives.

Reports:

```text
tools/reports/cr16-dataflow-normal.json
tools/reports/cr16-dataflow-p2test.json
```
