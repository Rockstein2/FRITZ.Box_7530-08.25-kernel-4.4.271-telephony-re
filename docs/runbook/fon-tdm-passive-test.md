# Passive TDM signal measurement (FSC / BCLK / DATA)

> **Status: measurement instruction, never executed.**
> No cable, probe or pin was touched to write this.  Nothing in this
> document changes pinmux, clocks or reset.

Purpose: decide, **without changing anything**, whether the Dialog SC14448 is
currently producing TDM clocks, and whether the IPQ4019 sees them.

---

## 1. What should be on the wire

| Signal | Expected | Source |
|---|---|---|
| FSC (frame sync) | 8 kHz, 125 us period | GPL, OEM (`TDM: FS: 8000 Hz`) |
| DCL / BCLK | ~1.0257 MHz | OEM measured 1 025 720 Hz |
| Slots | 8 | GPL (`adss_glb_tdm_ctrl_ch_num(slots - 1)`) |
| Bits per slot | 16 | GPL |
| Frame payload | 16 bytes | GPL (8 x 2) |
| Direction | **SC14448 is master**, IPQ4019 ADSS is slave | GPL driver slave path, board DTS input flags |

The slave direction is evidenced by:

- `gpio_avm_pcmlink_fsc/dcl/mcl` are declared **input** in
  `Fritz_Box_HW236.dtsi`; only `do` is an output;
- `adss_config_clk()` sets dummy rates 252/254/255 with `extclk = 1` so the
  ADCC selects the external pad clock;
- `STEREO_CONFIG_MASTER` (`ipq-adss.h:191`) is cleared (`master = 0`).

Consequence: **no FSC/BCLK means the SC14448 is not generating them.**  The
IPQ4019 will never generate them in this configuration.

---

## 2. Pin candidates and which group is real

From `avm-gpl/.../arch/arm/boot/dts/Fritz_Box_HW236.dtsi` lines 344-383:

| Signal | Group "PINMUX2" | Group "PINMUX3" | Direction |
|---|---|---|---|
| MCL | GPIO20 | GPIO24 | input |
| DCL (BCLK) | GPIO21 | GPIO25 | input |
| FSC | GPIO22 | GPIO26 | input |
| DI | — | GPIO23 | input |
| DO | — | GPIO27 | output |

Only **PINMUX3** carries data lines (`DI`/`DO` exist only there), so a full
PCM channel is the second column.  PINMUX2 has clocks but no data.

Important: `PINMUX2`/`PINMUX3` are **AVM board-table classes**, not IPQ4019
TLMM mux functions.  Mainline `pinctrl-ipq4019.c` exposes no PCM/TDM function
for GPIO20-27 at all (only `blp_i2c0`, `i2s_rx`, `rgmii`, `sdio`, `i2s_tx`,
`i2s_td`).  Therefore there is nothing in upstream Linux that can be
configured as an "audio pinmux"; the pads are wired by the board and the ADSS
IP block, not by TLMM.

Whether the pads are enabled after reset is **not proven**.  Do not assume
GPIO20-27 are live just because the DTS names them.

---

## 3. What can be checked without a probe

All of these are passive and already available in the Stage C0 collector:

1. `pinmux-pins` — confirms the pins are unclaimed (they are not muxed to
   any peripheral function);
2. `clk_summary` — confirms the ADCC/AHB state;
3. `dmesg` — no ADSS traffic;
4. `/proc/interrupts` — no SPI 156/159 activity (a running TDM with DMA
   would raise them only after the driver enables them; without DMA the IRQ
   may stay silent, so absence is not proof of no clocks).

These checks can distinguish only "another Linux driver owns the pins" from
"nobody owns them".  They cannot tell whether the SC14448 is toggling its
outputs.

---

## 4. Measurement setup

### 4.1 Where to probe

**Unverified.**  No source in this tree maps HW236 test points to these
signals.  Before touching the board:

- use the schematic/test-point list if it exists;
- otherwise probe at the **SC14448 side** of the series resistors on the
  three clock lines, never at a floating pad;
- confirm continuity to the named IPQ4019 pin with the board powered off.

Do not assume the SoC pins are reachable: the 7530 is a plastic case with no
exposed header.

### 4.2 Electrical limits

| Parameter | Value |
|---|---|
| SoC I/O voltage | 1.8 V class (IPQ4019 TLMM), **verify on the board** |
| Probe impedance | >= 1 MOhm, <= 15 pF |
| Ground | board ground, short lead |
| Never | drive a signal, inject a clock, or connect a signal generator |

A logic analyser with 1.8 V threshold support is required.  A 3.3 V-only
analyser with 1.8 V logic may read permanent "low" and mislead.

### 4.3 What to capture

| Sequence | Expectation if SC14448 runs | Expectation if it does not |
|---|---|---|
| Trigger on FSC edge, sample 1 ms | 8 frames visible | flat line |
| Measure FSC period | 125 us +/- 1 % | none |
| Measure BCLK inside a frame | 16 edges per slot, 128 per frame | none |
| Count slots between two FSC edges | 8 | none |

Record the capture together with a timestamp and the exact OpenWrt boot
(same initramfs, same U-Boot session), so it can be compared with a later
run.

---

## 5. Distinguishing the three failure modes

| Observation | FSC/BCLK | DATA | Meaning |
|---|---|---|---|
| No clocks at all | flat | flat | SC14448 not booted (no firmware) or not reset-released |
| Clocks present, no data | 8 kHz / 1.0257 MHz OK | flat | chip booted, no FON channel active |
| Clocks + data | OK | transitions | chip active and talking |

This is the cheapest way to separate "firmware missing" from "pins/reset
wrong" **before** designing any driver work.  It requires no Linux change at
all: boot the existing probe-only image and measure.

---

## 6. What this test cannot prove

- that the SC14448 firmware is the AVM one;
- that the FON SLIC is powered;
- that the analog line is safe to connect;
- that GPIO40 polarity is correct (a wrong reset leaves the chip silent, same
  symptom as missing firmware).

Each remains a separate gate.

---

## 7. Stop conditions

Stop and power off if:

- any probe slips and shorts a supply rail;
- the board fails to boot after the session;
- a signal exceeds the expected 1.8 V domain;
- the SC14448 gets warm, which would suggest a held reset or a short.
