# ADSS clock and reset dependency (IPQ4019)

> **Status: research document.**
> Evidence for `docs/fon-known-facts.md`; operational steps live in
> `runbook/fon-stage-c1.md`.  Everything here is read from source: no
> hardware was touched to write it.

Question answered: what must be true before any read of the ADSS
(`0x07700000`) register block can be considered safe.

---

## 1. What exists in Linux 6.12 for this block

### 1.1 GCC clocks

Binding header: `include/dt-bindings/clock/qcom,gcc-ipq4019.h`

| Macro | Value | Driver descriptor | Register | Bit |
|---|---|---|---|---|
| `AUDIO_CLK_SRC` | 1 | `audio_clk_src` (RCG, parent XO/FEPLL200) | `0x1b000` | n/a |
| `GCC_AUDIO_AHB_CLK` | 19 | `gcc_audio_ahb_clk` (branch, parent `pcnoc_clk_src`) | `0x1b010` | `BIT(0)` |
| `GCC_AUDIO_PWM_CLK` | 20 | `gcc_audio_pwm_clk` (branch, parent `audio_clk_src`) | `0x1b00c` | `BIT(0)` |

Source: `drivers/clk/qcom/gcc-ipq4019.c` lines 506-550, registered in
`gcc_ipq4019_clocks[]` (lines 1572-1592).

`GCC_AUDIO_AHB_CLK` is the bus clock for the audio/ADSS block; it gates
access to the register window.  `GCC_AUDIO_PWM_CLK` exists for audio PWM
output and is not part of the TDM path.

### 1.2 Reset line

There is **no** `dt-bindings/reset/qcom,gcc-ipq4019.h` in 6.12.  The reset
IDs live in the clock header:

| Macro | Value | Reset map entry | Register | Bit |
|---|---|---|---|---|
| `GCC_AUDIO_BCR` | 44 | `[GCC_AUDIO_BCR] = {0x1B008, 0}` | `0x1B008` | 0 |

Source: `include/dt-bindings/clock/qcom,gcc-ipq4019.h:140` and
`drivers/clk/qcom/gcc-ipq4019.c:1689`.  The controller is registered by
`common.c` (`devm_reset_controller_register`, lines 290-310) from the same
`gcc` node that provides the clocks, which has `#reset-cells = <1>`
(`qcom-ipq4019.dtsi`, `clock-controller@1800000`).

Mainline names it `GCC_AUDIO_BCR`; AVM's tree names the same bit
`AUDIO_BLK_ARES`.

### 1.3 What the board DTS says today

`qcom-ipq4019-fritzbox-7530.dts`, node `fon-tdm@7700000`, has **no**
`clocks`, `clock-names`, `resets` or `reset-names` properties.  The node
parses resources and IRQs only.  The base `qcom-ipq4019.dtsi` has no audio
node at all.

Consequence: nothing in the current tree claims the audio AHB clock or the
audio BCR.  That matches the Stage A capture, where all three audio clocks
show `enable_count = 0`, `hardware enable = N`, consumer `deviceless`.

---

## 2. What AVM's GPL driver does

File: `avm-gpl/sources/kernel/linux/sound/soc/qcom/ipq/ipq-adss-avm.c`.

`intf_audio_adss_probe` (lines 560-580) runs, in this order:

1. `devm_ioremap_resource()` of `0x7700000` (size `0x34`) — map first;
2. `devm_reset_control_get(&pdev->dev, "blk_rst")`;
3. `gcc_audio_blk_rst()`: `reset_control_assert()`,
   `usleep_range(20000, 24000)`, `reset_control_deassert()`;
4. `adss_glb_i2s_interface_en(ENABLE)` → read-modify-write of `0x10` `BIT(0)`;
5. `adss_glb_audio_mode_B1K()` → read-modify-write of `0x30` `BIT(28)`.

Order proven by the source: **map → reset assert/deassert → MMIO.**

What it does **not** do: it never enables `GCC_AUDIO_AHB_CLK` or
`GCC_AUDIO_PWM_CLK`.  There is no `clk_get`/`clk_prepare_enable` for any GCC
audio clock anywhere in the driver.  The vendor DTS gives the audio node only
`resets = <&gcc AUDIO_BLK_ARES>` — no `clocks` property either:

```dts
audio: audio@7700000 {
	compatible = "qca,ipq4019-audio-adss";
	reg = <0x7700000 0x34>, <0x7707000 0x20>;
	resets = <&gcc AUDIO_BLK_ARES>;
	reset-names = "blk_rst";
};
```

The clocks the driver does request belong to a **separate ADCC provider**,
not to GCC:

| Consumer | Literal | Purpose |
|---|---|---|
| `pcm@7704000` | `"audio_pcm_clk"` | PCM clock; `clk_prepare_enable` is commented out in AVM code |
| `tdm` | `"audio_tx_bclk"`, `"audio_tx_mclk"`, `"audio_rx_bclk"`, `"audio_rx_mclk"` | BCLK/MCLK; enabled only in master mode |

In slave mode the driver deliberately sets dummy rates (252/254/255) so the
ADCC selects the **external pad clock** supplied by the SC14448
(`adss_config_clk`, lines 2050-2096), and programs `MASTER = 0`
(`STEREO_CONFIG_MASTER`, `ipq-adss.h:191`).

---

## 3. Does the AHB clock gate register access?

**Proven by source: no one toggles it, so source alone cannot prove either
way.**  AVM maps the window and immediately asserts/deasserts the block reset,
then does `readl`/`writel`.  If the bus clock were required, that sequence
would fault in production and it does not.

Two readings remain open and must not be presented as fact:

1. `GCC_AUDIO_AHB_CLK` may be enabled implicitly by the bootloader or by a
   boot-time consumer that later disappears (the Stage A capture shows count
   0 *now*, not at boot);
2. the block may accept register traffic while its clock is gated, and only
   the TDM/DMA datapath needs the clock.

Neither is confirmed.  This is exactly why Stage C1 is gated: the first
MMIO read must be reversible and observable.

### 3.1 Can a gated-clock MMIO access hang the bus?

A read of a peripheral whose clock is gated usually returns `0xFFFFFFFF` or
raises a synchronous external abort.  An abort is recoverable (the faulting
instruction is in our own driver, not in an interrupt); a bus lock-up is not.
The IPQ4019 NOC does not document a timeout that we can rely on.

Consequence: a probe-only driver must **never** perform the first MMIO read
without (a) a way to see the fault, and (b) a documented rollback.  This is
the reason C1 is a separate, explicitly authorised stage.

---

## 4. Minimum preparation sequence

Derived from the AVM order plus the mainline API.  **Nothing here has been
run on hardware.**

| Step | Action | API / register | Reversible? |
|---|---|---|---|
| 1 | Map the ADSS window | `devm_ioremap()` of resource 0 | yes, `devm` |
| 2 | Get the AHB clock | `devm_clk_get(&pdev->dev, NULL)` with `clocks = <&gcc GCC_AUDIO_AHB_CLK>` added to DT | yes |
| 3 | Enable the AHB clock | `clk_prepare_enable()` | yes, `clk_disable_unprepare()` |
| 4 | Get the reset line | `devm_reset_control_get(&pdev->dev, NULL)` with `resets = <&gcc GCC_AUDIO_BCR>` | yes |
| 5 | Assert + deassert (20-24 ms) | `reset_control_assert()` / `reset_control_deassert()` | yes, re-assert releases the block |
| 6 | First MMIO read | `readl(base + 0x30)` etc. | read only |
| 7 | Rollback | re-assert reset, `clk_disable_unprepare()`, unmap | yes |

Step 3 is a **hardware write** (`0x181b010` bit 0) and step 5 writes
`0x181b008` bit 0.  Neither is passive diagnostics; both belong to Stage C1,
not C0.

Note the ordering difference to AVM: AVM relies on the reset to bring the
block up without touching the AHB gate.  Our sequence adds the gate *before*
the reset, because mainline access to a gated block is not proven safe and
enabling the clock first is the conservative order.

### 4.1 Register addresses for the future test

| Symbol | Offset | Absolute | Purpose |
|---|---|---|---|
| `ADSS_GLB_PCM_RST` | `0x00` | `0x07700000` | PCM reset control |
| `ADSS_GLB_CHIP_CTRL_I2S` | `0x10` | `0x07700010` | interface enable `BIT(0)` |
| `ADSS_GLB_I2S_RST` | `0x14` | `0x07700014` | per-block reset bits |
| `ADSS_GLB_CLK_I2S_CTRL` | `0x18` | `0x07700018` | BCLK/MCLK output enables |
| `ADSS_GLB_TDM_CTRL` | `0x1c` | `0x0770001c` | channel/sync counts, delays |
| `ADSS_GLB_AUDIO_MODE` | `0x30` | `0x07700030` | TDM/I2S select, `B1K BIT(28)` |
| `STEREO0_CONFIG` | `0x00` in its own window at `0x07709000` | `MASTER BIT(8)`, `ENABLE BIT(21)` |
| `STEREO3_CONFIG` | `0x00` in its own window at `0x0770f000` | same layout |

**Correction (2026-11-07).** An earlier revision of this document listed
STEREO0/STEREO3 at `0x07708000`/`0x0770c000`.  That was wrong: those are the
MBOX windows (`mbox0` at `0x07708000`, `mbox2` at `0x0770c000`).  The audio
windows in AVM's `qcom-ipq4019-audio.dtsi` are:

| Block | Address | AVM node |
|---|---|---|
| MBOX0 | `0x07708000` | `mbox0` |
| MBOX1 | `0x0770a000` | `mbox1` |
| MBOX2 | `0x0770c000` | `mbox2` |
| MBOX3 | `0x0770e000` | `mbox3` |
| STEREO0 | `0x07709000` | `stereo0` (`STEREO0_ID`) |
| STEREO1 | `0x0770b000` | `stereo1` (`STEREO1_ID`) |
| STEREO2 | `0x0770d000` | `stereo2` (`STEREO2_ID`) |
| STEREO3 | `0x0770f000` | `stereo3` (`STEREO3_ID`) |

The board DTS in this project is correct: `stereo_tx = 0x07709000`
(STEREO0) and `stereo_rx = 0x0770f000` (STEREO3), so Stage C2 wrote to the
STEREO windows and never to an MBOX block.

Remaining discrepancy worth noting: AVM's **PCM** node pairs
`dma-tx-channel = MBOX3_TX` with `stereo-tx-port = STEREO3` and
`dma-rx-channel = MBOX0_RX` with `stereo-rx-port = STEREO0`, i.e. TX uses
box/port 3 and RX uses 0.  Our node uses TX on 0 and RX on 3.  Which pairing
the FON path actually needs is **unresolved** and belongs to Stage C3; it
does not affect the C2 register writes, which only touched STEREO0/3
format bits.

---

## 5. What Stage C0 can prove without writing

C0 may read:

- DT (`clocks`, `resets`, `pinctrl` presence on the FON node);
- `/proc/iomem`, `/proc/interrupts`, `/proc/consoles`;
- `/sys/kernel/debug/clk/clk_summary` (see the caveat in the C0 runbook:
  this file is generated from cached clock state, but some providers read
  hardware on demand);
- `/sys/kernel/debug/pinctrl/*`;
- `dmesg`.

C0 must **not** enable a clock, assert/deassert a reset, `ioremap` plus
`readl`, or start DMA.

---

## 6. Open questions this document does not close

| # | Question | Blocks |
|---|---|---|
| 1 | Is `GCC_AUDIO_AHB_CLK` required for ADSS register access? | C1 gate |
| 2 | Who owned the audio clock at boot, if anyone? | C1 rationale |
| 3 | Does the ADCC provider exist in mainline 6.12? | master-mode TDM only |
| 4 | TX/RX port pairing: AVM uses MBOX3/STEREO3 for TX, our node uses 0 | C3 |
| 5 | Is a bus abort recoverable on this NOC? | C1 safety |
