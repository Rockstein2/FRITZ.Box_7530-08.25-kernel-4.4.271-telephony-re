# Software TDM clock check (recovered from the OEM modules)

> **Status: reverse-engineering result plus a feasibility analysis.**
> The algorithms come from `reports/piglet.annotated.txt` and
> `reports/pcmlink.annotated.txt`.  Nothing here was executed on hardware.
>
> **Correction (C0+):** an earlier revision of this document attributed the
> OEM boot line to `pcmlink.ko` and estimated its window as 0.38 s.  Both were
> wrong.  The boot line is from `Piglet_noemif.ko:Check_TDMInterface()`; the
> `pcmlink.ko` function is a separate diagnostic command with a different
> window.  The old estimate also ignored a 64-bit fixed-point constant.
>
> **Correction (C0+-R1):** the first C0+ revision then said the Piglet window
> was 100 µs.  That was wrong by a factor of 1000.  The recovered window is
> **100 ms**; the magic/`>>6` sequence produces `cyclefreq/1000`, and the
> `*100` produces 0.1 s.  The numerical proof is
> `tools/tests/test_oem_tdm_timing.py`.

Both OEM modules read the raw TLMM input bit and count transitions.  Neither
needs an oscilloscope.  The two functions are not interchangeable:

| Function | Module | When it runs | Window | Report |
|---|---|---|---:|---|
| `Check_TDMInterface` | `Piglet_noemif.ko` | before the boot-time TDM report | **100 ms** | `[piglet]TDM: FS: … CLK: …` |
| `ipq40xxtdm_checkhw` | `pcmlink.ko` | `cmd_general` diagnostic command (`0xa880`), not boot init | **≈195 ms** | `[pcmlink]TDM: FS: … CLK: …` |

The 2026-11-08 OEM capture contains only the Piglet line:

```text
[piglet]TDM: FS: 8000 Hz CLK: 1024355 Hz
```

No `[pcmlink]TDM` line appears in that boot log.

---

## 1. Register map

Linux 6.12 `drivers/pinctrl/qcom/pinctrl-ipq4019.c` defines:

```text
io_reg  = 0x4 + 0x1000 * id
ctl_reg = 0x0 + 0x1000 * id
mux_bit = 2
oe_bit  = 9
in_bit  = 0
```

The TLMM base on IPQ4019 is `0x01000000`.  Therefore:

```text
GPIO_CFG(n) = 0x01000000 + n * 0x1000
GPIO_IO(n)  = 0x01000000 + n * 0x1000 + 4
input level = GPIO_IO(n) bit 0
FUNC_SEL    = GPIO_CFG(n) bits 5:2
```

Both functions read the input bit at `membase + 4`.  The candidate pins are
GPIO21/22 (PINMUX2 DCL/FSC) and GPIO25/26 (PINMUX3 DCL/FSC); MCL is
GPIO20/24, DI is GPIO23 and DO is GPIO27.

---

## 2. Piglet: the boot-time check

Function: `Check_TDMInterface`, `0x3f0c..0x414c`.

### 2.1 Window

```text
0x3f10  ipq40xx_get_cyclefreq()          -> cyclefreq in cycles/second
0x3f14  magic = 0x10624dd3                 (274,877,907)
0x3f1c  umull                            -> r2:r3 = cyclefreq * magic
0x3f3c  lsr r6, r3, #6                   -> r6 ≈ cyclefreq / 1,000
0x4064  r3 = 100
0x406c  mul r6, r3, r6                   -> r6 = cyclefreq / 10 cycles
```

Numerically, `high32(cyclefreq * 274877907)` is about
`cyclefreq * 0.064`; shifting that right by 6 gives about
`cyclefreq * 0.001`, i.e. cycles per millisecond.  Multiplying by 100 gives
`cyclefreq / 10` cycles, which is **0.1 s = 100 ms**.  For a 25 MHz counter
this is 2,500,000 cycles.

This is a 100 ms hardware-time window, not a fixed number of iterations.
The FSC loop samples in chunks of 1001 reads and restarts a chunk when the
window has not yet elapsed; the DCL loop checks `ipq40xx_get_cycles()` after
each read.  The edge count covers the whole 100 ms.

**FSC and DCL are measured in sequential windows, not simultaneously.**  The
FSC loop runs to completion first (`0x4078..0x409c`), then the DCL loop starts
a new `ipq40xx_get_cycles()` window at `0x40a0..0x40d0`.  The two reported
frequencies therefore come from different 100 ms intervals; a fast change of
the source between the windows would not be visible in the comparison.

### 2.2 Sampling and reporting

```text
0x4014  dakota_gpio_ctrl(dcl, 0, 0)       ; API side effects UNKNOWN
0x4024  dakota_gpio_ctrl(fsc, 0, 0)
0x4078  ldr r4, [fsc_membase, #4]       ; raw input bit
0x4080  cmp previous, level
0x4084  addne r5, r5, #1                ; every transition counts
0x40b0  ldr r7, [dcl_membase, #4]
0x40d4  piglet_unlock()
0x40dc  r2 = 10 * fsc_edges
0x40e0  r1 = 10 * dcl_edges
0x40ec  r2 >>= 1                         ; 5 * edges
0x40f0  r1 >>= 1                         ; 5 * edges
0x40f4  printk("[piglet]TDM: FS: %u Hz CLK: %u Hz")
0x40f8  if dcl_edges <= 99 -> return bit 0
0x4104  if fsc_edges <= 99 -> return bit 1
```

For a 100 ms window and two transitions per period:

```text
frequency = edges / (2 * 100 ms) = 5 * edges
```

That is why the OEM line reports `8000` and `1024355`; the 8 kHz value is
consistent with 1600 transitions in 100 ms.  The threshold of 100 edges is
500 Hz as printed.

`Check_TDMInterface()` is skipped when `piglet_hostclkmaster` is set.  The
OEM 08.25 parameter is `piglet_hostclkmaster=0`, so the check runs.

### 2.3 What is still unknown

The function calls `dakota_gpio_ctrl(pin, 0, 0)` before sampling.  The body of
that API is unavailable, so it is **not** proven to be side-effect free.  The
new C0+ userspace probe deliberately avoids this API and reads TLMM directly.

---

## 3. pcmlink: the diagnostic command

Function: `ipq40xxtdm_checkhw`, `0xa3b4..0xa7f0`, reached from `cmd_general`
at `0xa880`; it is not part of the boot path.

### 3.1 Pin lookup

```text
0xa3d8..0xa408  scan avm_current_hw_config for "gpio_avm_pcmlink_fsc"
0xa438..0xa464  scan for "gpio_avm_pcmlink_dcl"
0xa490..0xa49c  reject function field 0xa or 0xb
0xa4a0..0xa4b8  dakota_gpio_get_membase(fsc/dcl)
0xa4ec..0xa4fc  dakota_gpio_ctrl(pin, 0, 0)
```

The error strings are `error:no gpio_avm_pcmlink_fsc exist`,
`error:no gpio_avm_pcmlink_dcl exist` and `error:no membase exist`.

### 3.2 Window: the old 0.38 s estimate was wrong

The code at `0xa500..0xa538` is not a simple `cyclefreq * 100000 / 2^18`
operation.  It also multiplies by the 64-bit fixed-point constant stored at
`0xa7b8`:

```text
C = 0x82de1b43db34b6d7       (C / 2^64 = 0.5112015763...)
```

The instruction sequence computes the upper product of
`(cyclefreq * 100000)` and `C`, then shifts the result right by 18.  Equating
the fixed-point scale to `2^64`, the window is:

```text
window_cycles ≈ cyclefreq * 100000 * (C / 2^64) / 2^18
              ≈ cyclefreq * 0.1950079
```

So the window is approximately **195 ms**, not 381 ms.  The previous document
computed only `100000 / 2^18 = 0.38147` and missed the `C` factor.

### 3.3 Report

The same `5 * edges` expression is used at `0xa6ec..0xa700`:

```text
r2 = 10 * fsc_edges ; >> 1
r1 = 10 * dcl_edges ; >> 1
printk("[pcmlink]TDM: FS: %u Hz CLK: %u Hz")
```

That formula is correct only for a 100 ms window.  If this diagnostic command
is run with its ~195 ms window, the printed number is about 1.95× the actual
frequency under the same cycles/second assumption.  It is therefore not a
substitute for the Piglet boot value and not the source of the `[piglet]TDM`
line.

The failure bits are the same shape as Piglet's: DCL edges ≤99 sets bit 0,
FSC edges ≤99 sets bit 1.

---

## 4. What a read-only probe can and cannot do

A userspace program can map the TLMM window with `PROT_READ` and poll
`GPIO_IO(n)` bit 0.  This is the same input path the OEM code reads.  It
does not need `gpio_request()`, `gpiod_get_optional()`, a pinmux state or a
clock.

The implementation is in `tools/fon-tlmm-clock-probe/`.  It uses:

```text
open("/dev/mem", O_RDONLY)
mmap(..., PROT_READ, MAP_SHARED, ...)
read GPIO_IO(n) bit 0
measure elapsed time with CLOCK_MONOTONIC
frequency = edges / (2 * elapsed)
```

It never writes MMIO.  `make test` also runs a source guard against
`PROT_WRITE`, GPIO requests, pinctrl, clock and reset operations.

### 4.1 Stock OpenWrt blocker

The stock OpenWrt 25.12.6 kernel in this workspace has:

```text
# CONFIG_DEVMEM is not set
CONFIG_IO_STRICT_DEVMEM=y
```

`/dev/mem` is therefore unavailable.  The userspace probe can be built and
dry-run offline, but it cannot run on the stock image.  A reviewed test kernel
with `CONFIG_DEVMEM=y` is required, or the optional kernel-side skeleton in
`tools/fon-tlmm-clock-probe/kernel/` must be used.  Neither is authorized by
this document.

### 4.2 Sampling limits

- FSC 8 kHz is easy to detect with a userspace loop.
- BCLK ~1.024 MHz requires a sample rate comfortably above 4× the signal
  (≈4.1 MS/s) for a credible frequency estimate.  A userspace loop may not
  reach that rate.
- `DETECTED` means transitions were seen but the rate was too low for a
  frequency estimate.
- `STATIC_OBSERVED` is only reported when the rate is at least 4× the expected
  frequency and the window is long enough.
- `STATIC_OBSERVED` does not prove the SC14448 is silent.  It proves only that
  the IPQ4019 input path did not register edges at this sample rate.

### 4.3 What the probe cannot prove

- the physical route from the SC14448 to the IPQ4019 pads;
- the signal amplitude or 1.8 V domain;
- signal quality, duty cycle or jitter;
- that a detected transition is a valid TDM clock rather than noise;
- the reset state of the SC14448, the firmware state or the analog path.

Those remain electrical or separate hardware-stage questions.

---

## 5. Relation to the OpenWrt driver

The probe is an observation tool.  It does not configure ADSS, pinmux,
clocks, DMA or the SC14448.  A positive FSC/BCLK result would justify a later
review of the slave TDM path; it would not authorize DMA, reset, firmware
upload or line/ring.

Q4/Q5/Q27/Q31 are **partially testable** with this probe under a
`CONFIG_DEVMEM`-enabled test kernel, but they are not closed by offline code
alone.

---

## 6. Confidence

| Claim | Confidence | Basis |
|---|---|---|
| Piglet uses a 100 ms window | high | `0x10624dd3`, `lsr #6`, `mul #100` |
| Piglet reports `5 * edges` | high | `0x40dc..0x40f0` |
| OEM boot line is from Piglet | high | message prefix and call site |
| `pcmlink` window is ≈195 ms | high | 64-bit constant at `0xa7b8` and the `>>18` sequence |
| `pcmlink` `5 * edges` is only correct for 100 ms | high | arithmetic; it is a diagnostic command |
| TLMM `base+4`, bit 0 | high | `io_reg`/`in_bit` in Linux 6.12 |
| direct read is side-effect free | medium | no API request, but the pad's electrical role is unverified |
| stock OpenWrt has `/dev/mem` | **DISPROVED** | `# CONFIG_DEVMEM is not set` |
| probe result proves the physical wire | **no** | input-path observation only |
