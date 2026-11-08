# FON D0.6 — current result

> **Current status page.** This is the entry point for D0.6. Detailed reverse-
> engineering records live under `history/`; executable procedures live under
> `runbook/`. If a historical D0.6 report conflicts with this page,
> `fon-known-facts.md`, or `fon-open-questions.md`, the current files win.

## Outcome

D0.6 recovered the Linux-side reset and pinmux paths but did **not** establish
the electrical reset polarity or authorize an active reset/upload.

| Topic | Current answer | Status |
|---|---|---|
| GPIO40 owner in FRITZ!OS | `Piglet_noemif.ko`, `dect_loader()` | **CONFIRMED** |
| Reset profile entry | OEM DTB `gpio_avm_dect_reset`: GPIO40, `param=0x0b`; `get_profile()` stores it at `profile+0x28` | **CONFIRMED** |
| Loader order | API value 0 → delay → `msm_dectuart_init()` → API value 1 → firmware transfer | **CONFIRMED** |
| Electrical level at GPIO40/SC14448 reset | not established by the API arguments | **UNKNOWN** |
| Hardware inversion between GPIO40 and SC14448 | no electrical connection proven | **UNKNOWN** |
| PINMUX2/PINMUX3 values | OEM DTB `function=<2>/<3>`; Linux TLMM selector indices are 2/3 | **CONFIRMED** |
| AVM pinmux owner | `pcmlink.ko:ipq40xxtdm_linkinit()` calls `dakota_gpio_pinconfig()` | **CONFIRMED** |
| AVM API transformation of 2/3 | body of `dakota_gpio_pinconfig()` unavailable | **UNKNOWN** |
| Clock check | `Piglet_noemif.ko:Check_TDMInterface()` reads FSC/DCL as GPIO inputs and counts edges | **CONFIRMED** |
| Active physical mux group/wiring | software names and selectors do not prove PCB connectivity | **UNKNOWN** |
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

The compiled HW236 DTB was extracted offline from the EVA/LZMA OEM kernel:

| Property | Value |
|---|---|
| Decompressed-kernel offset | `0x98d038` |
| Size | `26963` bytes |
| SHA256 | `3083e2acedc800015fea5ee7e57fa6cc8da551e21ee792095cbd8a7224bb841f` |
| Model | `AVM FRITZ!Box 7530` |

The binary remains outside Git. Reproduction instructions are in
`runbook/fon-oem-dtb-extraction.md`.

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
