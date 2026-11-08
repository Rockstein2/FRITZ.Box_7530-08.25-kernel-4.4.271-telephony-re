# SC14448 UART and reset: what the sources establish

> **Status: historical analysis.**
> This document records the reasoning and evidence as of the date it was
> written.  Some of its `UNKNOWN` / `UNVERIFIED` markers have since been
> answered.
> - Current confirmed facts: `../fon-known-facts.md`
> - Current open questions: `../fon-open-questions.md`
> - This file is kept for the reasoning trail, not as a status report.

Status: **offline source and compiled-DTB analysis.**  L1 (DTS/DTB/bindings),
L2 (driver code), L3 (measured Stage A facts already in
`../fon-known-facts.md`).  Nothing here was measured in this iteration.

**Corrected finding (2026-11-08).**  An earlier revision of this document
claimed that the HW236 `serial_pins` override *drops* `function` and
`bias-disable`.  That was **wrong**: `dtc` merges a repeated node's properties,
so the base `function` and `bias-disable` survive.  The claim is now settled
by decompiling the **compiled** DTB, not by reasoning about the sources
(§1.2).  Every conclusion that depended on the wrong reading is withdrawn.

The correct, narrower conclusion is: **the AVM DECT loader and the OpenWrt
console use the same known UART controller (`blsp_uart0` @ `0x78AF000`).  No
independent second UART path was found.**  That is *not* a proof that no other
UART hardware or route exists on the board, and it is *not* a proof that the
four console pads reach the SC14448.

---

## 1. The UART, traced through the sources *and the DTB*

### 1.1 Source fragments

| Step | Source | What it says |
|---|---|---|
| `serial0` is the console | `Fritz_qcom-ipq4019.dtsi:76,81` | `serial0 = &blsp_uart0; stdout-path = "serial0"` |
| `blsp_uart0` is the IPQ4019 BLSP1 UART at `0x78AF000` | `Fritz_qcom-ipq4019.dtsi:109` | `blsp_uart0: serial@78af000` |
| its pins are `serial_pins` | `Fritz_qcom-ipq4019.dtsi:110` | `pinctrl-0 = <&serial_pins>` |
| the base pins are `gpio60`/`gpio61` with `function = "blsp_uart0"` and `bias-disable` | `Fritz_qcom-ipq4019.dtsi:86` | full mux entry |
| **HW236 redeclares the pins as `gpio16`/`gpio17`** | `Fritz_Box_HW236.dtsi:124` | same node name `serial_pins`, `pins = "gpio16","gpio17"`; `function`/`bias` are **not repeated** |
| `serial@78b0000` is **disabled** | `Fritz_Box_HW236.dtsi:213` | `status = "disable"` |
| AVM attaches the DECT loader to one probed port | `msm_serial.c:1886-1908` | `msm_dectuart_probe()`, see §2 |
| no `avm,dectstub_uart` node exists in HW236 | `grep` over the DT sources **and** the DTB | absent — the driver comment "fallback: 7530/7520: no devicetree-entry" applies |
| GPIO16 is also named `gpio_avm_dect_rd` | `Fritz_Box_HW236.dtsi:340`; DTB `value = <0x10>` | GPIO 16, no parameter |

### 1.2 Compiled-DTB evidence (settles the merge question)

The AVM HW236 DTB was extracted from the OEM kernel image and decompiled.  The
DTB is the ground truth; the two `.dtsi` fragments above only *suggested* the
answer.

| Item | Value |
|---|---|
| Source | OEM kernel image `vmlinux` inside `/tmp/opencode/fw825/var/tmp/kernel.image` |
| Extraction | first FDT magic `d00dfeed` with a self-consistent `totalsize` |
| File | `/tmp/opencode/dtb_98d038.dtb` |
| SHA256 | `3083e2acedc800015fea5ee7e57fa6cc8da551e21ee792095cbd8a7224bb841f` |
| Size | 26 963 bytes |
| Model | `"AVM FRITZ!Box 7530"` |
| Commands | `dtc -I dtb -O dts dtb_98d038.dtb > dtb_avm.dts` |
| Tool | `dtc` version 1.7.0 |

The decompiled `serial_pinmux` node:

```
serial_pinmux {
        linux,phandle = <0x0e>;
        phandle = <0x0e>;

        mux {
                pins = "gpio16\0gpio17";
                function = "blsp_uart0";
                bias-disable;
        };
};
```

So the base `function` and `bias-disable` **survive the merge**.  Provenance:

| Property | Comes from | How it survives |
|---|---|---|
| `pins = "gpio16","gpio17"` | HW236 fragment | replaces the base `gpio60/61` value |
| `function = "blsp_uart0"` | base `Fritz_qcom-ipq4019.dtsi` | not repeated in HW236, so `merge_nodes()` keeps the base value |
| `bias-disable` | base `Fritz_qcom-ipq4019.dtsi` | same |

The base `blsp_uart0` node in the same DTB:

```
serial@78af000 {
        compatible = "qcom,msm-uartdm-v1.4\0qcom,msm-uartdm";
        reg = <0x78af000 0x200>;
        interrupts = <0x00 0x6b 0x00>;
        status = "ok";
        clocks = <0x04 0x1a 0x04 0x15>;
        clock-names = "core\0iface";
        tx-watermark = <0x00>;
        pinctrl-0 = <0x0e>;      /* == serial_pinmux above */
        pinctrl-names = "default";
};
```

`serial@78b0000` in the same DTB has `status = "disable"`.  There is **no**
`avm,dectstub_uart` node.

A direct `dtc` merge test confirmed the semantics independently:

```
base:  mux { pins="gpio60","gpio61"; function="blsp_uart0"; bias-disable; }
hw236: mux { pins="gpio16","gpio17"; }
=>     mux { pins="gpio16","gpio17"; function="blsp_uart0"; bias-disable; }
```

### 1.3 Comparison with OpenWrt

OpenWrt DTB source: `openwrt-25.12.6-source/build_dir/.../linux-ipq40xx_generic/image-qcom-ipq4019-fritzbox-7530.dtb`
(kernel 6.12 tree), SHA256
`cd6c5deca1e28531b3da0025c1a8a329b7aad60f9ca59da5d48530a226f4522e`.

| Parameter | AVM HW236 | OpenWrt 7530 |
|---|---|---|
| UART controller | `serial@78af000` | `serial@78af000` |
| Base address | `0x78AF000`, size `0x200` | `0x78AF000`, size `0x200` |
| TX GPIO | `gpio16` or `gpio17` — **direction UNKNOWN** | same |
| RX GPIO | the other of `gpio16`/`gpio17` — **direction UNKNOWN** | same |
| `function` | `blsp_uart0` | `blsp_uart0` |
| bias | `bias-disable` | `bias-disable` |
| UART `status` | `ok` | `okay` |
| Console binding | alias `serial0 = "/soc/serial@78af000"`; `stdout-path = "serial0"` | **no `serial0` alias** and no `stdout-path` in this DTB; console comes from the OpenWrt bootargs |
| `serial@78b0000` | `disable` | `disabled` |

The pinmux is effectively identical.  The only meaningful difference in this
comparison is the **console binding**: AVM wires `serial0`/`stdout-path` in the
DTB, OpenWrt does not (it uses its own bootloader command line).

**Direction is not encoded anywhere in the DT.**  `pins = "gpio16","gpio17"`
does not say which is TX; the order is not a direction.  The IPQ4019 pinctrl
driver knows the RX/TX pair per function, but the DTB does not state it and no
source consulted here states the assignment.  **TX/RX per GPIO: UNKNOWN.**

### 1.4 DECT port selection in the driver (§4 detail)

`msm_serial.c`:

```
static void msm_dectuart_probe(struct uart_port *port, int line)
{
        np = of_find_compatible_node(NULL, NULL, "avm,dectstub_uart");
        if (np) {
                of_property_read_u32(np, "line", &uart_line);
                if (uart_line == line)
                        msm_dectuart.port = port;
        } else if (msm_dectuart.port == NULL) {
                /* fallback: 7530/7520: no devicetree-entry */
                msm_dectuart.port = port;
        }
        if (msm_dectuart.port == port) {
                pr_info("%s: set dectuart_port to ttyMSM%d\n", ...);
                msm_dectuart.msm_dectuart_put_char = ...;
                ...
        }
}
```

Facts:

1. `msm_dectuart_probe()` is called per probed `uart_port` (from the driver's
   probe path).
2. With **no** `avm,dectstub_uart` node — the HW236 case — the **first** port
   that probes becomes the DECT port (`port == NULL` guard), and the console
   port is available and `status = "ok"`.
3. Therefore the DECT port is `ttyMSM0`, the console port, **for this DTS**.
   This is confirmed by the driver's own `pr_info` string and by the Stage A
   fact in `../fon-known-facts.md` (`0.39 s  msm_dectuart_probe -> ttyMSM0`).
4. **Caveat:** selection depends on probe order and on the DTS actually being
   the one the kernel booted.  A different DTS with another enabled UART could
   select a different port.  The statement is correct *for this
   configuration*, not as a board invariant.

## 2. GPIO40 (DECT reset) and GPIO16 (`dect_rd`)

| Fact | Source | Level |
|---|---|---|
| board table: `gpio_avm_dect_reset` = **GPIO40**, `OUT_ACTIVE_HIGH` | `Fritz_Box_HW236.dtsi:336`; DTB `value = <0x28>`, `param = <0x0b>` | L1 |
| board table: `gpio_avm_dect_rd` = **GPIO16** | `Fritz_Box_HW236.dtsi:340`; DTB `value = <0x10>` | L1 |
| no Linux driver claims GPIO40 | Stage A `pin 40 (MUX UNCLAIMED)` | L3 |
| the pad is configured as **input** and reads **0** | Stage A capture | L3 |

`OUT_ACTIVE_HIGH` (`param = 0x0b`) is an **AVM software convention** for its
GPIO abstraction; it says nothing about the electrical polarity at the SC14448
reset pin, which may be active-low.  Whether "reads 0" means "reset asserted"
depends on an unlocated pull resistor.  **Electrical polarity: UNKNOWN.**

### Searching for `gpio_avm_dect_rd` in the code

| Where searched | Result |
|---|---|
| AVM GPL kernel tree (`.c`/`.h`) | **no reference** to `dect_rd` |
| `Piglet_noemif.ko` (proprietary, `lib/modules/4.4.271/piglet_noemif/`) | string `gpio_avm_dect_rd` present; `dakota_gpio_in_bit` is imported twice |
| call site 1 | `piglet_init` — configures a board signal at init |
| call site 2 | `XBIT_WriteData.constprop.1` — also calls `dakota_gpio_in_bit` |

The string is used to **look up the board profile by name**, and
`dakota_gpio_in_bit` is a generic GPIO read helper.  Nothing consulted shows
`dect_rd` being read as "DECT UART RX"; and GPIO16 is already muxed as
`blsp_uart0`, so a second GPIO-level read of the same pin would read the UART
signal, not a clean GPIO.  **The role of `gpio_avm_dect_rd` and whether it
conflicts with the UART mux: UNKNOWN.**  It must not be assumed to be the UART
RX direction.

## 3. What is *not* established

| Question | Status |
|---|---|
| do the four Dialog-side test pads reach `gpio16`/`gpio17` | **UNKNOWN** — the owner's shell proves the pads carry `blsp_uart0` (the port *is* the console), but the pads are near the SC14448 and far from the IPQ4019; the trace has not been followed |
| does the UART reach the SC14448 at all, and how | **UNKNOWN** — no schematic; the driver uses the port but nothing in the sources shows the board route to the Dialog |
| which pad/GPIO is TX and which is RX | **UNKNOWN** |
| is there a series resistor, mux, buffer or level shifter between SoC and Dialog | **UNKNOWN** |
| voltage on the test pads | **UNKNOWN** — not measured |
| voltage on the SC14448 side | **UNKNOWN** — do not assume 1.8 V or 3.3 V |
| GPIO40 electrical polarity at the chip | **UNKNOWN** |
| whether the Dialog is powered at all under OpenWrt | **UNKNOWN** |

## 4. Candidate physical points

| Object | Location | Function | Evidence | Confidence |
|---|---|---|---|---|
| four test pads | near the SC14448, per the owner | console UART on `blsp_uart0` | owner connects `/dev/ttyUSB0` at 115200 8N1 and gets a shell | **confirmed** (functional) |
| `gpio16` / `gpio17` | IPQ4019 TLMM pins | `blsp_uart0` | base DTSI `function` + compiled DTB (`function = "blsp_uart0"`, `bias-disable`) | **source + DTB confirmed** |
| `gpio16` as `dect_rd` | AVM board table (DTB `value = <0x10>`) | DECT "read" | name only; no code reads it as RX | **logical only** |
| pad order = TX/RX | — | — | not encoded in DT | **UNKNOWN** |
| Dialog RX | UNKNOWN | firmware input | needs tracing or measurement | **unknown** |
| Dialog TX | UNKNOWN | boot responses | needs tracing or measurement | **unknown** |
| GPIO40 net | UNKNOWN | DECT reset | DTB `value = <0x28>` | **logical only** |

## 5. What the sources do and do not rule out

**Ruled out for this DTS**

* a second *enabled* UART in the HW236 DTB — `serial@78b0000` is `disable`;
* a DECT-specific DT node selecting a different port — no
  `avm,dectstub_uart` node, so the driver takes the fallback.

**Not ruled out**

* other UART-capable controllers on the SoC that DTS does not enable;
* a mux, buffer or level shifter *between* the SoC pin and the Dialog;
* a separate physical route from `gpio16`/`gpio17` to the SC14448;
* the possibility that the test pads are only an *observation* tap and the
  Dialog sits on another net.

## 6. Photographs still needed

1. The area around the four console pads at macro distance, showing any
   series resistors and where the traces head (towards the IPQ4019 or the
   SC14448).
2. The SC14448 package and its immediate surroundings, at a resolution where
   the BGA ball rows can be counted.
3. Any level-shifter-like package (small SOT/SOIC) between the SoC and the
   Dialog.
4. The GPIO40 net: a resistor or via that can be identified on the board.

Without (1) and (2) at sufficient resolution, the physical path from
`gpio16`/`gpio17` to the Dialog cannot be called even *probable*.
