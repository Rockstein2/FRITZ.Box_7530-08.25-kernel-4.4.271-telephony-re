# SC14448 vs TobleMiner CR16C register map

> **Status: historical analysis.**
> This document records the reasoning and evidence as of the date it was
> written.  Some of its `UNKNOWN` / `UNVERIFIED` markers have since been
> answered.
> - Current confirmed facts: `../fon-known-facts.md`
> - Current open questions: `../fon-open-questions.md`
> - This file is kept for the reasoning trail, not as a status report.

Status: **offline correlation.**  The reference targets **SC14441**; a match
is a candidate, never proof for the SC14448.

Reference: [TobleMiner/dialog-cr16c-uart-boot](https://github.com/TobleMiner/dialog-cr16c-uart-boot),
commit `3d041a68`, MIT, Copyright 2022 Tobias Schramm, and its fork
[vincentscode/dialog-cr16c-uart-boot](https://github.com/vincentscode/dialog-cr16c-uart-boot),
commit `9e413b55`.  The fork adds a chip table, more peripherals and — the
reason it matters here — an **SC14448 entry**.  Files read:
`uart.h`, `irq.h`, `clock.h`, `gpio.h`, `watchdog.h`, `system.h`,
`chipid.h`, `qspi.h`, `power.h`, `spi.h`, `display.h`, `debug.h`, `flash.h`,
`dma.h`, `chip_config.h`.

## 0. The fork's chip table

`device/chip_config.h` declares five chips; the SC14448 entry is:

```c
#elif defined(CHIP_SC14448)
    #define CHIP_NAME        "SC14448"
    #define CHIP_ID_DECIMAL  448
    // 16K SHARED_RAM (0x10000-0x13FFF) (this is just a guess)
    #define CHIP_RAM_ORIGIN  0x00010000
    #define CHIP_RAM_LENGTH  0x00004000
    #define CHIP_HAS_QSPI    1
```

Two facts and one caveat:

* every chip in the table uses `CHIP_RAM_ORIGIN = 0x00010000`, so the
  `0x10080` load address of our first-level image sits inside the shared-RAM
  window by the reference's own convention;
* the fork's README lists **`Gigaset C430 / SC14448` as tested**, i.e. the
  toolchain demonstrably runs on this SoC;
* the RAM size is marked *"this is just a guess"* in the source, so it is
  **not** evidence for the actual memory size.

Report: `tools/reports/cr16-external-register-map.json`.

---

## 1. How the comparison is made

`tools/cr16_external_register_map.py` extracts every `MMIOxx(0x....)`
definition, joins it with `peripheral-xrefs.json` **and** with a fresh scan
of the first-level image, and labels each register:

| Level | Meaning |
|---|---|
| `FUNCTIONAL_REGISTER_MATCH` | an entry in `MANUAL_EVIDENCE` names the exact instructions that were compared with the reference, and — where a value matters — the stored immediate is checked against it |
| `ACCESS_MATCH` | the same address, compatible width, **no sequence or value evidence** |
| `ADDRESS_ONLY` | the same address, but the width or value does not line up |
| `LOW_BITS_ONLY` | the exact address is absent, but the low 20 bits appear under another high half |
| `NOT_FOUND_IN_OUR_IMAGE` | absent |

**The level is never raised by the register name.**  An earlier version
promoted any register whose name looked meaningful; that is withdrawn.  The
GPIO, clock, battery, pad and interrupt-priority registers are therefore
`ACCESS_MATCH` even though their addresses match, because no instruction
sequence was verified for them.

## 2. UART — the strongest result

| Reference | Name | Our image |
|---|---|---|
| `0x00FF4900` | `UART_CTRL_REG` | **absent**; `0x000F4900` is used (first-level) — `FUNCTIONAL_REGISTER_MATCH` by manual comparison |
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
| `0x00FF4C00` | `WATCHDOG_REG`, written `0xff` | exact address, 8-bit store; value `0xff` verified at `0x28820` | `FUNCTIONAL_REGISTER_MATCH` |
| `0x00FF5402` | reset interrupt pending | `0x000F5402`, 7 writes | low bits only |
| `0x00FF5404` / `0x00FF5406` | interrupt priority 0/1 | **same address** used in both images | `ACCESS_MATCH` |

### Registers that the fork added

| Reference | Name | Ours |
|---|---|---|
| `0x00FF4002` | `CLK_CODEC_DIV_REG` | `0x000F4002` written once (`0x18BE`) |
| `0x00FF400C` | `CLK_PER_DIV_REG` | `0x000F400C` written once (`0x18C2`) |
| `0x00FF4010` | **`CLK_PLL_CTRL_REG`** | **exact address**, read-modify-write at `0x1896` |
| `0x00FF4012` | `CLK_PLL_DIV_REG` | `0x000F4012` written |
| `0x00FF401A` | `CLK_AUX_REG` | `0x000F401A` RMW at `0x1454` |
| `0x00FF4812` | `BAT_CTRL_REG` | exact address |
| `0x00FF481E` | **`PAD_CTRL_REG`** | **exact address**, two bit writes at `0x1200`/`0x1202` |
| `0x00FF4940`–`0x00FF4948` | SPI block | not used by our images |

The PLL control register being written by the second-level start-up is a new
lead: the firmware does configure a clock source, which matters for any
PCM/TDM timing question.

### Watchdog

The reference does `WATCHDOG_REG = 0xff`.  The **exact address**
`0x00FF4C00` is written **8-bit** in our image (`storb`, `0x15AE`/`0x15B6`),
while `0x000F4C00` is written **16-bit** with `0xFF`.  Our first-level does
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

**E3.2 update: the address-space part is SAME_ARCHITECTURAL_ADDRESS.**
Encoded abs20 `0xF6006` expands to effective `0x00FF6006`.  The physical
SC14448 register identity is still CANDIDATE.  What changed earlier is the
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
