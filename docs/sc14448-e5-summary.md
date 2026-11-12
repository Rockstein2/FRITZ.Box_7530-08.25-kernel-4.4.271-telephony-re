# SC14448-E5.1 — Gen2DSP / PCM+ / CODEC audio path (audited)

Baseline: E5 `fc51b4088c4a686e1dc39650535ac8e45b45b752`. E5.1 is the
independent audit of E5: register-offset and interpretation corrections,
a downgraded DSP-program classification, the SC14480 Table 63 conflict,
and a separation of the DSP main counter from DSP execution triggers.
STRICTLY OFFLINE; K1/K2 remain NO-GO. Registers remain **SC14480
related-device analogies**, never a proven SC14448 map.

Audit record: `docs/history/sc14448-e51-audit.md`.

## What E5.1 corrected

| Finding | Correction |
|---|---|
| Wrong DSP-window offsets (`0x8E/0x90/0x92/0x9A/0xA6/0xAE` instead of the real `0x0E/0x10/0x12/0x1A/0x26/0x2E`) | `SC14480["dsp_window"]` now carries the Table 65 offsets (`DSP_CODEC_OUT +0x0E`, `DSP_CODEC_IN +0x10`, `DSP_PCM_OUT0 +0x26`, `DSP_PCM_IN0 +0x2E`, …); a unit test pins every offset against the absolute datasheet addresses |
| `0x17300` classified as an embedded DSP *program* | downgraded to **`DSP_PROGRAM_CANDIDATE_REFERENCED_BY_PC_START`**: the only proven link is the firmware's `DSP_PC_START` derivation; block content, executability and execution mechanism are unproven and are now stated as `NONE`/unproven in the report; the copy-loop search is a real scan (absolute stores/loads into the `0x0103xxxx`/`0x0104xxxx` windows), reported factually |
| DSP PC `0x7980` presented without the SC14480 map conflict | the firmware transform is identical to the **SC14480 Table 63 linear rule** `DSP = (CR16>>1) − 0x4000 (mod 2^16)`; under Table 63, CR16 `0x17300` lies in the row **«Gen2DSP Micro code RAM (Reserved)»** (`0x0001.4000–0x0001.7FFF → 0x6000–0x7FFF`), *not* in the active shared-RAM row (`0x0001.0000–0x0001.3FFF → 0x4000–0x5FFF`) — recorded in every report and open question Q82 |
| LSRATT=001 labelled «+2 dB» | corrected to **0 dB nominal** (Table 299 level at 0 dBm0); the intermediate LSRATT=111 step stays −12 dB (Table 113) |
| `0x00FF4860` named P3_DIR | corrected to **P3_DATA_REG**; direction is `0x00FF4866`, mode `0x00FF4868` |
| «runtime trigger of the DSP is the DIP, not a CR16 bit» | corrected: `DSP_MAIN_CTRL=0x0400` configures the **main counter** (DIP-`<A_NORM>` start under the analogy), which supplies the 8 kHz DSP_SYNC0-2; other DSP start sources of the reference (CR16 `DSP_CR16_INT` bit4, DIP interrupts) are **not excluded** — no CR16-side bit4 write was found in these images, that is absence, not a trigger model |
| «complete bring-up recovered» | corrected: the register *sequences and values* are instruction-proven; a complete, independently confirmed bring-up is **not** claimed — every value remains an SC14480 analogy, the DSP program execution is unproven, and the PCM↔DSP↔CODEC data path is inside undecoded microcode |

## Answers to the eight questions (E5.1 status)

1. **Where and how does the Gen2DSP start?** Guarded `[0xD6]=0x01027F80`
   chain from main: `dsp_init` powers down, clears DSP_INT, writes
   `DSP_PC_START = 0x7980`; `enable` sets DSP_EN=1, INT_MASK|=0x803C,
   CLK_DSP=9, MAIN_CTRL=0x0400, then gates DSP_CLK_EN off again.
   Proven: the writes. Not proven: that any DSP instruction ever
   executes, or that the start sources fire. The main counter start
   (DIP `<A_NORM>` under analogy) is a **counter** configuration, not a
   proven DSP execution trigger. Vector-29 `dsp_int` handler
   (`0x28A94`/`0x27914`) is proven firmware behaviour.
2. **Where does the DSP program come from?** Candidate block at
   `0x17300` in both images (1469/893 words); the firmware derives
   `DSP_PC_START` from it via the exact Table-63 linear rule.
   Classification: **CANDIDATE_REFERENCED_BY_PC_START** — execution
   mechanism, content validity and the SC14480 «Reserved»-row conflict
   are all open (Q82/Q83).
3. **PCM+ configuration?** Instruction-proven: PCM_CTRL master base
   `0x0043` / slave-synced base `0x0045`, with the FSC0DEL bit5
   conditional on the runtime flag byte (finals `0x0043/0x0063` and
   `0x0045/0x0065`); CLK_PCM_EN, PCM_CLK 1.152/2.304 MHz, MAIN_SYNC1=0
   (8 kHz frame), SLOTCNT_RES, main-loop PHASE_INFO monitor — under
   analogy.
4. **PCM ↔ DSP ↔ CODEC route?** Still unproven and now explicitly
   bounded: the per-sample path is inside the undecoded `0x17300`
   microcode candidate (Q83). CONFIGURATION_PROVEN,
   DATA_PATH_UNVERIFIED.
5. **CODEC writes?** Proven bit sequences, with the corrected LSR gain
   reading (final LSRATT=001 → 0 dB nominal) and the note-57 order.
6. **PCM clock vs DECT timing?** Shared clock/init/firmware dependence
   proven; the main-counter DIP-`<A_NORM>` start is analogy;
   DSP-execution-trigger dependence is explicitly separated and marked
   RUNTIME_VERIFICATION_REQUIRED.
7. **Standalone OpenWrt needs?** The candidate register sequences are
   known, but the five blockers stand: SC14448 register identity, DSP
   program execution, DIP-`<A_NORM>` runtime question, IPQ4019↔SC14448
   PCM geometry mismatch (8×16-bit @1.024 MHz vs 4 channels
   @1.152/2.304 MHz), and the unproved FON command path (E4.2).
8. **The single missing fact?** Unchanged: the SC14448 side of the
   DSP-PC-to-flash mapping and the DSP-window identity. E5.1 adds the
   concrete test for it: Table 63 marks the `0x17300` range Reserved on
   SC14480, so either an SC14448 map confirms this region as microcode
   space, or the DSP_PC_START value is meaningless on this silicon.

## Criterion status after the audit

* **A (init sequence with concrete values)** — the sequences and values
  are instruction-proven, but as SC14480-analogy configurations only:
  **conditionally satisfied**, not a full completion.
* **B (DSP program selection path)** — the derivation chain is exact;
  the «program» identity is a candidate: **partially satisfied**.
* **C (digital audio route)** — narrowed to the undecoded `0x17300`
  block: **open**.
* **D (routing in inaccessible ROM)** — not claimed.

No hardware stage is justified by E5/E5.1 alone; K1/K2 remain NO-GO.

## Files

* `tools/cr16_audio_architecture.py` (corrected tables, downgraded
  classification, Table 63 comparison, real copy-loop scan),
  `tools/tests/test_cr16_audio_architecture.py` (offset truth table,
  classification gates, Table 63 rule, LSR gain labels, trigger
  separation, report invariants)
* reports: `tools/reports/cr16-e5-*.json` (regenerated, fail-closed
  replay)
* `docs/history/sc14448-e5-*.md` (corrected), plus the audit record
  `docs/history/sc14448-e51-audit.md`
* open questions updated: Q82 (Table 63 conflict), Q87
