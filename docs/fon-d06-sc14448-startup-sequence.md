# D0.6-D — the SC14448 start-up sequence, as far as it is proven

> **Status: reconstruction from OEM code + OEM boot log.**  The diagram in
> the task is a hypothesis; below it is checked link by link against what the
> binaries actually do.  Timestamps are not treated as causal proof.

## 0. What the code establishes

| Link | Function / file | What it does | GPIO40? | UART? | Status |
|---|---|---|---|---|---|
| POWER | board hardware | 1.8 V rail present (measured) | — | — | **CONFIRMED (measurement)** |
| RESET assert | `dect_loader` `0xb44`,`0xb54` | `ctrl(gpio,0,1)`, `out_bit(gpio,0)` | yes | no | **CONFIRMED** |
| UART ready (reset held) | `msm_dectuart_init` `0xb80` | serial port configured **while reset is still asserted** | no | yes | **CONFIRMED** |
| RESET release | `dect_loader` `0xb9c` | `out_bit(gpio,1)` — **after** UART init | yes | no | **CONFIRMED** |
| First-level load | `dect_loader` → `dect_file_process` | `dectfw_firstlevel_441_slow.hex` over UART | no | yes | **CONFIRMED** (code path), upload itself not observed by us |
| Second-level load | same | `dectfw_secondlevel_441.hex` | no | yes | **CONFIRMED** (code path) |
| Firmware runs | SC14448 | starts emitting FSC/BCLK | — | — | **UNKNOWN** |
| Clock check | `Check_TDMInterface` `0x3f0c` | counts GPIO edges on FSC/DCL, reports Hz | no | no | **CONFIRMED** (code) |
| Pin config | `ipq40xxtdm_linkinit` `0xa168` | `dakota_gpio_pinconfig(gpio, profile, 1)` — applies I2S mux | no | no | **CONFIRMED** |
| PCM link | `pcmlink.ko` | TDM slot 5 control/status | no | no | Stage 5, unchanged |

### 0.1 The order is hard-coded

```
b44        dakota_gpio_ctrl(gpio, 0, 1)   request as output
b54        dakota_gpio_out_bit(gpio, 0)   RESET = 0 (assert)
b58..b64   delay (11 iterations)
b74        log_piglet("dect_reset")
b80        msm_dectuart_init(...)          UART init while reset held
b98..b9c   dakota_gpio_out_bit(gpio, 1)   RESET = 1 (release)
ba0..bac   settle (16 iterations)
```

**Corrected.**  An earlier revision had the release at `b9c` before the UART
at `b80`; the addresses prove the opposite (`0xb80 < 0xb9c`).  The second
`dect_loader` branch agrees: `msm_dectuart_init` at `d10`, release at `d28`.

So the loader holds the chip in reset until the port is ready, then releases
it and starts the firmware transfer.  A loader that released reset first
would wake the chip with no host listening.

### 0.2 The clock check is passive

`Check_TDMInterface` requests FSC and DCL as **GPIO inputs**
(`dakota_gpio_ctrl(gpio, 0, 0)`), maps their registers and counts transitions
for ~1000 loop iterations.  It **does not** configure the ADSS block and does
not enable any clock from the SoC side.

**This is the key point for our driver:** AVM verifies that the SC14448 is
producing clocks *before* bringing up PCMLINK, and it does so by observing the
pins, not by driving them.  If the check fails, the loader path bails out
(`0x430c`: `cmp r0, #0; beq 0x4424`).

## 1. What makes FSC/BCLK appear

From the above:

- our SoC side never enables the ADSS clock to *drive* the pins;
- the pads are read as GPIOs, so they are inputs on our side;
- therefore the clocks must come **from the SC14448**, which must be
  running its firmware.

So the causal chain the evidence supports is:

```
power -> reset released -> UART upload of first+second level
      -> SC14448 starts executing firmware
      -> SC14448 drives FSC/BCLK
      -> AVM's passive check succeeds
      -> pcmlink opens TDM and exchanges slot 5
```

Without the firmware the chip has no reason to drive clocks, and that is the
most likely reason nothing is seen under OpenWrt — **but this is INFERRED**,
not measured.  A gated clock or an un-released reset would look identical
from the outside.

## 2. What the boot log adds, and what it does not

| Time | Event |
|---|---|
| 0.39 s | `msm_dectuart_probe` (driver binds the port) |
| 11.9 s | `piglet.service` starts |
| 12.03 s | `dect_loader-bootmode` |
| 17.77 s | second-level `dectfw` loaded |
| 19.98 s | `TDM: FS: 8000 Hz CLK: 1025720 Hz` |
| 20.12 s | `pcmlink.ko` loaded |

This is consistent with §0.1 and §0.2: UART binds early, reset+upload happen
around 12–18 s, the clock check succeeds at ~20 s, and only then is PCMLINK
brought up.

It is **not** proof that the upload is what starts the clocks; the clock check
is the only evidence that they exist, and it is downstream of the upload by
construction.

## 3. Under OpenWrt

| Step | FRITZ!OS | OpenWrt (current) |
|---|---|---|
| 1.8 V rail | present | present (measured) |
| reset released | by `dect_loader` | **never** — GPIO40 is an unclaimed input at 0 |
| UART configured for loader | yes | `ttyMSM0` exists as console |
| firmware uploaded | yes | **no** |
| clocks produced | yes | **not observed** |
| PCMLINK | yes | no |

So the earliest broken link under OpenWrt is **reset is never released**;
the firmware step is the next one.  Both are before any PCM question.

## 4. Remaining unknowns

| Question | Status |
|---|---|
| Does the SC14448 need the second-level firmware to start clocks, or only the first? | **UNKNOWN** |
| Is there a boot-mode strap that selects the loader? | **UNKNOWN** |
| Does the loader UART need a specific baud/format distinct from the console? | **UNKNOWN** (Stage 5 says 115200 8N1 on the same port) |
| Is GPIO40 the only reset, or is there a second (e.g. via the inverter)? | **UNKNOWN** |
| Exact reset pulse duration | **UNKNOWN** (loop unit not resolved) |
