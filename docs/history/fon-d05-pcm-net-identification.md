# D0.5 — where FSC/BCLK can actually be measured

> **Historical analysis.** D0.6 later recovered the compiled PINMUX2/3 values
> as 2/3 and the `pcmlink.ko` pinconfig call. Current status is in
> `../fon-d06-summary.md`; the physical-net cautions in this record remain
> valid.

> **Status: offline Device-Tree and pinctrl analysis + vendor disassembly.**
> No router was touched, no probe was placed, no GPIO/reset/DMA was changed.

Purpose: answer "where do I put the scope probe?" — not another round of
PCMLINK reverse engineering.

---

## 0. Bottom line

**GPIO20–27 are AVM's documented PCMLINK candidates on HW236.  Their physical
connection to the SC14448 and the active pinmux are not proven.**  The
pinctrl driver makes I2S reachable on other pins too, so the candidate list is
evidence of intent, not of wiring.

Three DT/pinctrl facts decide the whole question, in order of importance:

1. **The I2S/PCM function exists in the IPQ4019 pinctrl driver, and it is
   available on the AVM board-table pins.**  `i2s_rx` may use gpio20/21/22/23,
   `i2s_tx` gpio24/25/26, `i2s_td` gpio27 — but the same functions are also
   available on other GPIOs (e.g. `i2s_rx` also on 0/1/2/58/60/61/63,
   `i2s_tx` also on 52/53/57/60/61, `i2s_td` also on 28/29/54/55/56/63).
   So GPIO20–27 are the **documented AVM candidates** for PCMLINK on
   HW236, not the only pins that could carry I2S in the SoC.
2. **Neither the AVM audio DTSI nor the HW236 board file assigns
   `pinctrl-0` to the PCM/TDM nodes.**  The pins are not muxed by Linux
   Device Tree at all in the published sources.
3. Therefore the pins are either muxed by the **bootloader / AVM pinctrl
   state name** (`PINMUX2`/`PINMUX3`, which are AVM-only abstractions and are
   **not defined** anywhere in the GPL drop), or they carry a non-pinmux
   signal.  This is `UNKNOWN` from the sources available here.

**Consequence for the owner:** the only *proven* statement is that the
signals, if they exist, can appear on the IPQ4019 pins GPIO20–GPIO27.  Where
they are physically reachable on the board is **not** established by any
document in this repository.

## 1. Evidence tables

### 1.1 AVM board table (`Fritz_Box_HW236.dtsi:344-383`)

| Name | GPIO | Direction | AVM class |
|---|---|---|---|
| `gpio_avm_pcmlink_fsc` | 22 | input, active low | PINMUX2 |
| `gpio_avm_pcmlink_fsc_2` | 26 | input, active low | PINMUX3 |
| `gpio_avm_pcmlink_dcl` | 21 | input, active low | PINMUX2 |
| `gpio_avm_pcmlink_dcl_2` | 25 | input, active low | PINMUX3 |
| `gpio_avm_pcmlink_mcl` | 20 | input, active low | PINMUX2 |
| `gpio_avm_pcmlink_mcl_2` | 24 | input, active low | PINMUX3 |
| `gpio_avm_pcmlink_di` | 23 | input | PINMUX3 |
| `gpio_avm_pcmlink_do` | 27 | output, active low | PINMUX3 |

`AVM_DEF_HW_FUNCTION_PINMUX2/3` is **not defined** in this GPL tree; the
macro appears only in these DTS lines.  The runtime consumer
(`avm_gpio_generic`) is also absent from the drop.  So "PINMUX2/3" is a
board-table class we cannot expand.

### 1.2 IPQ4019 pinctrl (`pinctrl-ipq4019.c`, Linux 6.12.112)

Groups and their pins (verbatim from the group arrays):

| Function | GPIOs |
|---|---|
| `i2s_rx` | 0, 1, 2, **20, 21, 22, 23**, 58, 60, 61, 63 |
| `i2s_tx` | **24, 25, 26**, 52, 53, 57, 60, 61 |
| `i2s_td` | **27**, 28, 29, 54, 55, 56, 63 |

Per-pin capability from `PINGROUP(...)`:

| GPIO | Functions |
|---|---|
| 20 | `blsp_i2c0`, `i2s_rx` |
| 21 | `blsp_i2c0`, `i2s_rx` |
| 22 | `rgmii`, `i2s_rx` |
| 23 | `sdio`, `rgmii`, `i2s_rx` |
| 24 | `sdio`, `rgmii`, `i2s_tx` |
| 25 | `sdio`, `rgmii`, `i2s_tx` |
| 26 | `sdio`, `rgmii`, `i2s_tx` |
| 27 | `sdio`, `rgmii`, `i2s_td` |

**Important:** `i2s_rx` covers GPIO20-23 and `i2s_tx` covers GPIO24-26
(`i2s_td` = GPIO27).  This does **not** directly map "FSC→one GPIO, DCL→
another"; the pinctrl groups are direction classes (receive vs transmit
group), and which GPIO within a group carries FSC vs DCL is a board wiring
choice, not encoded here.  The AVM board table is the only source that
assigns a *name* to a pin, and it does so in two alternative groups
(MUX2 = 20/21/22, MUX3 = 24/25/26/27).

### 1.3 No `pinctrl-0` on any PCM/TDM node

| File | Node | has `pinctrl-0`? |
|---|---|---|
| `qcom-ipq4019-audio.dtsi` | `audio@7700000`, `pcm@7704000`, `mbox0..4`, `stereo0..3` | **no** |
| `Fritz_Box_HW236.dtsi` | `tdm@0`, `pcm@7704000`, `mbox0..3`, `stereo0..3` | **no** (only `status = "ok"`) |
| OpenWrt DTB (`cd6c5dec…`) | no PCM/TDM pinctrl node at all | **no** |

So in the published DTs nothing selects `i2s_rx`/`i2s_tx`/`i2s_td` on any
pin.  Stage C0 already observed the pads as **unclaimed GPIO inputs**, which
matches this: Linux never muxed them.

### 1.4 What `pcmlink.ko` expects

From `reports/pcmlink.annotated.txt` the strings and lookup order are:

```
gpio_avm_pcmlink_fsc        gpio_avm_pcmlink_dcl
gpio_avm_pcmlink_fsc_2      gpio_avm_pcmlink_dcl_2
gpio_avm_pcmlink_di         gpio_avm_pcmlink_do
```

It resolves each by **name** against the board data (`avm_get_hw_config_table`)
and errors with `ERROR: resource gpio %d not available` / `no
gpio_avm_pcmlink_fsc exist`.  So the GPIO numbers come from the same board
table summarised in §1.1; `pcmlink.ko` does not invent pins.

`[pcmlink]TDM: FS: %u Hz CLK: %u Hz` is the runtime check; it returns
failure if FSC/DCL are missing or the measured clock is below threshold.

## 2. The signal table requested by the task

| Signal | Source | Possible PCB net | Accessible point | Confidence |
|---|---|---|---|---|
| FSC | SC14448 (master) | GPIO22 (MUX2) or GPIO26 (MUX3) | **UNKNOWN** | name/role `GPL board table`; physical reachability `UNKNOWN` |
| BCLK/DCL | SC14448 (master) | GPIO21 (MUX2) or GPIO25 (MUX3) | **UNKNOWN** | same |
| MCL | SC14448? | GPIO20 (MUX2) or GPIO24 (MUX3) | **UNKNOWN** | same; whether MCL is even used is `UNKNOWN` |
| DI | SC14448 → IPQ | GPIO23 | **UNKNOWN** | `GPL board table` |
| DO | IPQ → SC14448 | GPIO27 | **UNKNOWN** | `GPL board table` |

"Accessible point" stays `UNKNOWN` because:

- no document in this tree maps GPIO20-27 to a test pad;
- the pins are unclaimed GPIOs under OpenWrt, so **software cannot confirm
  where they go physically**;
- the only board photos available are low resolution at the packages and do
  not show trace endpoints.

## 3. What the SoC-side evidence does and does not prove

**Proven**

- The I2S function exists and covers exactly GPIO20-27 as the AVM table
  claims, split `i2s_rx` (20-23) / `i2s_tx` (24-26) / `i2s_td` (27).
- No DT in the drop assigns those pins to I2S.
- `pcmlink.ko` looks these signals up by board-table name.

**Not proven / disproved**

| Claim | Status |
|---|---|
| GPIO20-27 are wired to SC14448 PCM pins | **UNKNOWN** |
| A specific GPIO is FSC / BCLK | **UNKNOWN** — only the MUX2/MUX3 name groups exist |
| A test pad anywhere carries FSC/BCLK | **UNKNOWN** |
| Linux can observe the clocks through GPIO | **DISPROVED as a method** — 8 kHz+ is invisible to the sysfs sampling used in C0 |
| Absence of transitions in C0 means no clocks | **DISPROVED** — sampling was far too slow |

## 4. The only safe ways to find the net

### 4.1 Best: continuity from the SC14448 pins, board **unpowered**

The SC14448 is a QFP with visible perimeter pins (confirmed from the GPL
description and the package appearance, not from a BGA underside).  With the
board fully unpowered, a multimeter can check whether `i2s_*`-capable GPIO
pads exist as **exposed pads/vias or resistor ends** on the board.

This does not require touching a pin under power.

### 4.2 Second: known resistor groups near the Dialog

If a series resistor is found on a candidate line, the **resistor end away
from the chip** is a safer scope point than the pin.

### 4.3 Never

- probing a QFP pin while powered;
- assuming A2/A3/B2/B3 are PCM;
- using the console pads as PCM points;
- injecting any signal.

## 5. What is still needed to answer Q4/Q27

| Missing input | Why it blocks |
|---|---|
| a board photo where GPIO20-27 traces or their resistors are visible | to name a physical point |
| or a continuity map from SC14448 pins to pads | same |
| or an AVM schematic/test-point list | same |

Without one of these, the honest answer is: **the net is not identifiable
from the documents available**, and the plan is a **continuity search**,
not a named probe point.

## 6. Status of the two vendor questions

### 6.1 `fs_per_dma` (Q76) — resolved to a formula

`ipq40xxtdm_linkinit` (`reports/pcmlink.annotated.txt`, `0x9ef0..0xa04c`):

```
0x9ef0: ldr  r0, [r5]           ; board config: slot_size
0x9ef4: ldr  r1, [r5, #8]       ; board config: slots-per-frame
0x9ef8: bl   __aeabi_uidiv      ; r0 = slot_size / slots
...
0x9f20: mul  r6, r6, r0
0x9f28: lsl  r6, r6, #1
```

and the `tdm_if_dma_init` call at `0xa040..0xa04c`:

```
r3      = 1                ; cpu
[sp]    = 1                ; only_rxirq
[sp,#4] = slot_size        ; slots
[sp,#8] = r0 (uidiv)       ; fs_per_dma
[sp,#0xc]= 0x10            ; desc_num
```

So `fs_per_dma` is `[r5] / [r5+8]`, computed at run time from the board
config block, and `slots` (`[sp,#4]`) is `r3 = [r5+8]` after the `lsl`
transform, **not** raw `[r5+8]`.

What can be stated:

- `fs_per_dma` is **a division of two board-config values**, not a literal
  32 and not a constant.
- `[r5+8]` is also the value that selects 8- vs 16-bit slots
  (`cmp r3, #8`, `movlo r6, #8`, `movhs r6, #0x10`), so it is the slot-width
  control.
- `[r5+4]` is used as a **shift count** (`lsl r3, r3, r2`), so it is a
  ratio/divider, not a frame count.
- The actual numbers in the 7530 board table are **not** present in the GPL
  drop; `pcmlink.ko` reads them from `avm_get_hw_config_table`, which is
  closed.

Therefore `fs_per_dma = 32` is **not provable** from the available sources.
The earlier `INFERRED 32` is withdrawn; status is **UNRESOLVED**, and the
only safe statement is that `fs_per_dma` is derived as
`[r5] / [r5+8]` from board data with no known numeric value.  Closing it
needs either the 7530 board-config table or one runtime readback of the
`DBG_TRC_API` line `tdm_if_adss_dma_init(... fs_per_dma=%u ...)`.

### 6.2 `TDMPriv+0x808` — resolved

`fpgadata_init` (`0x9434..0x944c`):

```
movw r2, #0x1003
and  r2, r6, r2
movw r3, #0x1001
cmp  r2, r3
moveq r3, #1
streq r3, [r4, #0x808]
```

`TxDMA` (`0x98ac..0x98c8`):

```
movw r2, #0x5555
ldr  r3, [r4, #0x808]
cmp  r3, #0
movne r2, #0
strh r2, [frame + 0x08]
```

So `+0x808` is an **FPGA-present flag**: when the board config has no FPGA
(the 7530 case), the flag is 0 and TX slot 4 is **0x5555**; on FPGA boards it
is **0x0000**.  The 7530 therefore uses the `0x5555` branch — the driver's
`FON_TDM_HDR08_5555` — **for the non-FPGA path**.  The driver default stays
explicit rather than silently switching.

### 6.3 Initial control word — still UNKNOWN

`+0x7fc` is read in `TxDMA` before any store (`ldrh r0, [sb]` where
`sb = TDMPriv+0x7fc`), and the `fpgadata_init` zeroing covers `TDMPriv`
memory, but no source shows a **written** first control word.  So the first
frames to the SC14448 carry whatever the allocation left there — in practice
0 — which is **not** the same as a proven line-idle encoding
(`build_slic_ctrl(0,0,0) = 0x4000`).  Status: **UNKNOWN, unchanged**.
