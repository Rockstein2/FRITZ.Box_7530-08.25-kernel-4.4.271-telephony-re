# Minimal Dialog SC14448 firmware loader

> **Status: design plus offline-tested dry-run tool.**
> Nothing here uploads firmware, resets the chip or opens a real UART.
> Stage D must be authorised separately.

Question answered: what is the smallest, most reversible way to get the
Dialog SC14448 into its boot firmware, and does it depend on AVM userspace?

---

## 1. What the chip needs

From the FRITZ!OS boot order (`fon-known-facts.md` section 6) and the GPL
sources:

```text
power / reset release
        |
        v
first-level firmware   (dectfw_firstlevel_441_slow.hex,  629-byte image)
        |
        v
second-level firmware  (dectfw_secondlevel_441.hex,    54124-byte image)
        |
        v
DECT core running -> FSC/BCLK on the PCM bus
        |
        v
TDM channel usable by the FON
```

Two upload paths exist in the AVM payloads: a **slow** path with an explicit
`SOH` + length + `ACK` handshake, and a **fast** path opened by an 11-byte
`HELLO DCX81` probe.  The local parser already implements both.

## 2. Split of responsibilities

| Layer | Needed for one analog FON? | Evidence |
|---|---|---|
| Boot firmware (level 1 + level 2) | **yes** | clocks do not exist until the chip runs |
| Firmware application (DECT stack) | **unknown** | not proven that the analog port works without DECT registration active |
| TDM clock generation | **yes**, produced by the chip | `fon-known-facts.md` section 4 |
| FON control protocol (slot 5) | **yes** for hook/ring | `fon-known-facts.md` section 7 |
| DECT-specific init (`avm_dect`, `dect_io`, CAPI) | **not proven necessary** | only needed for DECT handsets |

The honest answer to "can we use the SC14448 without AVM DECT userspace?" is
**probably yes for the analog port, unproven**.  Loading boot firmware is
necessary but not sufficient: the slot-5 protocol still has to be spoken by
our driver, and nobody has shown that the analog port answers without the
DECT application layer running.

This is the single largest unknown of the whole project and must be tested
before investing in a full driver.

---

## 3. UART constraints

The SC14448 boot UART is the **same** `serial@78af000` that carries the Linux
console (`ttyMSM0`).  Facts from the kernel tree and the Stage A capture:

| Fact | Value |
|---|---|
| Console device | `ttyMSM0`, char `248:0` |
| `/proc/consoles` | `-W- (EC  p  )` — `CON_ENABLED`, `CON_CONSDEV`, `CON_PRINTBUFFER` |
| `console=` on cmdline | **absent** |
| `stdout-path` in DTS | **absent** |
| `CONFIG_SERIAL_MSM_CONSOLE` | `y` |
| `CONFIG_SERIAL_DEV_BUS` (serdev) | **not set** |
| DMA on the console port | disabled by the driver (`!uart_console(port)` check) |

### 3.1 Can the port be shared?

Yes.  `uart_console(uport)` is true, so tty and console share one `uart_port`;
all traffic is PIO.  Opening `/dev/ttyMSM0` inherits the console termios and
a userspace program can read and write bytes.

### 3.2 What breaks the console

Only **reprogramming the hardware**:

- changing speed (`msm_set_termios` -> `dev_pm_opp_set_rate`,
  `MSM_UART_CSR`, then `msm_reset`) — the console terminal desyncs and the
  port is reset;
- changing word size / parity / stop bits;
- `HUPCL` on close (drops DTR/RTS).

Setting raw termios **without** changing speed is safe.

### 3.3 The unavoidable problem: interleaving

Kernel `printk` keeps writing to the same port.  Any `dev_err`, probe message
or unrelated subsystem warning lands in the middle of the firmware byte
stream and corrupts it.  There is no `console_stop()`/`console_start()` in
mainline 6.12 (that was an AVM 4.4 patch).

Options, in order of preference:

| Option | Effect on console | Risk |
|---|---|---|
| **A. Separate UART** (hardware) | none | needs a second UART wired to the SC14448 |
| **B. `quiet` + loglevel 0 + no driver binds during upload** | console silent but recoverable | a single late message corrupts the upload |
| **C. Userspace uploader with retry and per-block ACK** | survives corruption | slow; chip may reject a partial block |
| **D. Kernel-side console unregister** | console lost until reboot | no mainline API; needs a patch |
| **E. `earlycon` on another port** | keeps console elsewhere | no second port wired |

For a first attempt, **B + C** is the realistic combination: boot with
`quiet loglevel=0`, upload from userspace, rely on the chip's per-block ACK
and retry the whole block on mismatch.  If it proves unreliable, option A is
the clean answer.

---

## 4. Architecture of the loader

```text
firmware hex files (not in Git)
        |
        v
fon_dialog_fw.c  (existing parser: HEX -> image, checksums)
        |
        v
fon_loader_plan  (new: plan the transfer, no I/O)
        |
        v
transport (abstract: mock today, tty later)
        |
        v
SC14448
```

`src/fon-loader/` contains:

| File | Purpose |
|---|---|
| `fon_loader.h` | plan structures and transport interface |
| `fon_loader.c` | build a transfer plan, validate it, run it against a transport |
| `main.c` | command line: `plan`, `dry-run`, `mock` |
| `tests/` | offline tests |

### 4.1 What the tool does today

- parses the HEX files with the existing parser;
- verifies block order, sizes and XOR checksums;
- prints the exact byte sequence it *would* send (SOH/length/ACK handshake,
  then blocks);
- runs the whole sequence against a **mock transport** that answers like the
  documented protocol;
- reports timeouts and mismatches without retrying forever;
- never touches a device.

### 4.2 What it deliberately does not do

- open a real serial port;
- toggle GPIO40;
- wait on the PCM clocks;
- retry a blind upload;
- claim success without an ACK per block.

---

## 5. GPIO40 and reset

`gpio_avm_dect_reset` is GPIO40, `OUT_ACTIVE_HIGH` per the AVM board table.
Electrical polarity at the SC14448 pin is **unverified**.

The loader therefore assumes the chip is **already out of reset** and that
the boot firmware can be spoken to as-is.  If that is false, the fix belongs
to a dedicated reset stage, not hidden inside the loader.

Per the task constraints, GPIO40 is not toggled in this iteration.

---

## 6. Blockers before a real upload

| # | Blocker | Why it blocks |
|---|---|---|
| 1 | No proof the SC14448 is out of reset | silent chip looks identical to "no firmware" |
| 2 | Console interleaving | a stray `printk` corrupts the stream |
| 3 | Unknown reply timing | timeouts picked without measurement may be wrong by 10x |
| 4 | First-level versus fast path | not proven which one this unit uses |
| 5 | No measured FSC/BCLK baseline | cannot tell success from "uploaded but idle" |
| 6 | Analog port without DECT stack | unknown, see section 2 |

Blockers 1 and 5 are answered by the passive measurement in
`fon-tdm-passive-test.md`.  Blocker 2 needs the decision in 3.3.

---

## 7. Dry-run output contract

`fon-loader dry-run` prints, for each level:

```text
level 0: 629-byte image, 1 block, xor 0x.. OK
level 1: 54124-byte image, 9 blocks, xor 0x.. OK
sequence: HELLO/SOH -> ACK -> block 1 -> ACK -> ... -> block 9 -> ACK
bytes to send: N, expected replies: M
```

and exits non-zero if any checksum, order or size is wrong.  No port is
opened.
