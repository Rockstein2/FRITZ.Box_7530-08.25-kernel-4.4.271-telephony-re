# FON-E2 — IRQ/vector callgraph

> **Status: offline callgraph.**  No IRQ was asserted and no firmware ran.
> Report: `tools/reports/cr16-irq-paths.json`.

## 1. Method

The vector table at `INTBASE = 0x24` has 31 entries.  For every in-image
handler E2 records:

```text
vector entry -> handler -> direct calls -> memory reads/writes
             -> return path
```

The handler summary uses the same conservative `reads_before_write` /
`written` model as the interprocedural report.  An indirect callback is a
whole-register clobber.  The report does not infer a frequency unless the
code itself proves one.

## 2. Handlers with resolved memory operations

| Vector | normal | p2test | Resolved operations |
|---|---|---|---|
| `tim1_int` | `0x028996` | `0x02772a` | `0x2b6` counter read/write; `0xF5402 = 0x100` |
| `dip_int` | `0x028cd0` | `0x027c88` | `0x93c9` counter; **read `0xF6006`**; **write `0xF5402 = 0x400`** |
| `dsp_int` | `0x028a94` | `0x027914` | `0x93cb` counter; symbolic `(r1,r0)+...`; calls `0x28aee`, `0x28af6` |

Both images have the same three handler shapes.  Addresses differ, but the
read-`0xF6006` / write-`0xF5402` sequence in `dip_int` is structurally
equivalent.

The `dsp_int` path also contains indexed accesses and two direct callees
(`0x028aee`/`0x028af6` normal, `0x02796e`/`0x027976` p2test).  Those callees
are not named PCM; the indexed accesses remain symbolic.

## 3. What is not proven

- `dip_int` is not proven to be a PCM handler merely because it touches
  `0xF6006`/`0xF5402`.
- No handler computes an 8 kHz period.  The IRQ source clock and the
  relationship to the TDM frame are not recovered.
- No handler has a proven indirect callback.
- No RAM queue or FIFO consumer is linked to the slot-5 control word.
- The `0xFF4000` argument is not `0xFF6006` and is not an alias proof.

## 4. Normal/p2test comparison

| Metric | normal | p2test |
|---|---:|---:|
| Vectors | 31 | 31 |
| Handlers with memory operations | 3 | 3 |
| Handlers with direct calls | 2 | 2 |
| Indirect IRQ callbacks | 0 | 0 |
| PCM-named handlers | 0 | 0 |

This is a structural match, not a functional identification of the FON
handler.

## 5. Next useful check

A future offline step should follow the indexed `dsp_int` accesses and the
direct callees of `dip_int` across function boundaries.  A hardware trace
would still be required to prove the actual interrupt source and cadence;
none is authorized here.
