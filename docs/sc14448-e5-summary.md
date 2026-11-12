# SC14448-E5 — Gen2DSP / PCM+ / CODEC audio-path reconstruction

Baseline: E4.4 `e0156d1e8e59b86d8b245fd92780a146e7686cd2`. STRICTLY
OFFLINE; no router access, no hardware tests; K1/K2 remain NO-GO. All
results are static, from SHA256-checked normal and p2test images, via
`tools/cr16_audio_architecture.py` (7 reproducible JSON reports in
`tools/reports/cr16-e5-*.json`, tests in
`tools/tests/test_cr16_audio_architecture.py`).

Register **names** in this stage are SC14480 related-device analogies —
never a proven SC14448 map. What is proven is the firmware's own
instructions: raw bytes, `[0xD6]+offset` effective addresses and the
written values.

## Answers to the eight questions

### 1. Where and how does the Gen2DSP start?

Via a guarded, call-chained bring-up from the second-level main entry.
`[0xD6] = 0x01027F80` (image value; the init function itself checks
`cmpd $0x1027f80,([0xD6])` before any DSP access). The chain
main → `0x3A0C`/`0x27126` → pad init → `dsp_init`
(`0x1330`/`0x0DA6`) powers the DSP down, clears DSP_INT, stops the DIP,
and writes **DSP_PC_START = 0x7980**; then main → `0x3A34`/`0x27152` →
`enable` (`0x190E`/`0x1390`) sets DSP_EN=1, DSP_INT_MASK|=0x803C,
CLK_DSP=9, DSP_MAIN_CTRL=0x0400 and finally gates the DSP clock off
again (wake-per-sync model). Under the SC14480 analogy DSP_MAIN_CTRL
`0x0400` means the main counter (which generates the 8 kHz syncs and
the periodic DSP start/interrupts DSP_SYNC0-2) **starts only on a DIP
`<A_NORM>` instruction** — the runtime start trigger is the DIP, not a
CR16 bit write (no CR16-side DSP_CR16_INT site exists). Vector 29
(`dsp_int`) handler `0x28A94`/`0x27914` is proven: it reads and
write-back-clears `[0xD6]+0x58` (DSP_INT), dispatches on VECTOR bits 3/2,
clears `0xFF5402=0x2000` and `retx`s.

### 2. Where does the DSP program come from?

From the firmware image itself. Both images carry a dedicated block at
`0x17300` (normal `0x17300–0x17E79` = 1469 words; p2test
`0x17300–0x179F9` = 893 words; identical first bytes) and compute
`DSP_PC_START = ((0x17300 >> 1) + 0xC000) & 0xFFFF = 0x7980`.
Classification: **DSP_PROGRAM_EMBEDDED_IN_FIRMWARE_IMAGE**; whether the
DSP executes that block in place, from a copy, or from internal ROM is
unproven (no copy loop found, no ROM-window literal). A companion
`(addr>>1)+0x8000` transform builds DSP-visible data structures in both
images (candidate data-space mapping). See
`history/sc14448-e5-dsp-program-source.md`.

### 3. Was the PCM+ configuration found?

Yes, instruction-proven. `[0xD6]+0x36` (`0x01027FB6`) receives a
runtime-selected configuration: path A **master** `0x0043`
(PCM_EN+MASTER+PPOD), path B **slave synced to external PCM_FSC**
`0x0045` (PCM_EN+DSP_PCM_SYNC+PPOD), FSC0DEL conditional; selection by
bit0 of a flag byte (`0x93CD`/`0x9514`, not image-initialized, produced
by helper `0x3CBE`/`0x278DA`). CLK_CODEC: CLK_PCM_EN=1, PCM_CLK
1.152/2.304 MHz; MAIN_SYNC1 = 0 → 8 kHz frame; DIP_CTRL2 bit8
(SLOTCNT_RES); the main dispatcher reads `[0xD6]+0x38` (PHASE_INFO)
each pass — a runtime PCM-sync monitor. All under SC14480 analogy.

### 4. Was the PCM ↔ DSP ↔ CODEC route found?

No — and that is now precisely located. The firmware configures exactly
the windows of the SC14480 reference chain (PCM_IN0-3 / DSP_CODEC_OUT /
RAMIN/RAMOUT ADPCM buffers), but the per-sample conversion happens
**inside the embedded DSP microcode**, which is not disassembled
offline. Status: **CONFIGURATION_PROVEN, DATA_PATH_UNVERIFIED**. The
critical routing lives in the `0x17300` block (or ROM); this is the
missing fact for criterion D of E5.

### 5. Which CODEC register writes are proven?

The full analog bring-up, with values: CODEC_VREF (bias on, VREF_INIT=1
precharge, all powerdown bits cleared, 2000-iteration delay, VREF_INIT=0
later) — matching the SC14480 note-57 order; CODEC_MIC (single-ended
MICp, 0 dB, MIC_PD=0); CODEC_LSR (differential DA to LSR±, amplifiers
on, final 2 dB); CODEC_TONE (RNG_PR_DIS, CID_PR_DIS); CODEC_ADDA
powerdown (`orw 3`) in init and powerup (`andw 0x7FFC`) in enable;
CODEC_TEST_CTRL COR_ON plus the conditional MIC_MUTE/offset
compensation sequence (OFFSET1→OFFSET2). Details in
`history/sc14448-e5-codec-init.md`.

### 6. How are PCM clock and DECT timing connected?

By firmware configuration, strongly: the DIP is stopped (URST=1) before
every audio reconfiguration; DIP_CTRL2 SLOTCNT_RES=1 couples the DIP
slot counter to the DSP main counter; and DSP_MAIN_CTRL=0x0400 selects
DIP-`<A_NORM>`-synchronised start of the main counter that generates the
8 kHz audio syncs. **Shared clock, shared initialization and shared
firmware are proven; actual DECT-radio dependence is not** —
RUNTIME_VERIFICATION_REQUIRED (see `history/sc14448-e5-clock-dependencies.md`).

### 7. What is needed for standalone OpenWrt?

E5 makes the "keep the OEM firmware as a closed DSP/CODEC engine" model
concrete: clock init, PCM config, DSP init and CODEC init are all
instruction-proven with values, so offline re-implementation of the
*register sequences* is possible. But five blockers remain: SC14448
register identity (analogy only), DSP-program execution mechanism,
DIP/`<A_NORM>` runtime question, the IPQ4019↔SC14448 PCM geometry
mismatch (8×16-bit @1.024 MHz vs 4 channels @1.152/2.304 MHz), and the
still-unproved FON command path (E4.2). Inventory in
`history/sc14448-e5-standalone-readiness.md`.

### 8. What single missing fact blocks a safe audio test?

**The SC14448 side of the DSP-PC mapping and the DSP-window identity.**
If the `0x17300` block is really the Gen2DSP program and `0x01027Fxx`
is really the DSP register window on this silicon, E5 has already
recovered the complete bring-up; without it, every recovered value is an
unconfirmed analogy and no runtime audio test can be justified
(K1/K2 NO-GO). The second-order blocker is the DIP-`<A_NORM>`
synchronisation: the audio counter is configured to wait for a DECT
sequencer event whose issuance is not provable offline.

## Criterion status

* **A (init sequence with concrete register values) — satisfied** for
  clock, DSP, PCM and CODEC.
* **B (DSP program selection path) — satisfied** with the exact
  derivation chain; execution mechanism open.
* **C (digital audio route) — narrowed**: the route is inside the
  embedded DSP block; the block exists in-image.
* **D (critical routing in inaccessible ROM) — not claimed**: the
  microcode is present in the image, but its execution location is
  unknown, so neither "in-image execution" nor "internal ROM" is
  asserted.

## Review fixes bundled with E5

`test_cr16_external_register_map.py` no longer asserts the pre-E3.2
"`0x00FF4900` not used / low-20-bit correlation" model: it now checks the
RELOC_ABS20 ISA rule (encoded `0xF4900` ≡ architectural `0x00FF4900`)
directly, without needing the external reference headers, and keeps the
header-dependent checks as honest SKIPs (missing `/tmp/opencode/vc/device`
stays a SKIP, never a PASS). The tool's `alias_conclusion` was corrected
for future regeneration (v2); the committed v1 report artifact is
explicitly flagged in the test.

## Files

* `tools/cr16_audio_architecture.py`, `tools/tests/test_cr16_audio_architecture.py`
* reports: `tools/reports/cr16-e5-{dsp-registers,dsp-init,dsp-program-source,pcm-routing,codec-init,clock-dependencies,readiness}.json`
* `docs/history/sc14448-e5-{dsp-init,dsp-program-source,pcm-routing,codec-init,clock-dependencies,standalone-readiness}.md`
