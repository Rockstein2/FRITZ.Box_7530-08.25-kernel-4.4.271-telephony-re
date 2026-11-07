# SC14448 vs TobleMiner CR16C register map

Status: **offline correlation.**  The reference targets **SC14441**; a match
is a candidate, never proof for the SC14448.

Reference: [TobleMiner/dialog-cr16c-uart-boot](https://github.com/TobleMiner/dialog-cr16c-uart-boot),
commit `3d041a68`, MIT, Copyright 2022 Tobias Schramm.  Files read:
`uart.h`, `irq.h`, `clock.h`, `gpio.h`, `watchdog.h`, `system.h`,
`chipid.h`, `qspi.h`.

Report: `tools/reports/cr16-external-register-map.json`.

---

## 1. How the comparison is made

`tools/cr16_external_register_map.py` extracts every `MMIOxx(0x....)`
definition, joins it with `peripheral-xrefs.json` **and** with a fresh scan
of the first-level image, and labels each register:

| Level | Meaning |
|---|---|
| `FUNCTIONAL_REGISTER_MATCH` | the same address is accessed with the same width **and** the sequence matches the reference semantics |
| `ACCESS_MATCH` | the same address, compatible width, no sequence evidence |
| `ADDRESS_ONLY` | the same address, different width or no sequence evidence |
| `LOW_BITS_ONLY` | the exact address is absent, but the low 20 bits appear under another high half |
| `NOT_FOUND_IN_OUR_IMAGE` | absent |

## 2. UART — the strongest result

| Reference | Name | Our image |
|---|---|---|
| `0x00FF4900` | `UART_CTRL_REG` | **absent**; `0x000F4900` is used (first-level) |
| `0x00FF4902` | `UART_RX_TX_REG` | absent; `0x000F4902` used |
| `0x00FF4904` | clear TX interrupt | absent; `0x000F4904` used |
| `0x00FF4906` | clear RX interrupt | absent; `0x000F4906` used |

**The semantics match bit for bit:**

| Observation | Reference | Our first-level |
|---|---|---|
| receive status bit | `UART_CTRL_REG_RI = 1<<6` | `0x102AC tbit $6,r0` |
| transmit status bit | `UART_CTRL_REG_TI = 1<<5` | `0x102DA tbit $5,r0` |
| data register | `0xFF4902` read/write | `0x102BE loadw`, `0x102CE storw` |
| clear TX/RX | write 1 to `0xFF4904`/`0xFF4906` | `storw $1` to `0x000F4904`/`0x000F4906` |
| baud field | bits 2–4 | `0x100EA andw $0xFFE3`, `0x100EE orw $0x000C` → field = 3 = **115200** |

This is a `FUNCTIONAL_REGISTER_MATCH`: not only the address bits but the
entire bit layout agrees.  It is still **not** an alias proof — see §4.

## 3. Other registers

| Reference | Name | Ours (exact) | Level |
|---|---|---|---|
| `0x00FF4000` | `CLK_AMBA_REG` (HCLK/PCLK dividers) | `0x000F4000` used | ADDRESS_LOW_BITS only |
| `0x00FF4836` | GPIO port 0 direction | `0x000F4836` used | low bits only |
| `0x00FF4838` | GPIO port 0 mode | `0x000F4838` used | low bits only |
| `0x00FF4856` / `0x00FF4858` | GPIO port 2 direction / mode | used | low bits only |
| `0x00FF4860` / `0x00FF4866` / `0x00FF4868` | GPIO port 3 | used | low bits only |
| `0x00FF4C00` | `WATCHDOG_REG`, written `0xff` | `0x000F4C00`, written `0xFF` | `ADDRESS_ONLY` |
| `0x00FF5402` | reset interrupt pending | `0x000F5402`, 7 writes | low bits only |
| `0x00FF5404` / `0x00FF5406` | interrupt priority 0/1 | **same address** used in both images | `ACCESS_MATCH` |

### Watchdog

The reference does `WATCHDOG_REG = 0xff`.  Our first-level does
`0x102A0 storw $0xFF,0x000F4C00` and `0x102CA storw $0xFF,0x000F4C00`,
inside the two wait loops of the receive/send helpers.  Same address low
bits, same width (16-bit), **same written value**, same functional role
(a kick inside a polling loop).  This is the strongest single-register
correspondence in the set.

## 4. What this does and does not establish about aliasing

| Address pair | Low bits | Width | Written value | Function | Same SoC | Hardware | Confidence |
|---|---|---|---|---|---|---|---|
| `0x000F4900` ↔ `0x00FF4900` | match | 16 | n/a | **UART status, same bits** | both SC1x448/441 family | none | **high** |
| `0x000F4C00` ↔ `0x00FF4C00` | match | 16 | `0xFF` = `0xFF` | watchdog kick | family | none | **high** |
| `0x000F5402` ↔ `0x00FF5402` | match | 16 | one bit per source | pending clear | family | none | medium |
| `0x000F4000` ↔ `0x00FF4000` | match | 16 | unknown | clock dividers | family | none | low |

**The answer on physical aliasing is still UNKNOWN.**  What changed is the
kind of evidence: we no longer have only "the low 20 bits match", we have
"two independent implementations use the same bit layout at these low
addresses".  That is `FUNCTIONAL_REGISTER_MATCH`, not a documented alias and
not a hardware measurement.

A plausible model that fits everything: the peripherals decode the low 20
bits and the `0x00F00000` bit is a **mapping attribute** (for example a
bus/alias window or an access-mode select) rather than part of the address.
No offline source states this, so it remains a hypothesis.

## 5. Registers in the reference that we do **not** use

`SET_INT_PENDING_REG` (`0x00FF5400`),
`CLK_AUX2_REG` (`0x00FF402E`), `DEBUG_REG` (`0x00FF5004`), the chip-ID bytes
at `0x00FFFBF8`–`0x00FFFBFC`, and the QSPI block.  `INT3_PRIORITY_REG`
(`0x00FF540A`) is absent at the exact address but `0x000F540A` is written by
the second-level image.  Their absence in our
firmware is a fact; its meaning is unknown.
