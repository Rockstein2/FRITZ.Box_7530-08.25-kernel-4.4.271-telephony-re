# E5-E — DSP audio timing vs DECT (DIP) timing

> **Status: historical analysis; current summary is `../sc14448-e5-summary.md`.**
> Static, offline. Report: `tools/reports/cr16-e5-clock-dependencies.json`.

## Firmware facts (proven)

* `DSP_MAIN_CTRL_REG` (`[0xD6]+0x3C` = `0x01027FBC`) is written `0x0400`
  in both `dsp_cfg` and the runtime enable. Under the SC14480 analogy
  bits 9-8 = `10`: **the DSP main counter starts on a DIP `<A_NORM>`
  instruction** (DIP-synchronised start-up for a voice connection).
* `DSP_MAIN_SYNC1_REG` (`0x01027F82`) = `0x0000`: PCM_SYNC, ADC_SYNC,
  DA_LSR_SYNC, DA_CLASSD_SYNC, AD_SYNC and DSP_SYNC0-2 all at 8 kHz
  under the analogy — DSP_SYNC0-2 are the periodic DSP start/interrupt
  sources of the reference. **Other DSP start sources are not
  excluded**: the SC14480 also lists a CR16 trigger (`DSP_CR16_INT`,
  bit4) and DIP interrupts; no CR16-side bit4 write was found in these
  images (absence recorded, not a trigger model).
* The DSP init stops the DIP first: `0x00FF6006 = 0x80` (URST=1 under
  the analogy) before any clock/DSP reconfiguration, in two functions
  (`0x145C`/`0x0ED2` with `r0=0x80` from `movw $0x80`, and
  `0x1348`/`0x0DBE` with `r2=0x80`; the conditional `r2==0` path stores
  0 and is not taken from the proven caller `movb $1,r2`).
* `DIP_CTRL2_REG` (`0x00FF600E`) bit8 = 1: the DIP slot counter resumes
  with the DSP main counter (SLOTCNT_RES under the analogy).
* Clock bring-up (f_clk2, called with `r2=4` from the enable sequence):
  `CLK_PLL_CTRL` (`0x00FF4010`) `0 → 0x0800 → 0x0852 → 0x085A` with
  delays; `CLK_CODEC_DIV` = 9, `CLK_PER_DIV` = 9, `CLK_PER10_DIV` =
  `0x21`, `CLK_PLL_DIV` = `0x1C`, `CLK_DSP_REG` = 9 (CLK_DSP_EN=1,
  divider 1), `CLK_AMBA` bit7 and a `CLK_AMBA` write helper
  (`0x28A4C`/`0x9FB4` with `r2=0x18, r3=2`).
* End of enable: `DSP_CTRL` bit3 (DSP_CLK_EN) is cleared — the DSP
  clock is gated after bring-up (wake-per-sync model under the analogy;
  only one of the reference's possible wake sources).

## Dependency classification

| Aspect | Status |
|---|---|
| shared clock source | PROVEN_FIRMWARE_CONFIG: PLL/codec/peripheral/DSP dividers are programmed inside the audio bring-up |
| shared initialization | PROVEN_FIRMWARE_CONFIG: DSP init stops the DIP and sets SLOTCNT_RES |
| shared firmware | PROVEN: the same init functions configure both DIP control bits and DSP/PCM registers |
| actual DECT radio dependence | RUNTIME_VERIFICATION_REQUIRED: `0x0400` selects DIP-synchronised start under the SC14480 analogy; whether the DIP must be radio-active or merely issue `<A_NORM>` is not decidable offline |

## Boundary

The firmware couples audio timing to the DIP sequencer through the
**main counter** configuration: with the analogy reading, the 8 kHz main
counter (and therefore PCM_FSC, codec syncs and the periodic DSP_SYNC
start sources) begins after a DIP `<A_NORM>`. This is a counter-start
configuration, not a proven DSP execution trigger, and it says nothing
about the other reference trigger sources. Whether it means "DECT
runtime required" or "DIP sequencer running in a non-radio mode is
enough" cannot be answered without either the SC14448 system-controller
documentation or runtime observation — neither is available offline
(K1/K2 NO-GO unchanged). The DIP program filled by the E3.3 loop
(`0x01000000+2i`) is still not decoded, so whether `<A_NORM>` is ever
issued is unknown.
