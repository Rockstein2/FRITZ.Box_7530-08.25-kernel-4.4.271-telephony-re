# Dialog SC14448 boot / firmware path

> **Status: historical analysis.**
> This document records the reasoning and evidence as of the date it was
> written.  Some of its `UNKNOWN` / `UNVERIFIED` markers have since been
> answered.
> - Current confirmed facts: `../fon-known-facts.md`
> - Current open questions: `../fon-open-questions.md`
> - This file is kept for the reasoning trail, not as a status report.

Status: **protocol and parser recovered; no firmware upload was attempted**

This document is the boot-side companion to
`fon-dialog-dependency.md` and `fon-tdm-hardware.md`.

The implemented part is the clean-room parser and a mockable handshake
transport in `src/fon-firmware/`.  It was tested against the local AVM images
but does not open a UART, reset the SC14448, or upload anything.

---

## 1. Hardware path on the FRITZ!Box 7530

### 1.1 UART controller

The target OpenWrt DTS and the AVM 08.25 DTS agree on the physical UART:

```text
address:      0x078af000
IRQ:          GIC SPI 107
compatible:   qcom,msm-uartdm-v1.4 / qcom,msm-uartdm
target label: blsp1_uart1: serial@78af000
AVM label:    blsp_uart0: serial@78af000
pins:         GPIO16 (RX), GPIO17 (TX)
pin function: blsp_uart0
```

The AVM board DTS disables `serial@78b0000`; it is not the DECT UART.  The
target 7530 DTS enables `&blsp1_uart1` and gives it `serial_0_pins`
(GPIO16/17).  The target label is `blsp1_uart1` even though the pin function
name is `blsp_uart0`; the address is the unambiguous identifier.

The AVM `msm_serial.c` fallback selects the first probed MSM UART when no
`avm,dectstub_uart` node exists.  The 7530 DTS has no such node, so the
observed `ttyMSM` number must be confirmed at runtime rather than hard-coded.
The DECT UART is **shared with the serial console**; the original loader calls
`msm_console_stop()` / `msm_console_start()` around the upload.

### 1.2 Reset and auxiliary GPIOs

The production board hardware-config table differs from Piglet's static
fallback profile:

```text
gpio_avm_dect_reset = 40, output active high
gpio_avm_dect_rd    = 16, no parameter
gpio_avm_dect_tx    = absent in the 7530 board table (fallback -1)
```

Older notes quote the fallback profile value 18; the HW236 board table is the
authoritative 7530 value (**GPIO40**).  Do not use GPIO18 from the fallback
without checking the actual board revision.

`dect_requestinit()` may drive `gpio_avm_dect_tx` only when it is present; on
the 7530 board it is not, so the UART hardware path is used.

Do not toggle GPIO40 from this diagnostic driver.  A future loader must first
prove that the GPIO is free, that the console is stopped, and that resetting
the SC14448 is safe for the connected line circuit.

### 1.3 Baud rates found in `Piglet_noemif.ko`

The loader contains these exact divisor constants:

```text
0x2580   9600
0x4b00   19200
0x1c200  115200
0x38400  230400
0x70800  460800
```

The normal/slow path selects from the mode and chip type; the fast path uses
the higher rates.  The stock init script uses `piglet_dectmode=0x105` and the
`_slow` first-level image.  The exact selected rate must be confirmed from the
runtime `[piglet] ... baudrate`/`UART init` log; no scope or UART capture was
performed here, so this document does not invent a single fixed rate.

---

## 2. Reset and boot sequence

From `Piglet_noemif.ko` state 0 and `../../notes/piglet.md`:

```text
assert DECT reset (configure GPIO output, drive low)
delay / settle
msm_dectuart_init(baud, mode)       // shared UART is configured
release DECT reset (drive high)
delay
optional: drive gpio_avm_dect_tx
```

The loader then waits for the chip's boot response.

The first-level image is small (618 data bytes at address `0x00010080` on the
7530 image); the second-level image is about 54 KB.  `dect_file_process()`
calls the converter twice:

```text
first-level  -> ihex2bin(..., mode 0) -> u16be payload length
second-level -> ihex2bin(..., mode 1) -> u32be payload length
```

### 2.1 Slow/normal protocol

```text
host                                 SC14448
  |  reset low / UART init / reset high   |
  | <------------- STX (0x02) ------------|
  | ---- SOH (0x01) + length header ----->|
  | <------------- ACK (0x06) ------------|
  | ------------ payload bytes ---------->|
  | <--------- checksum / answer ---------|
  | ---- ACK (0x06) or NACK (0x15) ------>|
```

The length header is 2 bytes for first-level and 4 bytes for second-level,
big-endian.  A NACK is `0x15`.  The loader compares the final checksum byte
with the chip response and ends with an ACK on success.

### 2.2 Fast/HELLO protocol

The fast path writes the 11-byte probe:

```text
HELLO DCX81
```

It reads 11 bytes back, compares them, and expects the four-byte reply:

```text
0x11 0xba 0x5e 0xba
```

It then sends the length field `sl[0], sl[1], 0x00, 0x00` and the payload.
The exact mode bits selecting fast versus slow remain loader/firmware
dependent; the stock 7530 profile uses the slow image.

### 2.3 What `0xfefe` and `0x5555` are not

`0xfefe` and `0x5555` are fixed 16-bit words in the TDM TX frame
(`TxDMA`), not UART boot bytes.  They are not the STX/SOH/ACK handshake and
not a firmware upload sync sequence.  Their SC14448 semantic meaning remains
unknown; see `fon-tdm-hardware.md`.

---

## 3. Firmware image format

The parser in `src/fon-firmware/fon_dialog_fw.c` implements the recovered
format:

```text
Intel HEX input:
  :llaaaatt[data]cc
  types 0x00, 0x01, 0x02, 0x04

Converted image:
  level 0: u16be payload_length
  level 1: u32be payload_length
  repeated block:
    u32be address
    u32be data_length
    data bytes
  u8 xor_checksum over the block payload
```

The parser validates:

- the Intel HEX checksum;
- record types and data lengths;
- duplicate/overlapping addresses;
- contiguous block grouping;
- the 0x30005-byte image limit;
- the outer length and XOR byte.

Verified against local images (not in Git):

| Image | Result |
|---|---|
| `dectfw_firstlevel_441_slow.hex` | 629-byte image, 1 block |
| `dectfw_secondlevel_441.hex` | 54124-byte image, 9 blocks |
| `dectfw_secondlevel_441p2test.hex` | 49805-byte image, 8 blocks |

`src/fon-firmware/tests/fon_dialog_test.c` runs synthetic cases and optionally
parses these local files when present.

---

## 4. How successful boot is detected

After `dect_file_process()` the loader calls `Check_TDMInterface()` unless
`piglet_hostclkmaster` is set.  It:

1. looks up `gpio_avm_pcmlink_fsc` and `gpio_avm_pcmlink_dcl` in the board
   hardware-config table;
2. samples both pins for about 100 ms;
3. prints `[piglet]TDM: FS: %u Hz CLK: %u Hz`;
4. returns an error if FSC/DCL are missing.

On failure it prints:

```text
[piglet]bye bye - can't detect TDM-FS or TDM-CLK!
```

and does not send the successful `piglet_ready` event.

`pcmlink.ko` registers `piglet_ready_sink`; its control thread waits for the
readiness flag before normal TDM/control work.  This is the observable chain:

```text
firmware upload + FSC/DCL present
  -> piglet_ready event
  -> pcmlink readiness gate
  -> TDM/control work
```

The standalone FON transport does not need the AVM event API, but the SC14448
still needs a running firmware image to generate clocks and interpret slot 5.

---

## 5. Can the original firmware be loaded without the DECT userspace stack?

**Probably yes for the loader itself, but this is not the same as a working
FON line.**

The uploader uses:

- a normal MSM UART / tty or serdev path;
- GPIO reset;
- firmware blobs loaded by `request_firmware()`.

It does not require CAPI, SIP, `avm_dect.ko`, or the DECT application stack
to perform the byte upload.  However, the firmware image itself contains the
SC14448 application and PCM/TDM behavior.  A minimal loader could therefore
load the original firmware without porting `Piglet_noemif.ko` or the whole
AVM stack.

Unproven parts:

- whether the SC14448 first-level bootloader alone generates clocks;
- whether `piglet_hostclkmaster` is set on production units;
- whether some AVM DECT initialization is needed before the firmware accepts
  line commands;
- whether the firmware can be distributed legally outside the AVM rootfs.

The safe assumption is: **firmware is an external dependency of the FON
driver, not something the diagnostic TDM module may silently upload.**

---

## 6. Linux 6.12 loader requirements

A future loader should be a separate component, not part of `fon_tdm_drv`:

- open the target serial port via the standard tty/serdev API;
- stop console ownership or use a dedicated UART configuration;
- request firmware with `request_firmware()` from a user-supplied path;
- use the parser to produce the level-0/level-1 image;
- assert the reset GPIO only after an explicit safety check;
- perform slow or fast handshake with bounded timeouts;
- never upload automatically at module load;
- never touch line/ring voltage;
- expose a dry-run/parse-only mode.

The parser and protocol helpers are already implemented and tested; the UART
and GPIO side is intentionally not implemented in this iteration.

---

## 7. First safe firmware test

Do not start with an upload.  The first bench sequence should be:

1. Run the parser offline on the local images.
2. Read-only inspect the target UART and GPIO ownership; do not assert reset.
3. Confirm the console can be stopped and restored.
4. Capture the existing UART traffic only if the hardware setup permits it.
5. Only after a separate reset/line-isolation review may a loader assert
   GPIO40 and upload first-level firmware.
6. Do not proceed to second-level/audio/line tests until the first-level
   response and TDM clock behavior are understood.

The diagnostic TDM driver deliberately has no firmware upload and no GPIO
reset.  It remains safe to load without a working SC14448.
