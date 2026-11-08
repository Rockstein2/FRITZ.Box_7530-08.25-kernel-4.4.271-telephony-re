# D0.6-B — PCMLINK pinmux and TLMM register map

> **Status: offline source + disassembly analysis.**  No TLMM write, no
> router access.  The register map below is for a future **read-only** check;
> no write sequence is given.

---

## 0. Bottom line

| Question | Answer | Status |
|---|---|---|
| Does `pcmlink.ko` set the I2S pinmux itself? | **Yes** — `ipq40xxtdm_linkinit` calls `dakota_gpio_pinconfig(gpio, profile->field, 1)` | **CONFIRMED** |
| Does `Piglet_noemif.ko` set the pinmux? | No — it requests them as **input** via `dakota_gpio_ctrl(gpio, 0, 0)` and only reads | **CONFIRMED** |
| What are `AVM_DEF_HW_FUNCTION_PINMUX2/3`? | The numeric values stored in the profile fields `+0x1c`/`+0x20`, passed to `dakota_gpio_pinconfig`; the macro itself is still not in the GPL drop | **partly CONFIRMED** |
| Which group is used for `tdm@0`? | `pcmlink` reads `profile+0x1c` or `profile+0x20` depending on a mode flag | **CONFIRMED (mechanism)**, which one on HW236 **UNKNOWN** |
| Is I2S actually muxed on those pads under OpenWrt? | Stage C0 saw them as unclaimed GPIO inputs, so **not muxed** | **CONFIRMED (negative)** |

The decisive new finding: `Check_TDMInterface` **reads** the clocks as plain
GPIO inputs.  For that to produce clean edges, the pads must already be in an
input-capable state from the board/bootloader side, not driven by the SoC's
I2S block.  That is consistent with the SC14448 being the clock master and
the SoC only observing.

## 1. Evidence: `Check_TDMInterface`

`Piglet_noemif.ko`, `.text` `0x3f0c`.  It resolves two names:

| Literal | Address | String |
|---|---|---|
| `0x4134` | `.rodata.str1.1` off `0x11d6` | `gpio_avm_pcmlink_fsc` |
| `0x413c` | `.rodata.str1.1` off `0x121a` | `gpio_avm_pcmlink_dcl` |

and then:

```
3fcc: bl   strcmp                 ; match "gpio_avm_pcmlink_fsc"
3ffc: cmp  r4, #0
4004: ldr  r4, [r4, #0x4]         ; GPIO number
4008: mov  r2, r5                 ; r5 == 0 here
400c: mov  r1, r5                 ; 0
4010: mov  r0, r4
4014: bl   dakota_gpio_ctrl       ; dakota_gpio_ctrl(gpio, 0, 0)  <-- INPUT
4028: mov  r0, r4
402c: bl   dakota_gpio_get_membase ; direct register base for fast reads
```

The same block repeats for `dcl` at `0x4024`.  Afterwards it counts
transitions by polling the mapped register and computes frequencies
(`0x4078..0x40f4`), ending in the `[pcmlink]TDM: FS: %u Hz CLK: %u Hz`
style report.

**What this proves**

- `(gpio, 0, 0)` = request as **input**; the second argument is the direction
  (0 = in, matching `dect_loader`'s `(gpio, 0, 1)` = output).
- The module does **not** program a TLMM function select.  It asks for a
  plain GPIO input and reads edges.
- Therefore the I2S pinmux is **not** what this code relies on; it reads the
  pads as GPIOs.

**What this does not prove**

- That the pins are physically connected to the SC14448.
- Whether some other component muxes them at another time.

## 2. `pcmlink.ko` applies the pinmux itself

This corrects the earlier reading.  `ipq40xxtdm_linkinit` in
`lib/modules/4.4.271/ubik2/pcmlink.ko` (`.text` `0xa144..0xa168`) does:

```
a144: mov   r1, r11                 ; control value from the profile
a148: mov   r0, r8                  ; gpio
a14c: bl    dakota_gpio_ctrl        ; dakota_gpio_ctrl(gpio, ctrl, 1)
a150: mov   r2, #1                  ; request
a154: mov   r0, r8                  ; gpio
a158: ldr   r3, [sp, #0x14]
a15c: cmp   r3, #0
a160: ldrne r1, [r6, #0x20]         ; profile field B
a164: ldreq r1, [r6, #0x1c]         ; profile field A
a168: bl    dakota_gpio_pinconfig   ; dakota_gpio_pinconfig(gpio, field, 1)
```

So the module:

1. takes a **control value** and a **pinconfig value** from the board
   profile;
2. applies the direction/control with `dakota_gpio_ctrl(gpio, ctrl, 1)`;
3. applies the **function select** with
   `dakota_gpio_pinconfig(gpio, <profile field>, 1)`.

`pinconfig` therefore receives the value that `AVM_DEF_HW_FUNCTION_PINMUX2/3`
was meant to express, stored in the profile at `+0x1c` or `+0x20`.  The
choice between the two fields is a mode flag (`[sp,#0x14]`), so both groups
exist as **data**, and which one is used depends on that flag.

The numeric values themselves are still not available: they live in
`avm_get_hw_config_table`, which is closed.  What changed is that the
**mechanism** is now confirmed rather than assumed, and the earlier statement
"pcmlink does not set the pinmux" is **DISPROVED**.

## 2.1 `Piglet_noemif.ko` does not

`Check_TDMInterface` (`0x3f0c`) only calls `dakota_gpio_ctrl(gpio, 0, 0)` —
input request — and `dakota_gpio_get_membase` to poll.  It never calls
`pinconfig`.  That is consistent with the sequence: PCMLINK configures the
TDM pins, Piglet only observes them.

Because `Check_TDMInterface` resolves only `gpio_avm_pcmlink_fsc` and
`gpio_avm_pcmlink_dcl`, while `pcmlink.ko` carries `_fsc_2`, `_dcl_2`, `di`
and `do`, the two modules address **different name sets**.  `piglet` uses the
`fsc`/`dcl` pair, `pcmlink` uses the full `_2`/`di`/`do` set for pinconfig.
Which physical pins that ends up meaning is still the board table's answer.

## 2.2 `AVM_DEF_HW_FUNCTION_PINMUX2/3`

Searched the whole GPL drop: the macro appears **only** in the DTSI lines
that assign it.  No `#define`, no consumer, no `avm_gpio` driver source.

**Status:** the *name* remains UNKNOWN, but its **role** is now confirmed —
it is the value handed to `dakota_gpio_pinconfig`.  Treat PINMUX2/PINMUX3 as
two alternative values for that field:

| Signal | PINMUX2 | PINMUX3 |
|---|---|---|
| MCL | GPIO20 | GPIO24 |
| DCL/BCLK | GPIO21 | GPIO25 |
| FSC | GPIO22 | GPIO26 |
| DI | — | GPIO23 |
| DO | — | GPIO27 |

## 3. TLMM register map for GPIO20–27

From `pinctrl-ipq4019.c` (`PINGROUP` macro, lines 218–245):

```
.ctl_reg        = 0x0 + 0x1000 * id
.io_reg         = 0x4 + 0x1000 * id
.intr_cfg_reg   = 0x8 + 0x1000 * id
.intr_status_reg= 0xc + 0x1000 * id
```

and from the OpenWrt DTB, the controller is

```
pinctrl@1000000 {
    compatible = "qcom,ipq4019-pinctrl";
    reg = <0x1000000 0x300000>;
    ngpios = 100;
};
```

so the base is **`0x01000000`**.  Per-pin `CFG` (ctl) address is
`0x01000000 + 0x1000 * id`.

| GPIO | ctl/CFG address | io address | AVM name(s) | I2S function | FUNC_SEL for I2S | Confidence |
|---|---|---|---|---|---|---|
| 20 | `0x01014000` | `0x01014004` | MCL (MUX2) | `i2s_rx` | **UNKNOWN** | address CONFIRMED, selector UNKNOWN |
| 21 | `0x01015000` | `0x01015004` | DCL (MUX2) | `i2s_rx` | **UNKNOWN** | same |
| 22 | `0x01016000` | `0x01016004` | FSC (MUX2) | `i2s_rx` | **UNKNOWN** | same |
| 23 | `0x01017000` | `0x01017004` | DI (MUX3) | `i2s_rx` | **UNKNOWN** | same |
| 24 | `0x01018000` | `0x01018004` | MCL_2 (MUX3) | `i2s_tx` | **UNKNOWN** | same |
| 25 | `0x01019000` | `0x01019004` | DCL_2 (MUX3) | `i2s_tx` | **UNKNOWN** | same |
| 26 | `0x0101a000` | `0x0101a004` | FSC_2 (MUX3) | `i2s_tx` | **UNKNOWN** | same |
| 27 | `0x0101b000` | `0x0101b004` | DO (MUX3) | `i2s_td` | **UNKNOWN** | same |

### 3.1 Why FUNC_SEL is left UNKNOWN

`PINGROUP` builds `.funcs = (int[]){ qca_mux_gpio, qca_mux_f1, ... }`.
`i2s_rx` is the **second** entry (`f1`) for GPIO20–23 and `i2s_tx`/`i2s_td`
are also `f1` for 24–27.  That suggests the runtime value is one of the
`qca_mux_*` enum members, but the **numeric encoding written into
`FUNC_SEL`** is set by `msm_pinctrl_set_mux()` from an index we do not have a
documented table for here.  Do **not** program a value from this document.

The safe read-only check is: read `cfg` for each pin and compare the
`FUNC_SEL` field against the observed mux under FRITZ!OS, using the kernel's
own `debugfs` pinctrl view as the reference rather than an assumed constant.

## 4. Why the mux state matters, and what it means for us

The two modules deliberately use the pads differently:

| Module | Pad state it wants | Why |
|---|---|---|
| `Piglet_noemif.ko` (`Check_TDMInterface`) | plain **GPIO input** | it polls edges to measure FSC/BCLK |
| `pcmlink.ko` (`ipq40xxtdm_linkinit`) | **pinconfig** value from the profile | it needs the ADSS block connected to the pins for TDM |

Under OpenWrt, Stage C0 found the pads as **unclaimed GPIO inputs**, which is
the Piglet-side state, not the PCMLINK-side one.  That is expected: nothing
has run `dakota_gpio_pinconfig` because `pcmlink` never loaded and its TDM
link never initialised.

Two consequences:

1. The absence of an I2S mux is **not** an error and not evidence of a broken
   board.  It simply means the second consumer never started.
2. For a **passive** software check the GPIO-input state is actually the
   useful one: the pads are readable, so a future kernel edge counter could
   measure FSC/BCLK the same way AVM does — without touching TLMM.

Configuring `i2s_rx`/`i2s_tx` ourselves would move the pads to the ADSS side
and is **not** part of any current stage.

## 5. What would confirm the group

| Unknown | Needs |
|---|---|
| which of MUX2/MUX3 is populated | board table dump (`avm_get_hw_config_table` output) |
| FUNC_SEL numeric value for I2S | kernel `debugfs` pinmux under FRITZ!OS, read-only |
| whether pads reach the SC14448 | continuity, or a schematic |
