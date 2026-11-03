# SC14448 / Dialog hardware test plan

Status: **research and bench-plan only; no reset, UART upload, firmware or
line test was performed**

This is deliberately separate from `docs/fon-first-hardware-test.md`.  The
first FON module test must not touch the Dialog reset, UART ownership, audio
clocks or line circuit.

---

## 1. Reset GPIO

AVM HW236 board table:

```text
gpio_avm_dect_reset = GPIO40, AVM_DEF_HW_PARAM_GPIO_OUT_ACTIVE_HIGH
gpio_avm_dect_rd    = GPIO16
gpio_avm_dect_tx    = absent on the 7530 board table
```

The static Piglet fallback profile contains GPIO18, but the production HW236
board table is the authoritative value for this board file.  The difference
is a real finding: **do not use GPIO18 from the fallback profile without
checking the actual board revision and GPIO ownership**.

The reset is active-high according to the board table.  The loader sequence
observed in `Piglet_noemif.ko` is:

```text
configure GPIO output
drive low (assert reset)
delay
initialize/configure the DECT UART
drive high (release reset)
delay
```

A future loader must first prove:

- GPIO40 is not owned by another driver;
- the console and DECT UART users are quiesced;
- the analog line interface cannot be damaged by reset;
- recovery does not require flashing or bootloader changes.

Do not reset GPIO40 as part of the TDM probe-only test.

---

## 2. UART ownership

The target OpenWrt 7530 DTS has:

```text
blsp1_uart1: serial@78af000
  compatible: qcom,msm-uartdm-v1.4, qcom,msm-uartdm
  reg: 0x078af000 0x200
  IRQ: GIC SPI 107
  pins: GPIO16/GPIO17
  pin function: blsp_uart0
```

The target uses this UART as the serial console.  The AVM driver selects a
DECT UART through the first MSM UART or an `avm,dectstub_uart` node; the 7530
DTS has no such node.  The stock loader explicitly stops/starts console
ownership around the upload.

The Linux 6.12 side is not a drop-in AVM `msm_dectuart` replacement:

- target console currently owns the port;
- the AVM `msm_dectuart_init/get_char/put_char` API is not mainline;
- a serdev/tty implementation must be separate from `fon_tdm_drv`;
- console arbitration must be tested before any upload.

No command in this plan should stop the console or open the DECT UART for
writing.

---

## 3. Does SC14448 control both DECT and analog FON?

Static evidence says the SC14448 is on the TDM/PCM path and is the likely
source of FSC/DCL clocks and slot-5 behavior.  It is also the DECT baseband.
The exact split between DECT firmware state and analog FON line state is not
proven.

Therefore:

- resetting DECT may also disturb PCM/FON;
- starting DECT firmware may initialize the analog path;
- a DECT-only reset cannot be assumed harmless;
- a FON-only reset cannot be assumed to exist.

Treat reset and firmware upload as a combined risk to both DECT and FON.

---

## 4. Detecting a running SC14448 without reset/upload

Candidates, in increasing invasiveness:

### 4.1 Passive MBOX/TDM clock observation

Use a scope or logic analyzer on the board TDM pins if they are accessible:

```text
FSC/FS  GPIO22 (pinmux2) or GPIO26 (pinmux3)
DCL     GPIO21 or GPIO25
MCL     GPIO20 or GPIO24
DI      GPIO23
DO      GPIO27
```

Expected if SC14448 is running and is the TDM master:

- FSC approximately 8 kHz;
- DCL/BCLK approximately 1.024 MHz for 8 × 16-bit slots;
- MCL approximately 4.096 MHz if present;
- continuous frame activity, not a single edge.

These values are derived from the recovered 8-slot geometry; actual clock
presence and polarity must be measured, not assumed.

### 4.2 UART traffic

A passive UART sniffer may show boot/loader traffic.  Do not connect a
transmitter; do not open the Linux port for write.  The stock kernel has a
DECT UART sniffer interface, but that is AVM-specific and not present here.

### 4.3 Driver/device state

Check:

```sh
cat /proc/interrupts
cat /sys/kernel/debug/clk/clk_summary 2>/dev/null
dmesg -T | grep -iE 'dect|pcm|tdm|adss|mbox|piglet'
```

A running SC14448 may not create any Linux-visible device.  Absence of a
message is not evidence that it is stopped.

### 4.4 Unsupported / unsafe methods

Do not use:

- GPIO40 reset;
- firmware upload;
- MBOX DMA start;
- direct MBOX register writes;
- UART `msm_dectuart` replacement;
- forcing QCA ADSS clocks if ownership is unknown.

---

## 5. What requires a scope or logic analyzer

The following cannot be proven by software-only commands:

1. actual FSC frequency and duty;
2. actual DCL/BCLK frequency and polarity;
3. actual MCL frequency and direction;
4. whether SC14448 or IPQ4019 drives each pin;
5. frame/slot alignment at the SC14448;
6. slot-5 control/status signal integrity;
7. whether reset GPIO40 actually reaches the SC14448 reset pin;
8. whether the analog line is isolated/disabled during reset.

Use a differential probe/appropriate logic analyzer; do not connect the
high-voltage line side to a grounded instrument.

---

## 6. Minimal safe experiment sequence

### Stage D0 — documentation only

- Confirm board revision and HW236 GPIO table.
- Confirm GPIO40 is not used by another DT node/driver.
- Identify the physical SC14448 reset and PCM pins from the board.
- Confirm the recovery method.

### Stage D1 — passive observation

- Measure FSC/DCL/MCL with the system in its current boot state.
- Capture UART traffic passively if the hardware allows it.
- Do not reset or write.

### Stage D2 — console/UART ownership test

- On a bench unit, test only console stop/restore via a separate loader
  prototype.
- No firmware transfer.
- Verify console recovery and no watchdog/reboot.

### Stage D3 — first-level firmware upload

Only after separate approval:

- isolate the analog line;
- assert GPIO40;
- upload only the first-level image;
- capture the response;
- release reset;
- check passive FSC/DCL;
- restore the known-good system.

### Stage D4 — second-level firmware / PCM

Not part of this iteration.  Requires a reviewed loader, analog isolation, and
a plan for line/ring safety.

No stage above authorizes DMA, ringing, line feed or a production image
change.

---

## 7. Open questions

- Exact electrical connection of GPIO40 to SC14448 reset.
- Whether the 7530 board uses GPIO18 in another revision.
- Whether SC14448 or QCA is the active TDM clock master at runtime.
- Whether first-level-only firmware generates FSC/DCL.
- Whether the DECT and FON functions share a firmware state that makes a
  partial upload unsafe.
- Whether a passive test point is accessible without removing the board.
- Whether a runtime DTB/overlay path exists on the target bootloader.

Until these are resolved, the Dialog path remains **NOT READY** for hardware
upload/reset.
