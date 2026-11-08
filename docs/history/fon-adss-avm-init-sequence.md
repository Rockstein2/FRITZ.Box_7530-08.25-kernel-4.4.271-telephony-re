# AVM ADSS/TDM initialisation sequence

> **Status: source reconstruction plus hardware-confirmed values.**
> Everything marked *AVM* comes from `reference/sources/avm/avm-gpl/.../sound/soc/qcom/ipq/ipq-adss-avm.c`
> and `ipq-adss.h`.  Everything marked *HW* was observed on the board in
> Stage C1/C2.  Anything else is labelled as unproven.

---

## 1. What AVM actually does, in order

### 1.1 `intf_audio_adss_probe` (adss node)

```c
res = platform_get_resource(pdev, IORESOURCE_MEM, 0);
avm_adss_audio_local_base = devm_ioremap_resource(...);   /* map first */
audio_blk_rst = devm_reset_control_get(&pdev->dev, "blk_rst");
gcc_audio_blk_rst();      /* assert, 20-24 ms, deassert */
adss_glb_i2s_interface_en(ENABLE);   /* 0x10 bit 0 */
adss_glb_audio_mode_B1K();           /* 0x30 bit 28 set */
```

Two facts matter here that our C2 originally missed:

1. **`ADSS_GLB_CHIP_CTRL_I2S` (`0x10`) is enabled during ADSS probe**, before
   any TDM or stereo configuration.  `AUDIO_MODE` alone does not open the
   interface.
2. **`AUDIO_MODE` bit 28 (`B1K`) is set at probe time**, not together with
   the TDM configuration.

### 1.2 `adss_config_clk(ext_clk, bclk, mclk)` (TDM setup)

- `adss_glb_i2s_reset()` -> writes `i2s_reset_val` to `0x14`, 4-5 ms, writes
  `0x0` (a pulse, so `0x14` ends at zero).  *AVM*
- slave path (`ext_clk != 0`): `adss_config_clksel(2)` — selects the external
  pad clock.  *AVM*
- master path: four `clk_set_rate` + `clk_prepare_enable` on the ADCC
  BCLK/MCLK clocks, which mainline 6.12 does not provide.  *AVM*

### 1.3 `adss_config_tdm(enable, master, ext_clk)`

Read-modify-write of `STEREO0_CONFIG` and `STEREO3_CONFIG`:

```text
cleared : MASTER | ENABLE | DATA_WORD_SIZE | I2S_WORD_SIZE_32 |
          MIC_WORD_SIZE_32 | MCK_SEL
set     : DATA_WORD_SIZE(1) | I2S_WORD_SIZE_16 | MIC_WORD_SIZE_16
set if master  : MASTER
set if enable  : ENABLE
set if ext_clk : MCK_SEL      /* ohne dieses Bit wird extclk zerstoert */
```

Note `DATA_WORD_SIZE(1)`, not `(0)`: AVM's comment says "only 16-Bit-Mode"
but the constant is `(1) << 12`.

### 1.4 `ADSS_GLB_TDM_CTRL` (0x1c)

Not written in `adss_config_tdm`.  The channel fields are computed where the
TDM link is configured, as `GLB_TDM_CTRL_TX_CHAN_NUM(slots - 1)` and the RX
equivalent, with `GLB_TDM_CTRL_TX_DELAY`/`RX_DELAY` set for the FON path.
*AVM*

---

## 2. Register table

| Register | Reset (HW) | AVM writes | Required for FON | In C2 (old) |
|---|---|---|---|---|
| `ADSS_GLB_PCM_RST` `0x00` | unknown | `GLB_PCM_RST_CTRL(x)` | likely yes | **no** |
| `ADSS_GLB_CHIP_CTRL_I2S` `0x10` | unknown | `INTERFACE_EN` `BIT(0)` | **yes** | **no** |
| `ADSS_GLB_I2S_RST` `0x14` | `0x00000000` (HW) | pulse `0xF` then `0x0` | yes | **no** |
| `ADSS_GLB_CLK_I2S_CTRL` `0x18` | `0x00000000` (HW) | OE bits only in master mode | no (slave) | no (correct) |
| `ADSS_GLB_TDM_CTRL` `0x1c` | `0x00010001` (HW) | chan num, delays | **yes** | yes |
| `ADSS_GLB_AUDIO_MODE` `0x30` | `0x00000000` (HW) | `B1K` at probe, TDM bits later | **yes** | partly |
| `STEREO0_CONFIG` `0x00` @ `0x07709000` | `0x00000102` (HW) | slave, 16-bit, MCK_SEL, ENABLE | **yes** | yes |
| `STEREO3_CONFIG` `0x00` @ `0x0770f000` | `0x00000102` (HW) | same | **yes** | yes |

---

## 3. Was C2 correct?

| Item | Verdict |
|---|---|
| TDM_CTRL value `0x06070007` | **correct**: `(8-1)` in both fields plus both delays |
| STEREO values | **close but not exact**: C2 wrote `0x00240000` and did not set `DATA_WORD_SIZE(1)` (= `BIT(12)`), so the data word size stayed at its cleared value instead of AVM's 16-bit setting |
| `CHIP_CTRL_I2S` | **missing in the executed C2**; added in this revision |
| `I2S_RST` pulse | **missing**; added in this revision |
| `AUDIO_MODE` | the executed value `0x10000005` was coherent, but the duplicated `BIT(0)` in the source was a typo, not a feature: `BIT(0)` *is* the XMIT TDM bit |
| Addresses | correct (see the STEREO table below) |

The corrected C2 now writes `CHIP_CTRL_I2S`, pulses `I2S_RST`, uses
`DATA_WORD_SIZE(1)`, and derives `AUDIO_MODE` through a helper that sets each
bit once.

---

## 4. STEREO / MBOX address map

| Block | Address | AVM node | AVM id |
|---|---|---|---|
| MBOX0 | `0x07708000` | `mbox0` | `MBOX0_TX_ID` / `MBOX0_RX_ID` |
| MBOX1 | `0x0770a000` | `mbox1` | `MBOX1_*` |
| MBOX2 | `0x0770c000` | `mbox2` | `MBOX2_*` |
| MBOX3 | `0x0770e000` | `mbox3` | `MBOX3_*` |
| STEREO0 | `0x07709000` | `stereo0` | `STEREO0_ID` |
| STEREO1 | `0x0770b000` | `stereo1` | `STEREO1_ID` |
| STEREO2 | `0x0770d000` | `stereo2` | `STEREO2_ID` |
| STEREO3 | `0x0770f000` | `stereo3` | `STEREO3_ID` |

Our board DTS names `stereo_tx = 0x07709000` and `stereo_rx = 0x0770f000`,
so C2 wrote STEREO0 and STEREO3 and never touched an MBOX window.

**Open discrepancy:** AVM's PCM node uses TX on MBOX3/STEREO3 and RX on
MBOX0/STEREO0; our node uses TX on 0 and RX on 3.  Which pairing the FON
needs is unresolved and belongs to C3.

---

## 5. What is still needed for a correct slave TDM

| Requirement | Status |
|---|---|
| AHB clock on | proven (C1: 100 MHz) |
| block reset pulse | proven |
| interface enable (`0x10`) | implemented in this revision, **not yet run** |
| `I2S_RST` pulse (`0x14`) | implemented in this revision, **not yet run** |
| 8 slots | proven written and read back |
| STEREO slave + 16-bit + MCK_SEL | proven written; the `DATA_WORD_SIZE(1)` bit was **not** set in the executed run |
| external BCLK/FSC from SC14448 | **unproven** (Q27) |
| ADCC clock provider (master mode) | absent in mainline 6.12; not needed for slave |

---

## 6. Nothing here was executed

This revision changes code and tests only.  No `insmod`, no MMIO, no reset
cycle and no clock toggle was performed.
