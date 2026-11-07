# SC14448 UART and reset: what the sources establish

Status: **offline source analysis.**  L1 (DTS/bindings), L2 (driver code),
L3 (measured Stage A facts already in `fon-known-facts.md`).  Nothing here was
measured in this iteration.

**The headline result changes the Stage D0 plan**: the DECT UART is the
**same** `blsp_uart0` that carries the OpenWrt console on `gpio16`/`gpio17`.
There is no evidence of a second UART, of a level shifter, or of a separate
SC14448 pin pair on this board.

---

## 1. The UART, traced through the sources

| Step | Source | What it says |
|---|---|---|
| `serial0` is the console | `Fritz_qcom-ipq4019.dtsi:76,81` | `serial0 = &blsp_uart0; stdout-path = "serial0"` |
| `blsp_uart0` is the IPQ4019 BLSP1 UART at `0x78AF000` | `Fritz_qcom-ipq4019.dtsi:109` | `blsp_uart0: serial@78af000` |
| its pins are `serial_pins` | `Fritz_qcom-ipq4019.dtsi:110` | `pinctrl-0 = <&serial_pins>` |
| the base pins are `gpio60`/`gpio61` with `function = "blsp_uart0"` | `Fritz_qcom-ipq4019.dtsi:86` | full mux entry |
| **HW236 overrides the pins to `gpio16`/`gpio17`** | `Fritz_Box_HW236.dtsi:124` | same node name `serial_pins`, `pins = "gpio16","gpio17"`, **no `function`** |
| the override **drops** both `function` and `bias-disable` | DT semantics | a labelled node redefinition replaces the sub-node contents.  `serial_pins: serial_pinmux { mux { pins = "gpio16","gpio17"; } }` has **no** `function` and **no** `bias`, so the pinctrl driver applies the **default function** of those pins and the **default bias**.  For IPQ4019 `gpio16`/`gpio17` the default function is GPIO, not `blsp_uart0` |

**Consequence.**  On this board the console works in practice (the owner
gets a shell), so *something* muxes `gpio16`/`gpio17` to the UART.  Two
readings are possible and the sources here do not separate them:

1. the SoC's default function for `gpio16`/`gpio17` **is** `blsp_uart0`
   (so the empty `function` is harmless), or
2. a later DT fragment or the bootloader programs the mux, and the
   `serial_pins` override is incomplete.

This is a real uncertainty about **how the pins reach the UART**, not about
**which UART** (that is fixed by `blsp_uart0`).
| `serial@78b0000` is **disabled** | `Fritz_Box_HW236.dtsi:213` | `status = "disable"` — this is BLSP1 QUP1, not a hint of a second console |
| AVM attaches the DECT loader to the same port | `msm_serial.c:1886-1908` | `msm_dectuart_probe()`: if no `avm,dectstub_uart` node exists, the **first** probed port becomes the DECT port, and it logs `set dectuart_port to ttyMSM%d` |
| no `avm,dectstub_uart` node exists in HW236 | `grep` over the DT sources | absent — so the document's own comment "fallback: 7530/7520: no devicetree-entry" applies |
| GPIO16 is also named `gpio_avm_dect_rd` | `Fritz_Box_HW236.dtsi:340` | `value = <16>`, no parameter |

### What this means

1. **`ttyMSM0` is both the console and the DECT UART.**  Not two ports: one
   `uart_port`, shared by the console and by the loader (`fon-dialog-minimal-loader.md` §3 already said this; the DTS now shows *why*).
2. `gpio16` carries `blsp_uart0` **RX or TX**, and is *also* the board's
   "dect_rd" signal.  The `rd` name suggests "read", i.e. the SoC's receive
   line, but that is a **name**, not a measured direction (see §3).
3. There is **no evidence of a level shifter** in the DT and no second UART.
   The IPQ4019 TLMM `gpio16`/`gpio17` are 1.8 V-domain pins by SoC design;
   whether the SC14448 side is directly connected at that level is
   **UNKNOWN**.

## 2. GPIO40 (DECT reset)

| Fact | Source | Level |
|---|---|---|
| board table: `gpio_avm_dect_reset` = GPIO40, `OUT_ACTIVE_HIGH` | `Fritz_Box_HW236.dtsi:336` | L1 |
| no Linux driver claims GPIO40 | Stage A `pin 40 (MUX UNCLAIMED)` | L3 |
| the pad is configured as **input** and reads **0** | Stage A capture | L3 |

`OUT_ACTIVE_HIGH` is an **AVM software convention** for a GPIO abstraction
layer; it says nothing about the electrical polarity at the SC14448 reset
pin, which may be active-low.  Whether "reads 0" means "reset asserted"
depends on a pull resistor that has not been located.  **UNKNOWN.**

## 3. What is *not* established

| Question | Status |
|---|---|
| do the four Dialog-side test pads reach `gpio16`/`gpio17` | **UNKNOWN** — no schematic; the owner's working console proves the pads carry `blsp_uart0`, since that port *is* the console, but it does not prove the pads reach the Dialog |
| which pad is TX and which is RX | **UNKNOWN** — needs a passive measurement |
| is there a series resistor or level shifter between SoC and Dialog | **UNKNOWN** |
| SC14448 side voltage | **UNKNOWN** — do not assume 1.8 V or 3.3 V |
| GPIO40 electrical polarity at the chip | **UNKNOWN** |
| whether the Dialog is powered at all under OpenWrt | **UNKNOWN** |

## 4. Candidate physical points

| Object | Location | Function | Evidence | Confidence |
|---|---|---|---|---|
| four test pads | under the Dialog shield, per the friXtender teardown | console UART on `blsp_uart0` | owner connects `/dev/ttyUSB0` at 115200 8N1 and gets a shell | **confirmed** (functional) |
| `gpio16` / `gpio17` | IPQ4019 TLMM pins | `blsp_uart0` RX/TX | `serial_pins` override + base `function` | **source-confirmed** |
| `gpio16` as `dect_rd` | AVM board table | DECT receive | name only | **logical only** |
| Dialog RX | UNKNOWN | firmware input | needs tracing or measurement | **unknown** |
| Dialog TX | UNKNOWN | boot responses | needs tracing or measurement | **unknown** |
| GPIO40 net | UNKNOWN | DECT reset | board table | **logical only** |

## 5. What the sources rule out

* **A second UART.**  `serial@78b0000` is disabled, and the DECT port is
  chosen by "first probed port", i.e. the console port.
* **A DECT stub device node** on this board: there is none, which is exactly
  why the driver takes the fallback path.
* **A separate "DECT console" pin pair** declared anywhere in the DT.

## 6. Photographs still needed

1. The area around the four console pads at macro distance, showing the
   series resistors (if any) and where the traces go.
2. The SC14448 package and its immediate surroundings, at a resolution where
   the BGA ball rows can be counted.
3. Any level-shifter-like package (small SOT/SOIC near the Dialog).
4. The GPIO40 net: a resistor or via labelled on the board.

Without (1) and (2) at sufficient resolution, the physical path from
`gpio16`/`gpio17` to the Dialog cannot be called even *probable*.
