# FON-E6 (rev 2) — OEM Linux PCMLINK bring-up model and OpenWrt gap analysis

> **Status: offline consolidation, plan only.  Nothing here has been
> executed on hardware by this document.**  Every fact carries its evidence
> class; executed experiments are cited with their dates and are **not**
> re-presented as future steps.  K1/K2 remain NO-GO.

Revision 2 corrects the review findings: (a) the reference bootlog is
FRITZ!OS **07.28 / Linux 4.4.60**, not 08.25, and its timestamps must not
be presented as the 08.25 sequence; (b) module-load order in the log does
not prove a linear "DMA fully configured, then upper stack" order; (c) the
2026-11-07 probe-only/C0/C1/C2 executions are recorded as **done**;
(d) `fon_c2.c` differs from the OEM order and is **PARTIAL**, not MATCH;
(e) the DMA descriptor layout and 16-entry ring **are implemented**;
(f) the C2 rollback is "re-assert reset + drop clock", **not** a
restoration of the prior register state.

Evidence classes: `DT` (decompiled OEM DTB), `GPL` (published AVM GPL
source), `DISASM` (`pcmlink.ko`/`isdn_fbox_fon5.ko` instruction analysis),
`OEM-LOG-07.28` (wiki bootlog, Linux 4.4.60, committed as
`docs/history/wiki-fritzos-oem-bootlog-reference.txt`), `OEM-CAPTURE-08.25`
(read-only console capture on this board), `HW-TEST` (executed on the
router, recorded in `fon-known-facts.md` §9d), `UNKNOWN`.

---

## 1. Already executed (2026-11-07) — chronology, not future steps

| Stage | Result | Key values | Source |
|---|---|---|---|
| Stage B probe-only | **PASS** | module loads, FON DT node binds (`stage=0x23`, `mode=probe-only`), `irq_spi=156/159`, `irq_intid=188/191`, `irq=-1`, `/proc/iomem` unchanged before/after | `fon-go-no-go.md`, `HW-TEST` |
| Stage C0 read-only | **PASS** | no ADSS owner in `/proc/iomem`; audio clocks enable_count 0 | `HW-TEST` |
| Stage C1 (module `2b523aec…9e40`) | **EXECUTED, PASS** | clock enable → reset pulse (20–24 ms) → 6 `readl` → re-assert reset → clock disable. Reads: `AUDIO_MODE=0x00000000`, `TDM_CTRL=0x00010001` (**2 channels**, not 8), `CLK_I2S_CTRL=0x00000000`, `I2S_RST=0x00000000`, `STEREO_TX/RX=0x00000102` (**MASTER=1 at reset**) | `fon-known-facts.md` §9d-7, `HW-TEST` |
| Stage C2 old (module `3546c2b9…85c6`) | **EXECUTED** | wrote `TDM_CTRL=0x06070007`, `STEREO_TX/RX=0x00240000`, `AUDIO_MODE=0x10000005`; all read back exactly; no hang/abort. Did **not** write `CHIP_CTRL_I2S`, `I2S_RST`, `DATA_WORD_SIZE(1)` | `fon-known-facts.md` §9d-8, `HW-TEST` |
| Clock-disable confirmation | **NOT CONFIRMED** | `clk_branch_toggle` warning on the disable path in both C1 and C2; enable count returned to 0 but the gate stop is not proven | `fon-known-facts.md`, `docs/fon-audio-ahb-clock-warning.md` |
| Corrected C2 (C2.1, code only) | **NOT RUN** | adds `CHIP_CTRL_I2S`, `I2S_RST` pulse, `DATA_WORD_SIZE(1)`, strict 4-register readback, error propagation | `fon-known-facts.md` §9d-9, `src/fon-driver/fon_c2.c` |

Already answered positively on hardware: **the ADSS block accepts register
writes and readback for the 8-slot geometry and the slave mode.** Still
open: the corrected C2 order has never run; the clock-gate stop is
unconfirmed; the SC14448 has never been observed under OpenWrt (Q4/Q27).

---

## 2. The OEM reference sequence (version-labelled)

All timestamps below are from the **07.28 / 4.4.60 wiki log**; the 08.25
capture on this board shows the same sequence with `CLK: 1024355 Hz`
instead of `1025720 Hz` — both are OEM reports, not our measurements.

| t (07.28 log) | Event | Evidence |
|---|---|---|
| 0.39 s | `msm_dectuart_probe` → ttyMSM0 | `OEM-LOG-07.28` |
| 11.9 s | `piglet.service` starts | `OEM-LOG-07.28` |
| 12.03 s | `dect_loader-bootmode`; `patch_dectfw` patch `a0` len 53; `dectmode 5`; image 51637 B crc 0xd7 | `OEM-LOG-07.28`, `DISASM` |
| 17.77 s | secondlevel upload success (≈5.7 s) | `OEM-LOG-07.28` |
| 19.98 s | **`TDM: FS: 8000 Hz CLK: 1025720 Hz`** — before any TDM client | `OEM-LOG-07.28` |
| 20.12 s | `pcmlink` module-mem allocation | `OEM-LOG-07.28` |
| 20.33 s | `isdn_fbox_fon5` module-mem allocation | `OEM-LOG-07.28` |
| 20.39 s | `mbox_dma_init` success | `OEM-LOG-07.28` |
| 21.12 s | `avm_dect` module-mem allocation | `OEM-LOG-07.28` |

**Ordering caveat (review):** `isdn_fbox_fon5` appears at 20.33 s while
`mbox_dma_init` succeeds at 20.39 s. The log therefore does **not** prove
"DMA fully configured, then upper stack loaded"; overlapping or lazy
initialisation is possible. The only ordering this log establishes firmly
is: firmware upload → TDM clock report → first TDM-client module load.

The SC14448-side upload sequence (reset API order, upload protocol) and
the pcmlink register sequence (ADSS probe, slave clock selection, STEREO/
TDM_CTRL values, DMA channels, EOR#2 frame model) are documented in
`fon-d06-summary.md`, `fon-adss-clock-reset.md`,
`history/fon-adss-avm-init-sequence.md`,
`history/fon-adss-tdm-channel-map.md`,
`docs/fon-sc14448-pcmlink-protocol.md` — unchanged by this revision.

---

## 3. Clock-source model

| Quantity | Value | Status |
|---|---|---|
| FSC | 8000 Hz, reported by `Piglet_noemif:Check_TDMInterface()` right after the secondlevel upload, before any TDM client | `OEM-LOG-07.28` / `OEM-CAPTURE-08.25` |
| BCLK | 1 025 720 Hz (07.28 log) / 1 024 355 Hz (08.25 capture); formula 1 024 000 Hz | OEM reports; not our measurement |
| Who drives the bus | SC14448 master / IPQ4019 ADSS slave — by the GPL slave path (`master=0`, `clksel(2)` external pad clock, dummy rates) and the DT | `GPL`, `DT`; master identity **inferred**, not measured |
| `GCC_AUDIO_AHB_CLK` / `GCC_AUDIO_PWM_CLK` | never enabled by the AVM driver | `GPL` |
| `GCC_AUDIO_BCR` (`AUDIO_BLK_ARES`) | assert/deassert at ADSS probe | `GPL`, `HW-TEST` (C1) |
| ADCC provider | AVM-tree only, absent in mainline; unused in slave mode | `GPL` |
| Which SC14448 divider produces the 1.024 MHz TDM BCLK | **UNKNOWN** (E5 found 1.152/2.304 MHz PCM candidates; neither matches) | `HISTORY` (E5), `UNKNOWN` |

---

## 4. `fon_c2.c` (corrected C2.1) vs the OEM order

| OEM operation (GPL) | OEM phase | C2.1 today | Verdict |
|---|---|---|---|
| map → `gcc_audio_blk_rst()` (assert, 20–24 ms, deassert) | ADSS probe | enable AHB clock → reset pulse → map → snapshot (order of clock/reset/map differs but is the conservative C1-proven order) | compatible |
| `adss_glb_i2s_interface_en(ENABLE)` (`0x10` BIT0) | ADSS probe | step 6, before TDM config | match |
| `adss_glb_audio_mode_B1K()` (`0x30` BIT28) | ADSS probe | step 10, **together with** the TDM bits at config time | **phase differs** (value matches) |
| `adss_config_clk()`: `adss_glb_i2s_reset()` pulse (`0x14`), **`adss_config_clksel(2)`** (external pad clock) | TDM config | I2S_RST pulse present (step 7); **`clksel(2)` absent — `ADSS_GLB_CLK_I2S_CTRL` is never written** | **missing** |
| `adss_config_tdm(enable=DISABLE, …)` first, enable on start | TDM config | STEREO written **with `ENABLE` (BIT21) set** at config time | **differs** |
| STEREO `DATA_WORD_SIZE(1)`, 16-bit words, `MCK_SEL` | TDM config | present (fixed after the executed C2) | match (untested on hardware) |
| `GLB_TDM_CTRL` 8 slots + delays | TDM config | `0x06070007` | match (executed value readback-verified) |

**Conclusion: C2.1 is PARTIAL.** Individual register values are derived
from the GPL bit definitions, but the operation order/phasing (B1K at
probe, `clksel(2)`, ENABLE-only-on-start) is not reproduced, and the
corrected sequence has never run on hardware.

---

## 5. Gap matrix (rev 2)

| # | Component | OEM | Ours | Status (rev 2) |
|---|---|---|---|---|
| 1 | DECT UART | `msm_dectuart` | console UART works; upload arbitration open (Q79) | PARTIAL (upload path only) |
| 2 | Firmware uploader | `Piglet_noemif.ko` (closed) | protocol model only (`piglet_uart_mock.py`, `piglet_image.py`) | MISSING, not authorized |
| 3 | Reset path | `dect_loader` GPIO40 API (DISASM); polarity UNKNOWN | none | MISSING (D0.6 gate) |
| 4 | TDM DT node | `tdm@0` | `900/901` patches + test DTS; disabled in normal image | PARTIAL (ADCC phandles AVM-only) |
| 5 | ADSS probe order | map → blk reset → I2S enable → B1K | C1/C2.1 code; executed C1 read-verified | MATCH (code), C2.1 untested |
| 6 | Pinmux | `dakota_gpio_pinconfig` call; body UNKNOWN | none; mainline pinctrl has no PCM function | MISSING (Q31/Q77) |
| 7 | Slave clock config | `clksel(2)`, dummy rates | **no `CLK_I2S_CTRL` write at all** | MISSING (was "PARTIAL" — corrected) |
| 8 | STEREO/TDM_CTRL/AUDIO_MODE | GPL values | C2 values write+readback verified (old C2); corrected C2 not run | PARTIAL (values match; order/phasing differs, §4) |
| 9 | DMA descriptors | `_mbox_desc` 156 B, `mbox_get_desc_size()`=L1_CACHE_ALIGN(156), NextPtr chain, 16 descriptors | **implemented**: `fon_mbox_desc` (156 B, `_Static_assert`), `fon_dma_build_ring()` (16 descriptors, cache-aligned stride, ping-pong buffers, 28-bit mask), host-tested (`fon_dma_test.c`) | MATCH at the descriptor level; MBOX register programming + start MISSING (`dma_start=-EOPNOTSUPP`) |
| 10 | Frame geometry + EOR#2 | raw-memory model proven | `fon_tdm.c` builds the exact raw frame | MATCH (memory level); wire order UNKNOWN (Q74) |
| 11 | Slot-5 control/status | `build_slic_ctrl`/`PutRxDMA` | `fon_tdm_frame_set_control/get_status`, slot5 tool | MATCH (Linux side) |
| 12 | Upper stack | `isdn_fbox_fon5`/`avm_dect` | userspace mocks only | PARTIAL |

---

## 6. Rollback reality (review)

`fon_c2.c` cleanup does **not** restore the prior register state:

* it re-asserts `GCC_AUDIO_BCR` (block back to reset) and disables the
  AHB clock;
* the baseline snapshot is used for **comparison only** — `before` values
  are never written back;
* the pre-C2 register state is unknown (the C1 notes already state that
  the reset pulse itself changes the register state);
* the clock-gate stop is **unconfirmed** (the `clk_branch_toggle` warning
  appeared on the disable path in both C1 and C2).

The honest statement: C2.1 leaves the block **in reset with the clock
dropped**, which is a bounded "quiescent" state, not a restoration of the
original state. Any plan that calls this a full rollback is wrong.

---

## 7. The one question that changes the path: FSC/BCLK at the IPQ4019 input

**How to obtain evidence without touching reset, pinmux or firmware:**
read-only observation only — the TLMM software probe (C0+ runbook) reads
the `GPIO_IO(n)` input bits of the pins the OEM captures show as muxed
(`FUNC_SEL` 2/3 for GPIO21/22/23/25/26/27); the one-shot kernel probe is
the stock-OpenWrt path. No writes, no pinmux change, no reset, no upload.

**What a positive result means:** periodic edges at ≈1.024 MHz (BCLK) and
≈8 kHz (FSC) on the known OEM mux pins under OpenWrt ⇒ the SC14448 is
running and driving the bus **without any OpenWrt-side action** — the
whole driver question collapses to "read the frames correctly" and the
firmware-upload/reset/pinmux gates become lower-risk (not bypassed).

**What a negative result means — almost nothing by itself.** A flat or
wrong reading can be any of: SC14448 held in reset (GPIO40 observed low
as an input under OpenWrt), firmware never uploaded, pinmux `FUNC_SEL`
different under OpenWrt (Linux reports no mux owner, but that is not a
TLMM readback), the IPQ4019 input path not seeing the signal (pad
configuration), or the wrong pins entirely. T3 alone cannot discriminate
these; it only tells us whether the question is worth escalating.

**Why the scope is not yet a prepared stage:** no electrical test point
has been identified that provably carries FSC/BCLK (board BGA, internal
layers, continuity to the PCM nets not established — `fon-tdm-control-only-plan.md`
§3). Passive scope measurement (T4) therefore remains **blocked on net
identification**, not merely gated.

**Decision value:** a *positive* T3 result would justify moving directly
toward read-only frame capture (C3 passive RX) and would de-prioritise
the upload/reset reverse-engineering. A *negative* T3 result leaves the
upload-path question (Q79/Q80, reset polarity) as the only way forward —
it must not be used to conclude the SC14448 is dead.

---

## 8. Next-operation list (DONE vs TODO)

| # | Operation | Status |
|---|---|---|
| N1 | Stage B probe-only, Stage C0, Stage C1, old C2 | **DONE 2026-11-07** (results in §1; no repeat needed) |
| N2 | Corrected C2.1 bounded run (with the §6 rollback semantics, documented as quiescent-state not restoration) | TODO, gated by `fon-go-no-go.md` ("C2 rerun: NOT READY") |
| N3 | Read-only TLMM FSC/BCLK probe (C0+ software/kernel probe) | TODO, separate review (stock OpenWrt has no `/dev/mem`); semantics per §7 |
| N4 | Net identification for a passive scope point (unpowered continuity) | TODO, precondition for any scope stage |
| N5 | C3 dry-run (frame build in DMA buffers, no start) | TODO (already coded; `dma_start=-EOPNOTSUPP`) |
| N6 | C4 active TDM | BLOCKED (K1/K2; requires N3-positive or upload-path resolution) |

---

## 9. Reproducibility inputs (all offline)

| Input | Location / SHA |
|---|---|
| OEM bootlog reference (07.28 / 4.4.60) | committed `docs/history/wiki-fritzos-oem-bootlog-reference.txt` |
| 08.25 console capture | `evidence/oem-08.25/console/2026-11-08/` (manifest) |
| `S11-piglet`, `rc.voip`, `E41-capi` | `reference/oem-08.25/extracted/init-scripts/` (manifest) |
| `pcmlink.ko` | `6620510bc1d4b0f4d670e1e93d3f308dc3002785d3129521156eb5e1bc4a363b` |
| `isdn_fbox_fon5.ko` | `47e0e29bbdc4e76738f2d893c4c587ec7dd7aa99f543a035140561ed90dbd2c9` |
| AVM GPL ADSS source | `reference/sources/avm/avm-gpl/…/sound/soc/qcom/ipq/ipq-adss-avm.c` (manifest) |
| HW236 DTB (first blob) | `3083e2acedc800015fea5ee7e57fa6cc8da551e21ee792095cbd8a7224bb841f` |
| Executed C1/C2 modules | `2b523aec…9e40`, `3546c2b9…85c6` (recorded in `fon-known-facts.md`) |

---

## 10. What this model does NOT prove

* the SC14448-side interpretation of slot 5 (Q16/Q17/Q75) and the wire
  order (Q74);
* `fs_per_dma` (Q76) and the `dakota_gpio_*` bodies (Q31/Q77);
* that FSC/BCLK exist under OpenWrt without the OEM upload — §7 is the
  only way to obtain that evidence;
* that the corrected C2 sequence behaves like the OEM one — it has never
  run (§4);
* the console/DECT UART arbitration for a future uploader (Q79).
