# FON-E1 — normal vs p2test comparison

> **Status: offline comparison.**  No execution.

---

## 1. Builds

| | normal | p2test |
|---|---|---|
| SHA256 | `7cac33c7…ebab7b31` | `6361384d…dbc4860` |
| Decoded instructions | 19 570 | 18 058 |
| Blocks | 5 454 | 5 170 |
| Blocks with entry state | 750 | 894 |
| Newly resolved | 115 | 165 |
| Outside known ranges | 10 | 3 |
| PCM candidate accesses | 34 | 34 |

## 2. Shifted PCM/control paths

| Function/site | normal | p2test |
|---|---:|---:|
| `0xF6006 = 0x80` writers | `0x1348`, `0x145C` | `0x0DBE`, `0x0ED2` |
| `0xFF6006` pulse | `0x2582`, `0x258C`, `0x25B4` | `0x1E3E`, `0x1E48`, `0x1E70` |
| `0xF6002` poll | `0x25FAE` | `0x26764` |
| `0xF6006` read | `0x2602C`, `0x28CDE` | `0x267E2`, `0x27C96` |
| `0xF5402 = 0x400` | `0x25B0`, `0x26034`, `0x28CE8` | `0x1E6C`, `0x267EA`, `0x27CA0` |

The functional pattern is the same: a polled `0xF6002`, a pulsed
`0xFF6006`, and reads of `0xF6006` near interrupt-controller writes.  The
addresses move; the topology does not gain a slot-5 handler.

## 3. Newly resolved sets

Only 7 effective addresses are common between the two new-resolved sets.
This is expected because the dataflow is layout-sensitive and many resolved
cells are local data.  It is not evidence of a different protocol.

The normal image has 10 out-of-range candidates, p2test 3; these are flagged
as data/code false positives in the reports.

## 4. Conclusion

The equivalent PCM/control topology is present in both images.  E1 therefore
does not find a p2test-only PCM handler.  The remaining gap is the same in
both: unresolved indirect/cross-call/indexed paths.
