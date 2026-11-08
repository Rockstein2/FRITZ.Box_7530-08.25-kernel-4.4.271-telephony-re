# D0.6-B — PCMLINK pinmux and TLMM register map

> **Historical evidence record.** Current D0.6 conclusions are summarized in
> `../fon-d06-summary.md`. This file retains disassembly and register-map
> provenance.

> **Status: offline OEM DTB + source + disassembly analysis.**  No TLMM write, no
> router access.  The register map below is for a future **read-only** check;
> no write sequence is given.

> **Evidence boundary (2026-11-08).** `MUX UNCLAIMED` is a **Linux ownership**
> report. It is not a readback of the TLMM `FUNC_SEL` field, so it does not
> prove that the hardware field is `0` or that the pad is disconnected.

---

## 0. Bottom line

| Question | Answer | Status |
|---|---|---|
| Does `pcmlink.ko` set the I2S pinmux itself? | **Yes** — `ipq40xxtdm_linkinit` calls `dakota_gpio_pinconfig(gpio, profile->field, 1)` | **CONFIRMED** |
| Does `Piglet_noemif.ko` call the pinmux API? | No explicit `dakota_gpio_pinconfig()`; it calls `dakota_gpio_ctrl(gpio, 0, 0)` and reads edges. The side effects of `ctrl()` are not recovered, so this is not proven to be hardware read-only | **no pinconfig CONFIRMED**, `ctrl()` effects **UNKNOWN** |
| What are `AVM_DEF_HW_FUNCTION_PINMUX2/3`? | The compiled OEM DTB contains `function = <2>` and `<3>`; these match TLMM FUNC_SEL **2** and **3** (bits [5:2] = `0x08`/`0x0C`) | **values CONFIRMED**, API pass-through **UNKNOWN** |
| Which group is used for `tdm@0`? | OEM 08.25 live readback: GPIO21/22=2, GPIO23/25/26/27=3, GPIO20/24=0. Both groups are partly active; the earlier “either MUX2 or MUX3” reading is superseded. | **CONFIRMED (OEM runtime)**, MCL=0 reason **UNKNOWN** |
| Is I2S actually muxed on those pads under OpenWrt? | Stage C0 reported the pins as unclaimed by Linux; this is not a hardware register readback, so the actual `FUNC_SEL` is unknown | **Linux owner: none (RUNTIME-RO)**, hardware mux **UNKNOWN** |

`Check_TDMInterface` **reads** the clocks through the GPIO API. It does not
generate FSC/BCLK. For clean edges the pads would need an input-capable state,
but whether `dakota_gpio_ctrl()` leaves them untouched is not known. The
clock-master hypothesis is therefore **INFERRED**, not a hardware proof.

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

The compiled OEM DTB settles the numeric profile values: PINMUX2 is `2` and
PINMUX3 is `3` (see `../runbook/fon-oem-dtb-extraction.md`). What remains unknown is
whether `dakota_gpio_pinconfig()` passes the profile value to TLMM unchanged.
The **mechanism** is confirmed, and the earlier statement "pcmlink does not
set the pinmux" is **DISPROVED**.

## 2.1 `Piglet_noemif.ko` does not

`Check_TDMInterface` (`0x3f0c`) calls `dakota_gpio_ctrl(gpio, 0, 0)` — an
input request — and `dakota_gpio_get_membase` to poll.  It never calls
`pinconfig`.  That is consistent with the sequence: PCMLINK configures the
TDM pins, Piglet observes them.  It does **not** prove that `dakota_gpio_ctrl`
has no side effect on the pad; that function is closed (Q81).

Because `Check_TDMInterface` resolves only `gpio_avm_pcmlink_fsc` and
`gpio_avm_pcmlink_dcl`, while `pcmlink.ko` carries `_fsc_2`, `_dcl_2`, `di`
and `do`, the two modules address **different name sets**.  `piglet` uses the
`fsc`/`dcl` pair, `pcmlink` uses the full `_2`/`di`/`do` set for pinconfig.
Which physical pins that ends up meaning is still the board table's answer.

## 2.2 `AVM_DEF_HW_FUNCTION_PINMUX2/3`

The macro definitions are absent from the partial GPL drop, but the compiled
OEM DTB preserves their results:

```text
gpio_avm_pcmlink_mcl/dcl/fsc:       function = <0x02>
gpio_avm_pcmlink_di/mcl_2/dcl_2/
                    fsc_2/do:      function = <0x03>
```

Therefore the macro values themselves are **CONFIRMED**:

- `AVM_DEF_HW_FUNCTION_PINMUX2 = 2`;
- `AVM_DEF_HW_FUNCTION_PINMUX3 = 3`.

The complete compiled-node provenance and DTB hash are in
`../runbook/fon-oem-dtb-extraction.md`.

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

| GPIO | ctl/CFG address | io address | AVM name(s) | I2S function | `.funcs[]` index | FUNC_SEL | Bits [5:2] | Confidence |
|---|---|---|---|---|---|---|---|---|
| 20 | `0x01014000` | `0x01014004` | MCL (MUX2) | `i2s_rx` | 2 | **2** | `0x08` | CONFIRMED |
| 21 | `0x01015000` | `0x01015004` | DCL (MUX2) | `i2s_rx` | 2 | **2** | `0x08` | CONFIRMED |
| 22 | `0x01016000` | `0x01016004` | FSC (MUX2) | `i2s_rx` | 2 | **2** | `0x08` | CONFIRMED |
| 23 | `0x01017000` | `0x01017004` | DI (MUX3) | `i2s_rx` | 3 | **3** | `0x0C` | CONFIRMED |
| 24 | `0x01018000` | `0x01018004` | MCL_2 (MUX3) | `i2s_tx` | 3 | **3** | `0x0C` | CONFIRMED |
| 25 | `0x01019000` | `0x01019004` | DCL_2 (MUX3) | `i2s_tx` | 3 | **3** | `0x0C` | CONFIRMED |
| 26 | `0x0101a000` | `0x0101a004` | FSC_2 (MUX3) | `i2s_tx` | 3 | **3** | `0x0C` | CONFIRMED |
| 27 | `0x0101b000` | `0x0101b004` | DO (MUX3) | `i2s_td` | 3 | **3** | `0x0C` | CONFIRMED |

### 3.1 How FUNC_SEL is derived

`PINGROUP(id, f1, f2, ...)` expands to:

```c
.funcs = (int[]){ qca_mux_gpio,  /* index 0 */
                  qca_mux_##f1,  /* index 1 */
                  qca_mux_##f2,  /* index 2 */
                  ... },
.nfuncs = 15,
.mux_bit = 2,
```

and `msm_pinmux_set_mux()` (`pinctrl-msm.c`) picks the **index** of the
requested function and writes it shifted by `mux_bit`:

```c
for (i = 0; i < g->nfuncs; i++)
        if (g->funcs[i] == function)
                break;
...
val |= i << g->mux_bit;
```

So the value written is the array index, and the field is bits **[5:2]**
(`mux_bit = 2`).  For the pins in question:

| GPIO | `PINGROUP(...)` arguments | `i2s_*` position | index |
|---|---|---|---|
| 20, 21 | `blsp_i2c0, i2s_rx, …` | `f2` | **2** |
| 22 | `rgmii, i2s_rx, …` | `f2` | **2** |
| 23–27 | `sdio, rgmii, i2s_rx/tx/td, …` | `f3` | **3** |

This is exactly the split the AVM names describe:

- **PINMUX2** group (GPIO20/21/22) → FUNC_SEL **2** → bits `0x08`;
- **PINMUX3** group (GPIO23/24/25/26/27) → FUNC_SEL **3** → bits `0x0C`.

The Linux pinctrl derivation and the compiled OEM DTB independently agree:
`AVM_DEF_HW_FUNCTION_PINMUX2/3` carry values **2/3**. This is **CONFIRMED**.
It remains **UNKNOWN** whether the closed `dakota_gpio_pinconfig()` wrapper
passes those values to the TLMM field unchanged.

**Read-only check, not a write recipe:** reading `cfg` for each pin and
masking bits [5:2] should yield `0x08` or `0x0C` when the pin is muxed for
I2S, and `0x00` when it is a plain GPIO.  Nothing in this document is to be
written.

## 4. Why the mux state matters, and what it means for us

The two modules request the pads differently:

| Module | Requested pad state | Why |
|---|---|---|
| `Piglet_noemif.ko` (`Check_TDMInterface`) | plain **GPIO input** request (`ctrl()` side effects not proven) | it polls edges to measure FSC/BCLK |
| `pcmlink.ko` (`ipq40xxtdm_linkinit`) | **pinconfig** value from the profile | it needs the ADSS block connected to the pins for TDM |

Under OpenWrt, Stage C0 reported the pads as **unclaimed by Linux**.  That is
a software-ownership observation, not a readback of the TLMM register.  It is
consistent with nothing having run `dakota_gpio_pinconfig` because `pcmlink`
never loaded, but the actual pad state and `FUNC_SEL` remain **UNKNOWN**.

Two consequences:

1. The absence of a **Linux mux owner** is not an error and not evidence of a
   broken board.  It does not prove the hardware mux is `0`.
2. A future kernel edge counter could measure FSC/BCLK only after proving that
   its GPIO setup does not change the pad; the `dakota_gpio_ctrl()` side
   effects are unresolved.

Configuring `i2s_rx`/`i2s_tx` ourselves would move the pads to the ADSS side
and is **not** part of any current stage.

## 4a. OEM 08.25 live readback (2026-11-08)

`/proc/avm/gpio/list` from the running OEM firmware gives the actual TLMM
configuration:

| GPIO | `func` | `TLMM_GPIO_CFG` |
|---|---:|---|
| 20 | 0 | `0x00004802` |
| 21 | 2 | `0x0000480a` |
| 22 | 2 | `0x0000480a` |
| 23 | 3 | `0x0000480e` |
| 24 | 0 | `0x00004802` |
| 25 | 3 | `0x0000480e` |
| 26 | 3 | `0x0000480e` |
| 27 | 3 | `0x00004a0e` |

At the same time `pinmux-pins` reports `(MUX UNCLAIMED)` for GPIO20–27.
Therefore Linux ownership output is **not** a hardware `FUNC_SEL` readback.
The earlier conclusion “unclaimed, so not muxed” is **DISPROVED**.

The OEM state is mixed: MUX2 on GPIO21/22 and MUX3 on GPIO23/25/26/27,
while MCL GPIO20/24 remain `func=0`. This supersedes the “either MUX2 or
MUX3” reading. Why the profile’s MCL function is not applied, or is later
reset, remains **UNKNOWN** (Q77).

## 5. What would confirm the group

| Unknown | Needs |
|---|---|
| which of MUX2/MUX3 is populated | board table dump (`avm_get_hw_config_table` output) |
| whether AVM passes FUNC_SEL 2/3 through unchanged | `dakota_gpio_pinconfig()` body, not in the GPL drop |
| observed FUNC_SEL under FRITZ!OS | kernel `debugfs` pinmux, read-only |
| actual FUNC_SEL under OpenWrt | reviewed read-only TLMM register readback |
| whether pads reach the SC14448 | continuity, or a schematic |
