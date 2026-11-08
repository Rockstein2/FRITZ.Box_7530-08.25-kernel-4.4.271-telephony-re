# FON-E1 — PCM handler candidates

> **Status: bounded negative result.**  Report:
> `tools/reports/cr16-pcm-candidates.json`.

---

## 1. Candidate peripheral accesses

The resolved PCM-adjacent list is unchanged from E0: **34 accesses in normal
and 34 in p2test**.  They are the `0x000F6002`, `0x000F6006`, `0x00FF6006`,
`0x000F6400/6402` and `0x000F5402/5404/5406/5408/540A` sites.

No E1 cross-block resolution added a slot-5 buffer or a 16-bit PCM data
read/write outside this set.  In particular:

- no `loadw`/`storw` to a slot-indexed buffer was resolved as a constant;
- no new access in `0x000F60xx`/`0x00FF60xx`;
- no `0x4000`/`0x5555` immediate was found;
- the `0x8000` immediates remain in the `0x00116xx` data/table region.

## 2. Candidate regions

| Region | Writers | Readers | Interpretation |
|---|---|---|---|
| `0x01000000 + 2*index` | 511 sequential 16-bit writes | no resolved reader | loader/copy/initialisation **or** runtime buffer; **not named PCM** |
| `0x00108xx` | `0xFEFE`, `0x7FFF` writes | some cross-block reads | data/table candidate |
| `0x00116xx` | `0x8000` writes | none proven | data/table candidate |
| `0x000F6002` | none resolved | one polled read | status/poll candidate |
| `0x000F6006` | two `0x80` writers | two readers | control/status candidate |
| `0x00FF6006` | pulse `0x80`, clear `0` | discarded read | pulse candidate |
| `0x000F6400/6402` | reset path writes | none resolved | unknown control |
| `0x000F5402` | multiple values | none resolved | interrupt/control candidate |

`0x01000000` is a **SC14448 address**, unrelated to the IPQ4019 TLMM address
of the same number.

## 3. Handler-shaped patterns

The dataflow searched for the sequence:

```text
load 16-bit word -> mask/shift/branch -> store to peripheral/data -> status assembly
```

It found no complete path.  The closest resolved structures are ordinary
dataflow into RAM cells, not a periodic PCM consumer.  This remains a
**negative result**, not proof that no handler exists.

## 4. Q46/Q55

- The 511 writes are not linked to a resolved reader.
- The base is not proven to survive across a call or table.
- The writes may be loader/copy/initialisation.
- No periodic 8 kHz indexing was recovered.
- Do not call the region a PCM buffer.

## 5. Remaining paths

1. cross-call register passing (E1 kills state at calls);
2. table/vector dispatch, reported as unresolved;
3. indexed `r12/r13` accesses (kept symbolic, not constant);
4. data misidentified as code (flagged out-of-range);
5. an IRQ handler that reads a hardware FIFO rather than a RAM buffer.
