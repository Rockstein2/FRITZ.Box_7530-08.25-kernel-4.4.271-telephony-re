# FON-E6 — OEM Linux PCMLINK bring-up model and OpenWrt gap analysis

> **Status: offline reconstruction, plan only.  Nothing here has been
> executed on hardware.**  Every fact carries its evidence class.  K1/K2
> remain NO-GO: no reset, no GPIO40, no firmware upload, no clock/reset
> control, no DMA, no line/ring on this evidence.

Strategy decision (2026-11-12): stop reverse-engineering SC14448 internals
and instead reproduce the OEM Linux path to a working PCMLINK. This
document is the consolidated, ordered OEM model from **firmware upload to
active TDM**, the clock-source model, the component gap matrix against our
OpenWrt driver (`src/fon-driver/`), and the minimal-risk operation list for
the first future test. It supersedes no evidence; it sequences it.

Evidence classes: `DT` (decompiled OEM DTB), `GPL` (published AVM GPL
source), `DISASM` (`pcmlink.ko`/`isdn_fbox_fon5.ko` instruction analysis),
`OEM-LOG` (wiki 4.4.60 bootlog, committed as
`docs/history/wiki-fritzos-oem-bootlog-reference.txt`), `OEM-CAPTURE`
(read-only 08.25 console capture on this board), `UNKNOWN`.

---

## 1. The OEM sequence, in order

### Phase 0 — platform bring-up

| # | Step | Evidence |
|---|---|---|
| 0.1 | `msm_dectuart` binds the shared console/DECT UART (`serial@78af000` → ttyMSM0, t=0.39 s) | `OEM-LOG`, `GPL` (`drivers/tty/serial/msm_dectuart.c`, SHA in the AVM manifest) |
| 0.2 | HW236 DTB (first blob, SHA `3083e2ac…bb841f`, subrevision 2): `tdm@0` (dma-tx 0 / dma-rx 7, stereo-tx 0 / stereo-rx 3, ADCC BCLK/MCLK clocks), `pcm@7704000` (not the FON path), `audio@7700000` (reset `AUDIO_BLK_ARES`), `gpio_avm_dect_reset` = GPIO40 (`param 0x0b`), PINMUX2/PINMUX3 with `function` 2/3 | `DT` |

### Phase 1 — SC14448 firmware upload (`piglet.service`)

| # | Step | Evidence |
|---|---|---|
| 1.1 | `modprobe Piglet_noemif dect_firstlevelfile=dectfw_firstlevel_441_slow.hex dect_secondlevelfile=dectfw_secondlevel_441.hex piglet_dectmode=0x105` (p2test image + `0x105` when `Ptest_was_here`) | `GPL` init script `S11-piglet` (extracted, verified by `tools/verify-workspace.sh`) |
| 1.2 | `dect_loader()` reset order: `dakota_gpio_ctrl(gpio,0,1)` → `dakota_gpio_out_bit(gpio,0)` (API-assert) → delay → `msm_dectuart_init()` → `dakota_gpio_out_bit(gpio,1)` (API-release) → settle → upload | `DISASM` (`fon-d06-summary.md`, `history/fon-d06-dect-reset-path.md`) |
| 1.3 | Upload protocol: `STX`/`SOH` framing, length, `ACK`/`NACK`, data, checksum (modelled by `src/mock/piglet_uart_mock.py`, `piglet_image.py`). Firstlevel slow upload, then secondlevel: `patch_dectfw` patch address `a0`, len 53; `dectmode 5`; image `51637` bytes `crc=0xd7`; `slow: dect_loader-bootmode` | `OEM-LOG`, `DISASM` |
| 1.4 | t=17.77 s: `upload of '/lib/modules/dectfw_secondlevel_441.hex' successfull` (≈5.7 s upload) | `OEM-LOG` |
| 1.5 | t=19.98 s: **`[piglet]TDM: FS: 8000 Hz CLK: 1025720 Hz`** — `Piglet_noemif.ko:Check_TDMInterface()` (100 ms edge count × 5) confirms the SC14448 now drives the TDM clocks, **before any TDM client exists**. The 08.25 capture on this board reports the same sequence with `CLK: 1024355 Hz` | `OEM-LOG`, `OEM-CAPTURE`, `DISASM` (`fon-d06-summary.md`) |
| 1.6 | `piglet.service` exits | `OEM-LOG` |

### Phase 2 — `pcmlink.ko` (t=20.12 s)

| # | Step | Evidence |
|---|---|---|
| 2.1 | ADSS probe `intf_audio_adss_probe`: `ioremap(0x7700000, 0x34)` → `reset_control_get("blk_rst")` → `gcc_audio_blk_rst()` (assert, 20–24 ms, deassert) → `adss_glb_i2s_interface_en(ENABLE)` (`0x10` BIT0) → `adss_glb_audio_mode_B1K()` (`0x30` BIT28) | `GPL` (`sound/soc/qcom/ipq/ipq-adss-avm.c`), `docs/fon-adss-clock-reset.md` |
| 2.2 | Link init `ipq40xxtdm_linkinit()`: `dakota_gpio_pinconfig()` applies the PINMUX2/PINMUX3 profile (call site `0xa168`); the transformation inside `dakota_gpio_pinconfig()` is **UNKNOWN** | `DISASM` (`fon-known-facts.md` §4c) |
| 2.3 | Slave clock config `adss_config_clk(ext_clk=1)`: `adss_glb_i2s_reset()` pulse on `0x14` (4–5 ms, ends 0) → `adss_config_clksel(2)` selects the **external pad clock**. No GCC audio clock is enabled anywhere in the driver; the ADCC BCLK/MCLK provider is used only in master mode | `GPL` |
| 2.4 | TDM config `adss_config_tdm(enable=1, master=0, ext_clk=1)`: STEREO0/STEREO3 RMW — clear `MASTER|ENABLE|DATA_WORD_SIZE|I2S_WORD_SIZE_32|MIC_WORD_SIZE_32|MCK_SEL`, set `DATA_WORD_SIZE(1)|I2S_WORD_SIZE_16|MIC_WORD_SIZE_16|MCK_SEL|ENABLE` | `GPL` (`history/fon-adss-avm-init-sequence.md`) |
| 2.5 | `ADSS_GLB_TDM_CTRL` (`0x1c`): `TX_CHAN_NUM(8-1)`, `RX_CHAN_NUM(8-1)`, TX/RX delay → `0x06070007` (value cross-checked against the C2 reconstruction) | `GPL`, `HISTORY` |
| 2.6 | `tdm_if_adss_dma_init()`: `mbox_dma_init(PLAYBACK, stereo_tx=0 → mbox0@0x7708000, IRQ GIC_SPI 156 → INTID 188)`; `mbox_dma_init(CAPTURE, stereo_rx=3 → mbox3@0x770e000, IRQ GIC_SPI 159 → INTID 191)`; **16 DMA descriptors** per direction; `mbox_dma_policy_reset()` leaves the 16-bit/end-swap bits unset (vendor comment signals uncertainty) | `GPL`, `DT`, `OEM-LOG` (`mbox_dma_init: … hwirq=191`, t=20.39 s) |
| 2.7 | `fs_per_dma` is computed as `[r5]/[r5+8]` from the closed board config table (`ipq40xxtdm_linkinit` `0x9ef0..0x9f28`); the GPL comment "4 ms == 32" describes intent, not the passed value — **UNRESOLVED (Q76)** | `DISASM`, `GPL` |
| 2.8 | TX frame build `TxDMA`: rails `0x0000`, `0xfefe`×3, `0x5555` (suppressed when `TDMPriv+0x808 != 0`), control at logical slot 5, audio at logical slots 6/7; `EOR #2` swaps adjacent 16-bit halfwords inside each 32-bit DMA word → control lands at raw 16-bit index 4 (byte `0x08`). RX `PutRxDMA` reads status through the same swap | `DISASM` (`history/fon-e1-dma-byte-order.md`, `docs/fon-sc14448-pcmlink-protocol.md`) |
| 2.9 | Control/status chain: 64-entry command ring → `TxDMA` → slot-5 control word (`build_slic_ctrl`: `0x4000` marker, `0x8000` special); RX slot-5 status → virtual register `0x44` | `DISASM` |

### Phase 3 — the telephony stack

| # | Step | Evidence |
|---|---|---|
| 3.1 | `isdn_fbox_fon5` loaded (t=20.33 s) — upper FON state machine over pcmlink virtual registers | `OEM-LOG`, `DISASM` |
| 3.2 | `avm_dect` loaded (t=21.12 s) — DECT userspace-facing stack (`dect_io` → `avm_dect` → `pcmlink`) | `OEM-LOG`, `OEM-CAPTURE` (module refcounts) |

---

## 2. Clock-source model

| Quantity | Value | Status |
|---|---|---|
| FSC | 8000 Hz, generated by the **SC14448** after secondlevel upload | `OEM-LOG` (proven behaviour), master identity inferred from the GPL slave path + DT `master=0` |
| BCLK | 1 025 720 Hz (wiki build) / 1 024 355 Hz (08.25 capture) | `OEM-LOG`/`OEM-CAPTURE` — both OEM reports, not our measurements |
| BCLK formula | 8 slots × 16 bit × 8000 Hz = 1 024 000 Hz | `GPL` (`ipq-adss-avm.c:2060`) |
| ADSS role | slave; external pad clock via `clksel(2)`, dummy rates 252/254/255 | `GPL` |
| `GCC_AUDIO_AHB_CLK` (0x181b010 bit0), `GCC_AUDIO_PWM_CLK`, `audio_clk_src` | never enabled by the AVM driver (no `clk_get` in the driver) | `GPL` |
| `GCC_AUDIO_BCR` (`AUDIO_BLK_ARES`, 0x1B008 bit0) | asserted/deasserted at ADSS probe (20–24 ms) | `GPL` |
| ADCC provider (audio_tx/rx_bclk/mclk) | AVM-tree only; absent from mainline 6.12; unused in slave mode | `GPL` |
| Relationship to E5 | the SC14448 firmware configures its own PCM clock domain (1.152/2.304 MHz candidates); which SC14448 divider produces the 1.024 MHz TDM BCLK is **UNKNOWN** | `HISTORY` (E5), `UNKNOWN` |

The measured 1025720/1024355 Hz vs the 1024000 Hz formula (+0.17 % /
+0.03 %) is an OEM-report artefact to be re-measured passively (D0.4),
not a confirmed SC14448 divider.

---

## 3. Component gap matrix (OEM vs our OpenWrt driver)

`src/fon-driver/` status: `fon_tdm.c/h` (frame/control helpers),
`fon_hw.c/h` (platform driver, DT resources, safe diagnostics, DMA ring
prep), `fon_c1.c`/`fon_c2.c` (bounded MMIO tests), `fon_dma.c` (C3
dry-run buffer fill), `src/mock/*` (userspace models).

| # | Component | OEM (evidence) | Ours | Gap |
|---|---|---|---|---|
| 1 | DECT UART driver | `msm_dectuart` (GPL) | none needed — console UART already works under OpenWrt; **upload arbitration is the open Q79** | MISSING but only for upload path |
| 2 | Firmware uploader (piglet) | `Piglet_noemif.ko` (closed) + `S11-piglet` params | protocol model `piglet_uart_mock.py`/`piglet_image.py` (userspace, upload not authorized) | MATCH at protocol-model level; kernel uploader MISSING and **not authorized** |
| 3 | Reset path | `dect_loader` GPIO40 API sequence (DISASM); electrical polarity UNKNOWN | none | MISSING (gate D0.6); `dakota_gpio_out_bit` body UNKNOWN |
| 4 | TDM DT node | `tdm@0` (DT) | `900/901` patches + `fon-tdm-7530-dtc-test.dts`; node `status=disabled` in the normal image | PARTIAL — resource list matches (adss, pcm, mbox_tx/rx, stereo_tx/rx, irq, resets); ADCC clock phandles are AVM-tree-only |
| 5 | ADSS probe order | map → blk reset → I2S enable → B1K (GPL) | `fon_c1.c` (bounded C1: clock+reset+readback+rollback); C2 revised to add `CHIP_CTRL_I2S` and `I2S_RST` pulse | MATCH (C1/C2 corrections recorded in `history/fon-adss-avm-init-sequence.md`) |
| 6 | Pinmux | `dakota_gpio_pinconfig` call (DISASM); body UNKNOWN; OEM live FUNC_SEL 2/3 captured | none (mainline pinctrl has no PCM function; Linux shows MUX UNCLAIMED) | MISSING — needs the TLMM `FUNC_SEL` write path; gated (Q31/Q77) |
| 7 | Slave clock config | clksel(2), dummy rates, no GCC audio clock (GPL) | `fon_c2.c` writes STEREO/TDM_CTRL bits; clock provider absent in mainline | PARTIAL — external-pad-clock selection inside ADSS (`0x18`/clksel) not yet modelled; C3 gate |
| 8 | STEREO/TDM registers | STEREO0/3 RMW + `0x1c` = `0x06070007` (GPL) | `fon_c2_bits.h` + C2 writes with restore | MATCH at register level (C2 not yet executed on this board) |
| 9 | DMA descriptors/IRQ | mbox0/mbox3, 16 descriptors, INTID 188/191 (GPL/DT/OEM-LOG) | `fon_dma.c` prepares buffers, never starts DMA; descriptor struct layout not modelled | PARTIAL — ring prep matches the frame model; actual descriptor programming MISSING (`dma_start` = `-EOPNOTSUPP`) |
| 10 | Frame geometry + EOR#2 | raw-memory model proven (DISASM); wire order UNKNOWN | `fon_tdm.c` builds the exact raw frame (control at byte `0x08`, rails, hdr08 `0x5555` default) | MATCH at the memory level; physical presentation UNKNOWN (Q74) |
| 11 | Slot-5 control/status | `build_slic_ctrl`/`PutRxDMA` (DISASM) | `fon_tdm_frame_set_control/get_status` + `tools/fon-slot5-protocol` | MATCH on the Linux side; SC14448-side interpretation UNKNOWN (Q16/Q17/Q75) |
| 12 | Upper stack | `isdn_fbox_fon5`/`avm_dect` (closed) | `src/mock` userspace models (dect_io/avm_dect/pcmlink chain) | PARTIAL — Asterisk needs the FON device ABI; mock models the boundary, no kernel implementation |

---

## 4. Minimal-risk first-test operation list

Ordered; each step is gated, reversible, and already documented in the
referenced runbooks. **Nothing here authorizes execution** — it is the
sequence the next hardware stage must follow once separately approved.

| # | Operation | Gate / precondition | Rollback | Reference |
|---|---|---|---|---|
| T1 | Load `fon_tdm_drv.ko` with `probe_only=1` on the normal OpenWrt image (FON node `disabled`) | bench kit, serial console, recovery image | `rmmod`; no MMIO/clock/reset/DMA by construction | `runbook/fon-first-hardware-test.md` |
| T2 | Probe-only on the **901 test image** (FON node `okay`) — verify platform-device bind, resource list, `/proc/iomem` unchanged | T1 clean; separate test image; recovery route | node stays probe-only | `runbook/fon-first-hardware-test.md` |
| T3 | Read-only TLMM software probe (C0+) for FSC/BCLK presence on the known OEM mux pins | separate review; `CONFIG_DEVMEM=y` test kernel or one-shot kernel probe; no writes | none (read-only) | `runbook/fon-stage-c0plus-*-probe.md` |
| T4 | Passive scope on an identified TDM net (continuity first, unpowered) — confirm/deny FSC 8 kHz and BCLK ≈1.024 MHz under OpenWrt **with and without** the OEM firmware answer | T3 negative or inconclusive; net identified | none (passive) | `runbook/fon-tdm-passive-test.md`, `docs/fon-tdm-control-only-plan.md` |
| T5 | Bounded C1: map ADSS, enable AHB clock, assert/deassert `GCC_AUDIO_BCR`, first `readl(0x30)`, readback, rollback | T1/T2 clean; C1 authorization | re-assert reset, disable clock, unmap | `runbook/fon-stage-c1.md`, `docs/fon-adss-clock-reset.md` |
| T6 | Bounded C2: STEREO0/3 + `GLB_TDM_CTRL` + `CHIP_CTRL_I2S` + `I2S_RST` pulse writes with restore | C1 clean; C2 authorization | restore every written register; re-assert reset | `history/fon-adss-avm-init-sequence.md` |
| T7 | C3 dry-run: build AVM-shaped frames in DMA buffers; no DMA start, no IRQ | C2 clean | nothing armed | `src/fon-driver/README.md` |
| T8 | First active TDM (C4) | FSC/BCLK physically confirmed (T4); DMA start authorized; SC14448 known to be running (firmware question resolved by T4/OEM comparison) | `dma_start` currently `-EOPNOTSUPP` by design | blocked (K1/K2) |

The two facts the sequence is designed to establish before any active TDM:
**(a)** whether the SC14448 supplies FSC/BCLK under OpenWrt without the OEM
firmware upload (T3/T4 — this decides whether the upload path, Q79/Q80 and
the reset path must come first), and **(b)** whether the ADSS block answers
register traffic after the C1 clock/reset sequence (T5).

---

## 5. Reproducibility inputs (all offline)

| Input | Location / SHA |
|---|---|
| OEM bootlog reference | committed `docs/history/wiki-fritzos-oem-bootlog-reference.txt` |
| `S11-piglet`, `rc.voip`, `E41-capi` | `reference/oem-08.25/extracted/init-scripts/` (workspace manifest verified by `tools/verify-workspace.sh`) |
| `pcmlink.ko` | `6620510bc1d4b0f4d670e1e93d3f308dc3002785d3129521156eb5e1bc4a363b` |
| `isdn_fbox_fon5.ko` | `47e0e29bbdc4e76738f2d893c4c587ec7dd7aa99f543a035140561ed90dbd2c9` |
| AVM GPL ADSS source | `reference/sources/avm/avm-gpl/…/sound/soc/qcom/ipq/ipq-adss-avm.c` (manifest) |
| HW236 DTB (first blob) | SHA `3083e2acedc800015fea5ee7e57fa6cc8da551e21ee792095cbd8a7224bb841f` |
| SC14448 images | `7cac33c7…b31` (normal), `6361384d…860` (p2test) |
| 08.25 read-only console capture | `evidence/oem-08.25/console/2026-11-08/` (manifest) |

---

## 6. What this model does NOT prove

* the SC14448-side interpretation of slot 5 (Q16/Q17/Q75) and the
  physical wire order (Q74);
* `fs_per_dma` (Q76), the `dakota_gpio_pinconfig`/`dakota_gpio_out_bit`
  bodies, the PINMUX mapping under OpenWrt (Q31/Q77);
* that FSC/BCLK exist on this board under OpenWrt without the OEM
  upload — this is the very thing T3/T4 measure;
* the console/DECT UART arbitration for a future uploader (Q79).
