# E5-D — CODEC initialization evidence

> **Status: historical analysis; current summary is `../sc14448-e5-summary.md`.**
> Static, offline. Report: `tools/reports/cr16-e5-codec-init.json`.

Part 1 (normal `0x11CE` / p2test `0x0C44`), reached from main via
`0x3A10→0x131C` / `0x2712A→0x0D92` (gated by flag byte bit0). Part 2
(normal `0x12EA` / p2test `0x0D60`) continues with GPIO direction,
`0xFF4974/0xFF4976 = 0x47` and `0xFF4970` bit0.

## CODEC analog writes (SC14480 analogy names)

`0x00FF5804` CODEC_VREF_REG, in order:

1. `cbitw 7` — BIAS_PD=0 (bias on);
2. `(andw 0xFFF3 | 4)` — VREF_FILT_CADJ=01, VREF_INIT=1 (precharge);
3. `cbitw 8, 9, 6, 5, 1, 0`, `sbitw 4` — AGND_LSR, REFINT, bandgap,
   1.5 V converter, filter, VREFp all powered on, precharge kept;
4. delay loop, `0x7D0` (2000) iterations (`0x1272`/`0x0CE8`);
5. MIC and LSR amplifiers enabled afterwards.

This matches the SC14480 note-57 recommended order (bias → VREF_INIT=1
precharge → wait ≥100 µs → VREF_INIT=0 → MIC amplifier on → AD/DA on):
the runtime enable (`0x190E`/`0x1390`) later clears VREF_INIT (`cbitw 4`
on `0xFF5804`) and powers the converters.

`0x00FF5800` CODEC_MIC_REG: `orw 1` (MIC_MODE=01, single-ended MICp),
`cbitw 3` (MIC_MUTE=0), `andw 0xFF0F` (MIC_GAIN=0000, 0 dB), `cbitw
8,9,A,B` (offset-comp/test off, gain via MIC_GAIN not DSP, MICn input),
`(andw r1 | 0x1000)` with r1=0xCFFF (MIC_CADJ=00), `cbitw 2` (MIC_PD=0,
amplifier on).

`0x00FF5802` CODEC_LSR_REG: `orw 0x1C0` (LSRATT=111, −12 dB, Table 113),
`(andw 0xFFFC | 2)` (LSRP_MODE=10, differential DA+), `(andw 0xFFE7 |
0x10)` (LSRN_MODE=10, differential DA−), `cbitw 5, 9, 2` (LSRN_PD=0,
LSREN_SE=0, LSRP_PD=0), `(andw 0xFE3F | 0x40)` (**LSRATT=001 → 0 dB
nominal**, Table 299 level at 0 dBm0 — the E5 text «+2 dB» was wrong and
is corrected).

`0x00FF5806` CODEC_TONE_REG: `sbitw 3` (RNG_PR_DIS=1, RING protection
diodes disabled) in part 1; `sbitw 1` (CID_PR_DIS=1) in the pad init —
consistent with VREFp being enabled (reference note 56).

`0x00FF5808` CODEC_ADDA_REG: `orw 3` during DSP init (AD_PD=1, DA_PD=1,
converters down) and `andw 0x7FFC` during runtime enable (AD_PD=0,
DA_PD=0, converters on) — a proved powerdown/powerup pair.

`0x00FF580C` CODEC_TEST_CTRL_REG: `sbitw 12` (COR_ON=1, digital offset
compensation); when CLK_DA_LSR_SEL == 11 the enable path sets MIC_MUTE
(`orw 8` on `0xFF5800`), spins on bit13 (COR_STAT), then copies
`0x00FF580A` (OFFSET1) → `0x00FF580E` (OFFSET2).

## GPIO/pad sites

`0xFF481E` PAD_CTRL (bit2 conditional on helper result, bits 5/4),
`0xFF4856/58` GPIO2 dir/mode (`0x550` patch), `0xFF4860/66/68` GPIO3
dir/mode, `0xFF4836/38` (part 2), `0xFF4808` (pad init), `0xFF4812`.

## What is NOT proven

Converter/amplifier configuration is instruction-proven; that no audio
actually flows (no PCM↔DSP↔CODEC sample path is verifiable offline) and
that the RING/TONE bits map to SC14448 pins the same way are not. Analog
line control (FON) remains unreached by any proved command path.
