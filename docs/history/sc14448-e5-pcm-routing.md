# E5-C — PCM+ configuration and digital routing boundary

> **Status: historical analysis; current summary is `../sc14448-e5-summary.md`.**
> Static, offline. Report: `tools/reports/cr16-e5-pcm-routing.json`.

## DSP_PCM_CTRL composition (normal `0x1468`, p2test `0x0EE4`)

The codec-clock init programs `[0xD6]+0x36` (`0x01027FB6`, DSP_PCM_CTRL_REG
under the SC14480 analogy) with two runtime-selected paths. Selection:
bit0 of a flag byte (`0x93CD` normal / `0x9514` p2test) that the function
itself overwrites with the return value of a hardware/state helper
(`0x3CBE`/`0x278DA` wrapper, `r2=7`); the byte is **not** image-initialized
in either image, so the mode is a runtime decision.

| Path | Bit ops (in firmware order) | Base | Final (FSC0DEL conditional) | Meaning under analogy |
|---|---|---|---|---|
| A (flag bit0=0) | `sbitw 1, sbitw 6`, then clear 7,8,9,15, keep `&0x83FF`, `sbitw 0` | `0x0043` | `0x0043` / `0x0063` | PCM_MASTER=1, PCM_PPOD=1 (open drain), PCM_EN=1 |
| B (flag bit0=1) | `cbitw 1, sbitw 2, cbitw 4,3, sbitw 6`, same tail | `0x0045` | `0x0045` / `0x0065` | PCM_MASTER=0 (slave), DSP_PCM_SYNC=1 (count enable on external PCM_FSC), PPOD, EN |
| both | `PCM_FSC0DEL = not flag bit3` | — | `+0x20` | frame-sync placement, runtime-selected |

The base value is composed from the unconditional bit ops; the final
register value is conditional on the runtime flag byte — the report
separates `pcm_ctrl_path_a/b_base` from `pcm_ctrl_final_values`
(`0x0043/0x0063` master, `0x0045/0x0065` slave).

The transient `sbitw 11` / `sbitw 9` steps are wiped by the later
`cbitw 9` / `andw 0x83FF` — they are recorded as transient, not part of
the stable value.

## Clock side

* `CLK_CODEC_REG` (`0x00FF4004`): `andw 0xFCFF` clears bit8, `sbitw 9`
  (conditional on flag bit3) and `sbitw 14` → CLK_PCM_EN=1; CLK_PCM_SEL
  ∈ {01, 11} → PCM_CLK 1.152 MHz or 2.304 MHz under the SC14480 divider
  analogy.
* `DSP_MAIN_SYNC1_REG` (`0x01027F82`): `& 0x3FFF` in helper `0x156C`
  leaves PCM_SYNC=00 → 8 kHz frame under the analogy; `dsp_cfg` writes
  the full register to 0 (all audio interfaces at 8 kHz).
* `DIP_CTRL2_REG` (`0x00FF600E`) bit8 = SLOTCNT_RES=1: the DIP slot
  counter resumes with the DSP main counter.
* Runtime supervision: the main dispatcher reads `[0xD6]+0x38`
  (`0x01027FB8`, PHASE_INFO) each pass and tracks changes in a struct —
  a proven runtime PCM-sync monitor.

## Routing: where the proof stops

The SC14480 reference chain (PCM_IN0-3 → Gen2DSP → DSP_CODEC_OUT →
CODEC DAC, and CODEC ADC → DSP → PCM_OUT0-3, with RAMIN/RAMOUT ADPCM
buffers via DIP `A_LDRx`/`A_LDWx`) is a **documented architecture of a
related device**. The firmware configures exactly these windows, but the
per-sample data movement happens inside the DSP microcode, which is not
disassembled. Therefore: **configuration proven, data path unverified.**

## Interface mismatch with the Linux side (open)

Linux OEM: 8 × 16-bit slots, nominal BCLK 1.024 MHz, TX slot 5 = FON
control. SC14448 firmware side (under analogy): 4 PCM channels, PCM_CLK
1.152/2.304 MHz, 8 kHz frame. These are different interface geometries;
no slot↔channel mapping is proven. Slot 5 is **not** re-promoted to any
consumer here — the FON control-word question (Q46/Q55/Q75) stays open.
