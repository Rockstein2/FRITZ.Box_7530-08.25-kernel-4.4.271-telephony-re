# FON D0.6 — current result

> **Current status page.** This is the entry point for D0.6. Detailed reverse-
> engineering records live under `history/`; executable procedures live under
> `runbook/`. If a historical D0.6 report conflicts with this page,
> `fon-known-facts.md`, or `fon-open-questions.md`, the current files win.

## Outcome

D0.6 recovered the Linux-side reset and pinmux paths. The OEM 08.25 live
readback later supplied the actual OEM-side `FUNC_SEL` and GPIO40 state; the
OpenWrt-side values, electrical reset polarity and physical PCM wiring remain
unknown. D0.6 did not authorize an active reset/upload.

| Topic | Current answer | Status |
|---|---|---|
| GPIO40 owner in FRITZ!OS | `Piglet_noemif.ko`, `dect_loader()` | **CONFIRMED** |
| Reset profile entry | OEM DTB `gpio_avm_dect_reset`: GPIO40, `param=0x0b`; `get_profile()` stores it at `profile+0x28` | **CONFIRMED** |
| Loader order | API value 0 → delay → `msm_dectuart_init()` → API value 1 → firmware transfer | **CONFIRMED** |
| Electrical level at GPIO40/SC14448 reset | not established by the API arguments | **UNKNOWN** |
| Hardware inversion between GPIO40 and SC14448 | no electrical connection proven | **UNKNOWN** |
| PINMUX2/PINMUX3 values | OEM DTB `function=<2>/<3>`; Linux TLMM selector indices are 2/3 | **CONFIRMED (DTB/value)** |
| AVM pinmux owner | `pcmlink.ko:ipq40xxtdm_linkinit()` calls `dakota_gpio_pinconfig()` | **CONFIRMED (call site)** |
| AVM API transformation of 2/3 | body of `dakota_gpio_pinconfig()` unavailable | **UNKNOWN** |
| OEM live GPIO40 | `OUT func=0 val=1`, `TLMM_GPIO_CFG=0x00004a02` | **CONFIRMED (OEM-CAPTURE)** |
| OEM live PCM `FUNC_SEL` | GPIO21/22=2; GPIO23/25/26/27=3; GPIO20/24=0 | **CONFIRMED (OEM-CAPTURE)** |
| `pinmux-pins` vs actual mux | OEM shows `MUX UNCLAIMED` for GPIO20–27 while `/proc/avm/gpio/list` shows func 2/3 | **CONFIRMED (not a hardware readback)** |
| Actual hardware `FUNC_SEL` under OpenWrt | Linux reports no mux owner, but that is not a TLMM register readback | **UNKNOWN** |
| Clock check | `Piglet_noemif.ko:Check_TDMInterface()` calls `dakota_gpio_ctrl(gpio,0,0)` and counts edges; it does not generate clocks | **CONFIRMED (code)** |
| Piglet ctrl side effects | `dakota_gpio_ctrl()` may change pad configuration; body unavailable | **UNKNOWN** |
| Active physical mux group/wiring | software names and selectors do not prove PCB connectivity | **UNKNOWN** |
| OEM DTB selection | three HW236 DTBs in `kernel.image`; FON properties identical, only `subrevision` differs. OEM runtime log and live FDT report `HWS(2)`, matching the first blob | **board subrevision CONFIRMED; bootloader choice UNKNOWN (Q80)** |
| 74LVC1G04 role | measurements exist only under OpenWrt; no connection to GPIO40/reset proven | **UNKNOWN** |
| First missing OpenWrt startup actions | no recovered reset sequence and no firmware upload are performed | **CONFIRMED (software state)** |
| Why FSC/BCLK are absent/present on this board | not passively measured on an identified net | **UNKNOWN** |

## Exact recovered order

Both `dect_loader()` branches initialise the UART before releasing the reset
API state:

```text
0xb44  dakota_gpio_ctrl(gpio, 0, 1)
0xb54  dakota_gpio_out_bit(gpio, 0)   API assert state
        delay
0xb80  msm_dectuart_init(...)
0xb9c  dakota_gpio_out_bit(gpio, 1)   API release state
        settle delay, firmware loader continues
```

Second branch: `msm_dectuart_init()` at `0xd10`, API value 1 at `0xd28`.
API arguments 0/1 must not be promoted to physical pad or SC14448 pin levels
without the `dakota_gpio_out_bit()` implementation and electrical evidence.

## OEM DTB provenance

The EVA/LZMA OEM kernel contains **three** self-consistent HW236 DTBs. They
share the same model, compatible string, GPIO, UART and TDM properties; the
only difference found in the decompiled trees is `avm-hw-revision/subrevision`.

| Decompressed offset | Size | SHA256 | Subrevision |
|---|---:|---|---|
| `0x98d038` | `26963` | `3083e2acedc800015fea5ee7e57fa6cc8da551e21ee792095cbd8a7224bb841f` | `2` |
| `0x993990` | `26963` | `497fe05825d104c7d781729ce37e2f9cb101cccb85bdcbdab67be1eb1aedb4f4` | `0` |
| `0x99a2e8` | `26963` | `497fe05825d104c7d781729ce37e2f9cb101cccb85bdcbdab67be1eb1aedb4f4` | `0` |

The repository analyses the first blob. The OEM 08.25 runtime capture reports
`HWS(2)`, so this board's hardware subrevision is **2** and the first blob
matches it (`reference/oem-08.25-boot/`). That still does **not** prove which
blob the OEM bootloader selects (Q80). Because the FON-relevant properties are
identical in all three, D0.6 conclusions do not depend on that choice.

The binaries remain outside Git. Reproduction and comparison instructions are
in `runbook/fon-oem-dtb-extraction.md`.

## Document map

### Current

| File | Purpose |
|---|---|
| `fon-d06-summary.md` | D0.6 outcome and status |
| `fon-known-facts.md` | project-wide confirmed facts |
| `fon-open-questions.md` | unresolved items only |
| `fon-go-no-go.md` | authorization gates |
| `runbook/fon-stage-d06-readonly.md` | later read-only OpenWrt collection |
| `runbook/fon-oem-dtb-extraction.md` | reproducible offline OEM DTB extraction |

### Historical evidence

| File | Purpose |
|---|---|
| `history/fon-d06-dect-reset-path.md` | instruction-level reset reconstruction |
| `history/fon-d06-pcm-pinmux.md` | pinmux disassembly and TLMM derivation |
| `history/fon-d06-sc14448-startup-sequence.md` | detailed startup reconstruction |
| `history/fon-d06-inverter-hypotheses.md` | explicitly unproven inverter alternatives |

## Gate after D0.6

Read-only state collection is documented and may be run only when separately
requested. D0.6 does **not** authorize GPIO40 output/toggle, reset assertion or
release, firmware upload, TLMM writes, clock/reset control, DMA, C4, or analog
line activity.
