# FON-E1 — indirect dispatch and table candidates

> **Status: offline candidate report, not proof of execution.**
> No firmware was executed.

Report: `tools/reports/cr16-indirect-candidates.json`.

---

## 1. Indirect edges

The CR16 CFG reports:

| Image | Indirect edges |
|---|---:|
| normal | 382 |
| p2test | 396 |

These are `jalr`, `jump (rp)`, and other register-indirect forms that the
CFG cannot resolve without a value.  They are not automatically entrypoints.

## 2. Table candidates

`cr16_cfg.find_indirect_tables()` scans aligned 16-bit words for values that
match a decoded instruction address:

| Image | 16-bit table-like hits |
|---|---:|
| normal | 5 639 |
| p2test | 5 668 |

This is a **candidate set**, not a function-pointer proof.  A word can be
data, a literal, or a false positive from code bytes.  The report keeps only
the first 200 hits per image, with the note that a match alone is not a
target.

## 3. Vector table

The existing `cr16-vector-map.json` records 31 vector entries at the known
`INTBASE=0x24` table.  E1 did not assign any vector the name `PCM`, `slot 5`,
`DMA` or `PON`.  The known handlers (`tim1_int`, `dip_int`, `dtmp_int`,
`uart_int`) are not linked to a PCM slot-5 consumer.

## 4. Classification

| Class | Count/status |
|---|---|
| PROVEN target | no new proof in E1 |
| CANDIDATE target | table hits; no PCM-specific candidate |
| UNRESOLVED | 382 / 396 indirect edges |

No table hit is promoted to `PROVEN`.  A future step needs:

- table base/stride and index range;
- a branch that consumes the loaded word;
- cross-image topology confirmation.

## 5. Conclusion

No PCM/IRQ dispatcher is proven.  The unresolved indirect paths remain one of
the two main reasons a slot-5 handler could still be missed; the other is the
cross-block/indexed data path.
