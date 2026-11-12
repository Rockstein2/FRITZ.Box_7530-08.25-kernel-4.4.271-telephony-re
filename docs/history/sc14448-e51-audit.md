# E5.1 — Independent Audio Architecture Audit

> **Status: historical analysis; current summary is `../sc14448-e5-summary.md`.**
> Offline audit of E5 (`fc51b4088c4a686e1dc39650535ac8e45b45b752`).
> No hardware activity; K1/K2 NO-GO unchanged.

Review inputs: the E5 analyzer and reports, the SC14480 rev 1.0 datasheet
(Tables 63, 65, 113, 154, 155, 299) and the SC14CVMDECT-related GPIO
layout. The audit found six problems; all are corrected in the analyzer
and the regenerated reports, and pinned by tests.

## 1. DSP register offsets were wrong (fixed)

The E5 `dsp_window` table used `0x8E/0x90/0x92/0x9A/0xA6/0xAE` for
CODEC_OUT/CODEC_IN/RAM_OUT0/RAM_IN0/PCM_OUT0/PCM_IN0. Table 65 gives
the CR16 addresses `0x01027F8E`, `0x01027F90`, `0x01027F92`,
`0x01027F9A`, `0x01027FA6`, `0x01027FAE` — offsets `+0x0E`, `+0x10`,
`+0x12`, `+0x1A`, `+0x26`, `+0x2E` from `0x01027F80`. The wrong keys
were outside the 0x80-sized window check and therefore never matched
firmware accesses (the reports themselves never mislabelled a register),
but the reference table was wrong. It is now the full Table 65 set, and
`test_cr16_audio_architecture.py` pins every offset against the
datasheet absolute addresses.

## 2. `0x17300` was classified as an embedded DSP *program* (downgraded)

`classify_program_source` promoted any non-empty block to
`DSP_PROGRAM_EMBEDDED_IN_FIRMWARE_IMAGE`, ignored `pc_value`, and took
`copy_loop_found=False` as a constant instead of a search result.
Corrected classification: **`DSP_PROGRAM_CANDIDATE_REFERENCED_BY_PC_START`**.
The only proven link is the firmware's own derivation
`DSP_PC_START = ((0x17300>>1)+0xC000)&0xFFFF = 0x7980`. The report now
states `block_content_validation = NONE` (no DSP opcode/structure check
exists), records a real scan of absolute stores/loads into the
`0x0103xxxx`/`0x0104xxxx` microcode windows (`NONE_FOUND_BY_THIS_SCAN`),
and passes the derived `pc_value` through the classifier.

## 3. DSP PC `0x7980` vs the SC14480 map (documented, not resolved)

SC14480 Table 63 (printed p132) rows:

| CR16Cplus address | Gen2DSP code address | Meaning |
|---|---|---|
| `0x0001.0000–0x0001.3FFF` | `0x4000–0x5FFF` | Gen2DSP Micro code RAM **mapped in Shared RAM** |
| `0x0001.4000–0x0001.7FFF` | `0x6000–0x7FFF` | Gen2DSP Micro code RAM **(Reserved)** |
| `0x0104.0000–0x0104.AFFF` | `0x8000–0xD7FF` | Micro code ROM |

The firmware transform `(addr>>1)+0xC000 (mod 2^16)` is **identical**
to the table's linear rule `DSP = (CR16>>1) − 0x4000 (mod 2^16)`
(verified: `0x00010000 → 0x4000`, `0x17300 → 0x7980`). But CR16
`0x17300` lies in the table's **(Reserved)** row, not in the active
shared-RAM row. This neither proves nor refutes execution on the
SC14448 — the whole second-level image (code at `0x0+`) does not fit
the SC14480 program-flash map (`0x000F0000+`) either, so the SC14448
organisation clearly differs. Consequence: the value `0x7980` is a
proven firmware-written constant; its hardware meaning is open (Q82).
The conflict is recorded in `cr16-e5-dsp-program-source.json`
(`sc14480_table63`).

## 4. LSRATT gain misread (fixed)

E5 called the final `LSRATT=001` «+2 dB». Table 113's step table gives
`000 = +2 dB`, `111 = −12 dB`; Table 299 gives `001` **0 dB nominal** at
0 dBm0. The codec report now emits `0 dB nominal (Table 299 level at
0 dBm0) (LSRATT=001)`, with the intermediate `LSRATT=111 → −12 dB`
step labelled from Table 113. Pinned by `lsratt_gain()` unit checks.

## 5. GPIO name corrected

`0x00FF4860` was named `P3_DIR_REG`; the SC14CVMDECT-related layout is
`P3_DATA_REG` (`0x00FF4860`), `P3_DIR_REG` (`0x00FF4866`),
`P3_MODE_REG` (`0x00FF4868`) — consistent with the P0/P2 pattern
(data at `0x48x0`, dir at `0x48x6`, mode at `0x48x8`). Corrected and
test-pinned.

## 6. DSP main counter vs DSP execution triggers (separated)

`DSP_MAIN_CTRL = 0x0400` configures the **main counter** to start on a
DIP `<A_NORM>` under the SC14480 analogy (Table 155); the counter then
generates the 8 kHz syncs, including the periodic `DSP_SYNC0-2` DSP
start/interrupt sources (Table 154). The reference also lists a CR16
trigger (`DSP_CR16_INT`, bit4) and DIP interrupts as DSP start sources.
E5's «the runtime trigger is the DIP, not a CR16 bit» was therefore too
categorical. Corrected wording: no CR16-side bit4 write was found in
these images (absence recorded); other trigger sources are **not
excluded**. The clock-dependencies report now carries
`dsp_trigger_sources_not_excluded` and separates
`MAIN_COUNTER_DIP_DEPENDENT_START` from DSP execution.

## What survived the audit unchanged

* `[0xD6] = 0x01027F80` with the in-function guard (`cmpd`) — proven.
* `DSP_PC_START = 0x7980` write and its derivation chain — proven.
* The PCM_CTRL master/slave composition (`0x43`/`0x45`), CLK_CODEC
  PCM bits, MAIN_SYNC1=0, SLOTCNT_RES, the PHASE_INFO monitor and the
  vector-29 DSP-interrupt handler — proven firmware behaviour.
* The CODEC VREF/MIC/LSR/ADDA/TONE sequences and the note-57 order —
  proven firmware behaviour, analogy names.
* The IPQ4019↔SC14448 PCM geometry mismatch and the unclaimed slot 5.

## Verdict

E5 is accepted **as a partially confirmed reconstruction**, not as a
proof of DSP execution or of a standalone-reproducible bring-up.
Criteria A and B are conditionally/partially satisfied; C and D are
open. No hardware stage may be scheduled on this evidence; K1/K2 remain
NO-GO. The decisive next evidence is the SC14448-side meaning of DSP PC
`0x7980` (Q82): a SC14448 memory/system-controller document, or a
runtime observation — the latter is explicitly out of scope here.

## Follow-up fixes (review round 2)

Three further findings were corrected after the first audit commit:

1. **Classifier strictness.** `classify_program_source()` now checks
   `pc_value == dsp_pc_word(run_start)` before granting
   `DSP_PROGRAM_CANDIDATE_REFERENCED_BY_PC_START`; any inconsistency
   (including `pc_value = None`) returns
   `DSP_PROGRAM_PC_ADDRESS_MISMATCH`. The report records the check as
   `pc_consistency_check`.
2. **Copy-scanner status.** `find_microcode_copy_candidates()` derives
   its status from the findings (`PAIR_BASED_STORES_FOUND`,
   `DIRECT_ABSOLUTE_STORES_FOUND`, `PAIR_BASED_LOADS_FOUND`,
   `DIRECT_ABSOLUTE_LOADS_FOUND`, else `NONE_FOUND_BY_THIS_SCAN`) and
   now also scans register-pair bases loaded from a window literal
   (`movd $imm:l,(rp)`). Documented limitations: abs24 cannot encode
   the >24-bit windows at all (the direct-absolute pass is a low-alias
   completeness check), pair tracking follows only `movd` bases (no
   `addd`/`r12`/`r13`/indirect), and DMA/hardware copies are invisible.
   For both real images the result stays `NONE_FOUND_BY_THIS_SCAN`.
3. **PCM_CTRL base vs final.** The report separates the unconditional
   base values (`master 0x0043`, `slave 0x0045`) from the conditional
   finals with FSC0DEL (`master 0x0043/0x0063`,
   `slave 0x0045/0x0065`); `pcm_ctrl_final_values` states all four.
