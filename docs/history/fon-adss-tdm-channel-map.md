# C3 — ADSS TDM channel and DMA mapping for the 7530 FON

> **Status: historical analysis.**
> This document records the reasoning and evidence as of the date it was
> written.  Some of its `UNKNOWN` / `UNVERIFIED` markers have since been
> answered.
> - Current confirmed facts: `../fon-known-facts.md`
> - Current open questions: `../fon-open-questions.md`
> - This file is kept for the reasoning trail, not as a status report.

> **Scope: static source/DTB analysis + offline dry-run.**  No router was
> touched, no DMA was started, no MMIO was written in this iteration.
>
> This document answers "which MBOX/stereo/IRQ does the FON actually use?"
> It does **not** repeat the Stage-5 pcmlink register-path reversal
> (`fon-pcmlink-register-path.md`) and does not claim that the
> SC14448 has ever been observed receiving a frame.

Status legend: `CONFIRMED` (read directly from published GPL source, the
decompiled DTB, or an OEM runtime log), `INFERRED` (consistent analysis, not
directly proven), `UNKNOWN`, `DISPROVED`.

---

## 0. Bottom line

The 7530 DTB contains **two** QCA audio descriptions that point at
**opposite** MBOX/stereo pairs.  Picking the wrong one is the single most
likely way to get C3 wrong, so it is stated first:

| Node | `dma-tx` | `dma-rx` | `stereo-tx` | `stereo-rx` | Used by |
|---|---|---|---|---|---|
| `tdm@0` (`qca,ipq4019-tdm`) | 0 (`MBOX0_TX`) | 7 (`MBOX3_RX`) | **0** | **3** | **the FON / pcmlink path** |
| `pcm@7704000` (`qca,ipq4019-pcm`) | 6 (`MBOX3_TX`) | 1 (`MBOX0_RX`) | 3 | 0 | not the FON path |

`pcmlink.ko` is the vendor `ipq40xxtdm_*` backend, i.e. the **TDM**
description.  Both the OEM boot log and the compiled DTB agree on the TDM
values.

So the FON mapping is:

| Direction | MBOX block | Stereo block | IRQ |
|---|---|---|---|
| IPQ → SC14448 (playback / TX) | `mbox@7708000`, index **0** | `stereo@7709000`, index **0** | `GIC_SPI 156` → INTID **188** |
| SC14448 → IPQ (capture / RX) | `mbox@770e000`, index **3** | `stereo@770f000`, index **3** | `GIC_SPI 159` → INTID **191** |

**This matches the values already recorded in `../fon-known-facts.md`** (TX
channel 0 / RX 7, stereo 0 / 3) and the OEM `intf_tdm_probe` log.  The
`stereo-tx-port = 3` seen in the DTB belongs to the **`pcm@7704000`** node,
which is *not* the FON path.

> **Correction history.**  A first draft of this document read
> `pcm@7704000` and concluded the mapping was "crossed".  That was wrong:
> `tdm@0` is the node in use.  The error is recorded here because the two
> nodes look similar and the mistake is easy to repeat.

## 1. Why `stereo` and not `dma-*-channel` selects hardware

`reference/sources/avm/avm-gpl/sources/kernel/linux/sound/soc/qcom/ipq/ipq-adss-avm.c:2188`
`tdm_if_adss_dma_init()`:

```c
res  = mbox_dma_init(&mbox_dma[PLAYBACK], refhandle, TxData, ...,
                     tdm_priv.stereo_tx, PLAYBACK,
                     only_rxirq ? -1 : mbox_data[tdm_priv.stereo_tx].irq, ...);
res |= mbox_dma_init(&mbox_dma[CAPTURE], refhandle, RxData, ...,
                     tdm_priv.stereo_rx, CAPTURE,
                     mbox_data[tdm_priv.stereo_rx].irq, ...);
```

- The `dma_id` argument is `stereo_tx` / `stereo_rx` (lines 2208, 2216).
- The IRQ is `mbox_data[stereo_tx].irq` / `mbox_data[stereo_rx].irq`.
- `mbox_dma_init()` stores it as `pmbox_dma->dma_id` (line 1043), and
  `mbox_dma_prepare_reg()` writes registers through `MBOX_IO(dma_id, ...)`
  → `mbox_data[dma_id].reg_base` (lines 1352-1377).

`grep -n 'mbox_tx\|mbox_rx' ipq-adss-avm.c` returns only lines 191-192
(field declarations), 1540/1547 (DT read) and 1571/1573 (a log).  There is no
other use: **`dma-tx-channel` never selects hardware.**  It is a label.

Consequence: `stereo-tx-port`/`stereo-rx-port` are the numbers that must be
right.  `CONFIRMED`.

## 2. Evidence: the compiled HW236 DTB

Source: OEM `vmlinux` (`/tmp/opencode/fw825/var/tmp/kernel.image`), FDT at
offset `0x98d038`, SHA256 `3083e2acedc800015fea5ee7e57fa6cc8da551e21ee792095cbd8a7224bb841f`.

```
tdm@0 {
        compatible = "qca,ipq4019-tdm";
        dma-tx-channel = <0x00>;
        dma-rx-channel = <0x07>;
        stereo-tx-port = <0x00>;
        stereo-rx-port = <0x03>;
        clocks = <0x15 0x07 0x15 0x05 0x15 0x09 0x15 0x03>;
        clock-names = "audio_tx_bclk\0audio_tx_mclk\0audio_rx_bclk\0audio_rx_mclk";
        status = "ok";
};

pcm@7704000 {
        compatible = "qca,ipq4019-pcm";
        reg = <0x7704000 0x2000>;
        dma-tx-channel = <0x06>;
        dma-rx-channel = <0x01>;
        stereo-tx-port = <0x03>;
        stereo-rx-port = <0x00>;
        clocks = <0x15 0x0b>;
        clock-names = "audio_pcm_clk";
        status = "ok";
};
```

Both are `ok`, but they select different hardware.  The FON path is the
`tdm` one (see §3).

MBOX nodes:

| Node | `dma-index` | `tx-channel` | `rx-channel` | IRQ |
|---|---|---|---|---|
| `mbox@7708000` | 0 | 0 | 1 | `GIC_SPI 156` |
| `mbox@770a000` | 1 | 2 | — | `GIC_SPI 157` |
| `mbox@770c000` | 2 | 4 | — | `GIC_SPI 158` |
| `mbox@770e000` | 3 | 6 | 7 | `GIC_SPI 159` |
| `mbox@7706000` | 4 | — | 9 | `GIC_SPI 163` |

STEREO nodes:

| Node | `stereo-index` |
|---|---|
| `stereo@7709000` | 0 |
| `stereo@770b000` | 1 |
| `stereo@770d000` | 2 |
| `stereo@770f000` | 3 |

So `stereo-tx-port = 0` → `stereo@7709000`, `mbox@7708000`, IRQ 156.
`stereo-rx-port = 3` → `stereo@770f000`, `mbox@770e000`, IRQ 159.

## 3. Evidence: the OEM runtime log

`docs/history/fon-oem-bootlog-crosscheck.md:126-135` records FRITZ!OS
printing its own probe result:

```text
intf_tdm_probe: ena: dma-tx-channel=0 stereo-tx-port=0
               ena: dma-rx-channel=7 stereo-rx-port=3
```

This is the strongest single piece of evidence: it is the running kernel's
reported configuration, not a source reading.  It agrees with `tdm@0`.

The same log gives the clocks:

```text
[piglet]TDM: FS: 8000 Hz CLK: 1025720 Hz
```

Two numbers already in `fon-known-facts.md:195-196` must not be conflated:

| Quantity | Value | Origin |
|---|---|---|
| BCLK formula (master) | 1 024 000 Hz | GPL |
| BCLK measured on FRITZ!OS | **1 025 720 Hz** (+0.17 %) | OEM |

The 7530 runs as **slave** (§4.2), so `bclk = 254` is a sentinel meaning "use
`bclk_pad_in`" and no numeric rate is programmed.  The measured 1 025 720 Hz
is the SC14448-supplied clock; it is a sanity baseline, not a tuning target.

## 4. TDM configuration the AVM firmware applies

### 4.1 Frame geometry

`__tdm_if_config_init()` (`ipq-adss-avm.c:2050`) is called by
`tdm_if_adss_config_init(slots, rxdelay, txdelay, master)` (line 2110).
`notes/pcmlink.md:160-188` recovered the call site in `pcmlink.ko`:

```text
tdm_if_config_init(slot_size, tx_slots, rx_slots, config)
tdm_if_dma_init(handle, TxData, RxData, 1, 1, slot_size, slot_ratio, 16)
```

with `slot_size` = 8 or 16 and `desc_num = 0x10` (16).

`slots = 8` at runtime is `INFERRED` (OEM "only 8 tested", our DTS, and the
log above are consistent; no runtime readback of the `ch_num` field with the
AVM configuration has been taken on our board).

### 4.2 Master/slave and clock source

```c
if (pconf->master == 1) {
        bclk = pconf->slots * BITS_PER_BYTE * sizeof(short) * 8000;
        mclk = bclk * 4;
        extclk = 0;
} else {
        mclk = (is_IPQ807x() ? 252 : 255);
        bclk = 254;
        extclk = 1;
}
```

`BITS_PER_BYTE * sizeof(short)` = 16, so the master formula gives
`8 * 16 * 8000 = 1 024 000 Hz` and MCLK = 4.096 MHz.

The 7530 is **slave**: `master = 0` takes the pad clocks.  This is the code
behind the existing fact "ADSS is slave, SC14448 supplies BCLK/FSC".

### 4.3 Register order

From `__tdm_if_config_init`, inside `local_irq_save`:

```text
adss_config_clk(extclk, bclk, mclk)
adss_glb_tdm_ctrl_ch_num(slots - 1)
adss_glb_clk_enable_oe(master, CAPTURE)
adss_glb_clk_enable_oe(master, PLAYBACK)
adss_glb_rxtx_data_port_en(1)
adss_glb_rxtx_framesync_port_en(1)
adss_glb_tdm_mode()
adss_config_tdm(DISABLE, master, extclk)
adss_glb_tdm_ctrl_sync_num(0, CAPTURE)
adss_glb_tdm_ctrl_sync_num(0, PLAYBACK)
adss_glb_tdm_ctrl_delay(rxdelay, CAPTURE)
adss_glb_tdm_ctrl_delay(txdelay, PLAYBACK)
```

TDM is **disabled** here; enabling happens in the start path, not in config.
`rxdelay`/`txdelay` are 1 bit clock per the existing fact table.

## 5. TX/RX transport

`tdm_if_adss_dma_start()` (`ipq-adss-avm.c:2234`):

```text
workarround_reset_tdm_interface()
mbox_dma_prepare_desc(PLAYBACK); mbox_dma_prepare_reg(PLAYBACK)
mbox_dma_prepare_desc(CAPTURE);  mbox_dma_prepare_reg(CAPTURE)
local_irq_save()
mbox_dma_start(PLAYBACK)
mbox_wait_for_dma_completion(PLAYBACK)
udelay(125)
mbox_dma_start(CAPTURE)
local_irq_restore()
```

TX is started first and one completion is awaited before RX starts; the
source comment explains that the TDM FIFO swallows ~800 µs of data.  Our
`dma_start` sysfs action refuses with `-EOPNOTSUPP`, so this ordering is
**not** yet implemented and must be before any C4 test.

### 5.1 Buffer sizing

`mbox_dma_init()` (`ipq-adss-avm.c:1017-1019`):

```c
DMABufferSize      = slots * sizeof(short) * fs_per_dma;
DescriptorPoolSize = L1_CACHE_ALIGN(ndescs * desc_size);
AlignedBufferSize  = L1_CACHE_ALIGN(DMABufferSize);
DMAPoolSize        = DescriptorPoolSize + 2 * AlignedBufferSize;   /* ping-pong */
```

Two ping-pong buffers, `ndescs` descriptors (16 for the FON call site).  Our
`fon_dma.h` uses the same `16` descriptors and the same 28-bit mask, so ring
geometry is already compatible.

### 5.2 `fs_per_dma` — what is actually known

`tdm_if_adss_dma_init(ref, TxData, RxData, cpu, only_rxirq, slots,
fs_per_dma, desc_num)` maps to the call site as:

| Argument | FON call site |
|---|---|
| `cpu` | `1` |
| `only_rxirq` | `1` (shared TX/RX interrupt) |
| `slots` | `slot_size` (8 or 16) |
| `fs_per_dma` | **`slot_ratio`** = `uidiv([r5+0], [r5+8])` |
| `desc_num` | `0x10` = 16 |

So the number of frames per DMA buffer is **not a literal 32**: it is the
`slot_ratio` value computed inside `pcmlink.ko`.  `slot_ratio` has not been
decoded to a number.

The GPL doc comment at `ipq-adss-avm.c:2178` says *"fs_per_dma: count of
framesyncs for one dma-buffer (4 ms == 32)"*, and 4 ms at 8 kHz is exactly
32.  That describes the **intended** value, not necessarily the value passed.

Status: **UNRESOLVED (Q76)**.  Finding `fs_per_dma` is `[r5] / [r5+8]` means
the value is a ratio of board-config numbers, and those numbers are not in
the GPL drop.  A literal 32 is *not* established for the FON path; it is only
this offline driver's own constant (`FON_DMA_FRAMES_PER_BUFFER`) and the
example in the GPL comment.  Consequences if 32 is wrong: the ping-pong half
would not be 4 ms, so buffer size and DMA-relative timing differ.  It does
**not** change the slot-5 byte offset, which is per-frame.

For a dry-run the difference is harmless because no DMA runs.  Before C4 it
must be settled from the 7530 board-config table or a runtime `DBG_TRC_API`
readback of `tdm_if_adss_dma_init(... fs_per_dma=%u ...)`.

## 6. The control slot 5

Stage 5 established (`fon-pcmlink-register-path.md`):

| Fact | Status |
|---|---|
| TX control word at byte offset `0x0a` | `CONFIRMED` (`0x98cc..0x98e0`) |
| RX status word at byte offset `0x0a` | `CONFIRMED` (`0x9b38..0x9b90`) |
| `0x0a / 2 = 5` → physical slot 5 | `CONFIRMED` arithmetic |
| hook = RX status bit 3 → reg 0x44 bit 7 | `CONFIRMED` mapping |
| **SC14448 interprets slot 5 as claimed** | **UNKNOWN** |

The `0x0a / 2 = 5` arithmetic holds only for **16-bit slots**.  With 8-bit
slots, offset `0x0a` would be slot 10.  `INFERRED`, dependent on
`slots = 8`, 16-bit, and one frame per DMA transfer.

## 7. Differences between AVM and our driver

| Parameter | AVM (CONFIRMED) | Our DTS | Impact |
|---|---|---|---|
| MBOX block for TX | index 0, `0x7708000`, IRQ 156 | `mbox_tx = 0x07708000` | matches |
| MBOX block for RX | index 3, `0x770E000`, IRQ 159 | `mbox_rx = 0x0770E000` | matches |
| STEREO for TX | index 0, `0x7709000` | `stereo_tx = 0x07709000` | matches |
| STEREO for RX | index 3, `0x770F000` | `stereo_rx = 0x0770F000` | matches |
| TDM slots | 8 × 16-bit | `qcom,tdm-slots = <8>` | matches |
| BCLK/FSC direction | slave | driver assumes slave | matches |
| Control slot | 5 (`0x0a`) | `FON_TDM_CONTROL_SLOT 5` | matches |
| Descriptor count | 16 | 16 | matches |
| DMA mask | 28-bit | `0x0fffffff` | matches |
| `dma-tx/rx-channel` | informational only | not encoded | no action needed |
| Frames per DMA buffer | `fs_per_dma` | 32 (driver constant) | **UNRESOLVED (Q76)**, verify |

**The register-block mapping in our DTS is already correct.**  The one thing
that was genuinely wrong was the *draft of this document*, which read the
`pcm@7704000` node instead of `tdm@0`.

Remaining real gaps are behavioural, not mapping:

1. `dma_start` is unimplemented (`-EOPNOTSUPP`).
2. The TX-first / wait / RX ordering of §5 is not implemented.
3. `fs_per_dma` is not runtime-confirmed.

## 8. What this does not prove

| Question | Status |
|---|---|
| SC14448 actually receives the slot-5 word | **UNKNOWN** — no hardware observation |
| SC14448 actually drives BCLK/FSC on this board | **UNKNOWN** — Q4/Q27 |
| ADSS pads are muxed to the PCM pins | **DISPROVED for the current boot** — Stage C0 found `i2s_rx/tx/td` |
| `slots = 8` at runtime on our kernel | **INFERRED** |
| `fs_per_dma` in the FON call site | **UNRESOLVED** — it is `[r5] / [r5+8]`; the board numbers are closed |
| Exact SC14448 bit meaning of the control word | **UNKNOWN** |

The dominant open item is still **Q4/Q27**: until the SC14448 is shown running
and producing FSC/BCLK, the DMA side cannot be validated.

## 9. How to verify each open item

| Item | Method |
|---|---|
| SC14448 drives FSC/BCLK | passive scope: FSC 8 kHz, BCLK ≈ 1.0257 MHz |
| `slots = 8` at runtime | read `ADSS_GLB_TDM_CTRL` `ch_num` after an AVM-like setup |
| MBOX mapping on our kernel | prepare rings, read back descriptor base per block |
| `fs_per_dma` | compare our buffer fill time against 4 ms of audio |

See `../runbook/fon-tdm-passive-test.md` and the Stage D0 runbook.
