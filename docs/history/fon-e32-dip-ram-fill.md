# E3.2 history — DIP RAM fill and payload `0x1001`

> **Status: offline analysis only.**  No DIP sequencer was started or touched.

## 1. What the firmware does

Both images execute one static indexed store 511 times:

| Image | Control | Store | Range | Payload |
|---|---|---|---|---|
| normal | `0x25F90` | `0x25D0` | `0x01000002…0x010003FE` | `0x1001` |
| p2test | `0x26750` | `0x1E8C` | `0x01000002…0x010003FE` | `0x1001` |

The store is `storw r2,0x0:s(r5,r4)` after a base/index setup; it is not 511
distinct instructions.  The range is 511 words, matching the SC14480 DIP
Sequencer RAM rule that execution starts at `0x01000002` (the second word).

## 2. SC14480 DIP opcode evidence

SC14480 printed pages 35–38, Table 10, list:

| Opcode | Command |
|---:|---|
| `0x01` | `BR` — branch always |
| `0x10` | `BR_B0` — branch to bank 0 |
| `0x11` | `BR_B1` — branch to bank 1 |
| `0x12` | `JMPF` — jump far to bank 1 |
| `0x14` | `RTNF` — return far to bank 0 |

`0x1001` has bytes `01 10`:

| Byte order | Opcode | Parameter | Interpretation |
|---|---|---|---|
| little-endian | `0x01` | `0x10` | `BR` |
| big-endian | `0x10` | `0x01` | `BR_B0` |

Both readings are branches.  This is stronger than the earlier “maybe BR”
note, but it is still not a valid-program proof:

- the DIP instruction width/byte order is not stated for the payload;
- the branch parameter/target is not decoded;
- 511 identical branch words could be an idle/loop fill;
- no SC14448 DIP RAM identity or execution was observed.

## 3. Classification

The range remains:

```text
DIP_RAM_FILL_CANDIDATE
```

not `PCM buffer` and not `proven DIP program`.  The fill range is distinct
from the `0xD6` pointer target `0x01027FD8` (`DSP_INT_REG` candidate), so the
region has at least two separate uses.

Reports: `tools/reports/cr16-dip-ram-fill.json`.
