# Stage C0+ — read-only software TDM clock probe

> **Status: prepared, never executed.**
> This runbook is not authorization.  The probe has not been copied to the
> router or run there.  Running it is a hardware action and needs explicit
> operator approval for this stage.

Purpose: determine whether the IPQ4019 **input path** sees transitions on the
FSC/BCLK candidates without an oscilloscope, using the same TLMM input bit
that the OEM `Piglet_noemif.ko` check reads.

The instrument is `tools/fon-tlmm-clock-probe/`.  It maps the TLMM window
with `mmap(..., PROT_READ, ...)` and polls `GPIO_IO(n)` bit 0.  It never
writes MMIO and never requests a GPIO line, changes pinmux, enables a clock,
toggles reset or loads a kernel module.

---

## 1. What this stage can and cannot answer

| Question | This stage |
|---|---|
| Does the IPQ4019 input path see 8 kHz edges on GPIO22/26? | **can detect** |
| Does it see ~1.024 MHz edges on GPIO21/25? | **can detect**, but a frequency estimate needs a sample rate comfortably above 4.1 MS/s |
| Which group is live, PINMUX2 or PINMUX3? | **can narrow** by comparing the four pins |
| Is the SC14448 physically connected to those pads? | **cannot prove** |
| Is the amplitude/1.8 V level correct? | **cannot prove** |
| Is the SC14448 out of reset and running its firmware? | **cannot prove** |
| Is a detected transition a valid TDM clock rather than noise? | **cannot prove**; frequency/edge pattern only suggests it |

A `STATIC_OBSERVED` result must not be reported as "the SC14448 is silent".
A low-rate `DETECTED` result must not be reported as a frequency.

---

## 2. Hard prerequisite: `/dev/mem`

The userspace tool needs `/dev/mem`.  The stock OpenWrt 25.12.6 build in this
workspace has:

```text
# CONFIG_DEVMEM is not set
CONFIG_IO_STRICT_DEVMEM=y
```

Therefore the stock image is **NO-GO** for the userspace probe.  Do not work
around it by loading an unreviewed module or by enabling arbitrary devmem
access.

Two valid paths:

1. a reviewed test kernel with `CONFIG_DEVMEM=y` and a checked
   `CONFIG_STRICT_DEVMEM`/`CONFIG_IO_STRICT_DEVMEM` policy; or
2. the optional kernel skeleton in `tools/fon-tlmm-clock-probe/kernel/`,
   built offline and loaded only after a separate approval.

This runbook covers path 1.  Path 2 has the same measurement limits and needs
its own review.

---

## 3. Preflight (read-only)

Run these on the test image; record the output.

```sh
uname -a
cat /etc/openwrt_release
cat /proc/cmdline

# Is /dev/mem present?
ls -l /dev/mem

# If the kernel exposes its config:
zcat /proc/config.gz 2>/dev/null | grep -E 'DEVMEM|STRICT_DEVMEM'
# otherwise check the build config used for the image

# The TLMM window should be visible in the physical memory map:
grep -i -E '1000000|pinctrl' /proc/iomem

# Exact binary identity:
sha256sum /tmp/fon-tlmm-clock-probe
```

Stop if `/dev/mem` is missing.  The exact `sha256sum` must be recorded in the
evidence file and compared with the build record for the copied binary.

### 3.1 GO / NO-GO

| Condition | Decision |
|---|---|
| Stock OpenWrt 25.12.6, no `/dev/mem` | **NO-GO** |
| Test kernel with `/dev/mem`, no strict-devmemblock on TLMM | continue only after review |
| `/dev/mem` present but `mmap` fails | **NO-GO**; do not change kernel policy ad hoc |
| Another agent is changing GPIO/pinctrl/clock/reset concurrently | **NO-GO** |
| FON driver is loaded and doing DMA/reset/firmware work | **NO-GO** for this observation |
| Analog line connected | disconnect it before the run |
| Operator has not approved this stage | **NO-GO** |

The probe is read-only, but it is still a hardware action.  Do not run it
during an active reset, firmware upload, DMA start or line test.

---

## 4. Copy and dry-run

Use a temporary path; do not install the tool into `/usr/bin` or any
persistent location on the router.

```sh
# Host: cross-build (example prefix; use the SDK prefix installed here)
cd tools/fon-tlmm-clock-probe
make clean
make CC=arm-openwrt-linux-muslgnueabi-gcc
sha256sum fon-tlmm-clock-probe

# Copy through the approved test-image channel, then on the router:
sha256sum /tmp/fon-tlmm-clock-probe

# No /dev/mem access in this mode:
/tmp/fon-tlmm-clock-probe --measure-all --dry-run
/tmp/fon-tlmm-clock-probe --inspect --dry-run
```

The dry-run output must show:

```text
gpio=21 signal=DCL  cfg_address=0x01015000 io_address=0x01015004
gpio=22 signal=FSC  cfg_address=0x01016000 io_address=0x01016004
gpio=25 signal=DCL_2 cfg_address=0x01019000 io_address=0x01019004
gpio=26 signal=FSC_2 cfg_address=0x0101a000 io_address=0x0101a004
```

If the addresses differ, stop.

---

## 5. Execution

Run one mode at a time.  Use a short observation first; the default is 200 ms
per pin, and the hard cap is 2000 ms.

```sh
# CFG/IO snapshot first; this does not measure edges.
/tmp/fon-tlmm-clock-probe --inspect | tee /tmp/c0plus-inspect.txt

# FSC candidates.
/tmp/fon-tlmm-clock-probe --measure-fsc --duration-ms 200 \
    | tee /tmp/c0plus-fsc.txt

# BCLK candidates.
/tmp/fon-tlmm-clock-probe --measure-bclk --duration-ms 200 \
    | tee /tmp/c0plus-bclk.txt
```

If the first pass is clean and the operator wants a longer confirmation, use
at most 1000 ms per pin.  Do not loop the tool indefinitely.

Copy `/tmp/c0plus-*.txt` off the router before power-off.

### 5.1 Stop conditions

Stop and power off without further commands if:

- `cfg_changed=1` on any line;
- the tool reports `ERROR`;
- the router hangs, panics, reports `Oops`/`BUG`/lockdep, or loses the console;
- `/proc/iomem` changes unexpectedly;
- another process starts touching the FON/ADSS/GPIO40/SC14448;
- the sample rate collapses or the elapsed time is implausible.

Do not "fix" a stop condition by writing a register, toggling GPIO40,
uploading firmware or changing pinmux.

---

## 6. Interpretation

Each line has this form:

```text
gpio=22 signal=FSC address=0x01016004 cfg=0x... io=... func=... oe=...
input=... samples=... edges=... elapsed_s=... sample_rate_hz=...
freq_hz=... status=... cfg_changed=...
```

| Status | Report as |
|---|---|
| `FREQUENCY_ESTIMATED` | transitions seen; sample rate at least 4× expected; frequency estimate usable |
| `DETECTED` | transitions seen, but rate/duration is insufficient or fewer than two edges; **do not quote a frequency** |
| `STATIC_OBSERVED` | no transitions over a long-enough window at ≥4× oversampling; does **not** prove the wire is silent |
| `INCONCLUSIVE` | rate/duration too low, or `CFG` changed; no conclusion |
| `ERROR` | invalid input or MMIO/time failure |

Recommended report form:

| Pin | Group | Signal | Status | `sample_rate_hz` | `freq_hz` | Note |
|---:|---|---|---|---:|---:|---|
| 22 | PINMUX2 | FSC | | | | |
| 26 | PINMUX3 | FSC_2 | | | | |
| 21 | PINMUX2 | DCL | | | | |
| 25 | PINMUX3 | DCL_2 | | | | |

Rules:

- Only call `FREQUENCY_ESTIMATED` a measurement.
- For `DETECTED`, report "edges observed, frequency not established".
- For `STATIC_OBSERVED`, report "no edges seen by this input path at this
  rate", not "no clock".
- If both groups are static, the result does not distinguish reset, missing
  firmware, wrong pins, wrong mux or an input-path problem.
- If one group toggles at plausible rates, it narrows Q31 but still does not
  prove PCB continuity.

---

## 7. Evidence to keep

- exact OpenWrt release, kernel and DTB hash;
- `uname -a`, `/proc/cmdline`, `/proc/iomem` excerpt;
- tool SHA256 and the build/commit record;
- `c0plus-inspect.txt`, `c0plus-fsc.txt`, `c0plus-bclk.txt`;
- operator, date/time, ambient setup, analog line state;
- any stop condition and the exact last command.

Store raw output outside the public repository if it contains unique device
data.  Do not publish proprietary binaries or full dumps.

---

## 8. Kernel-side alternative

`tools/fon-tlmm-clock-probe/kernel/fon_tlmm_probe.c` is a skeleton that reads
the same registers with `readl()`.  It can sample faster than userspace, but
it is still an input-path observation.

Do **not** build or load it in this stage.  If it is ever approved:

```sh
# Offline build only, in a copy of the target kernel tree:
make -C /path/to/linux-6.12.112 \
     M=$PWD/tools/fon-tlmm-clock-probe/kernel modules

# Loading is a separate hardware action.  It must not be done here.
```

The module has `gpio`, `duration_ms` and `expected_hz` parameters.  It
contains no MMIO writes, GPIO requests, pinctrl changes, clock/reset calls or
interrupt setup.  The same stop conditions and interpretation table apply.

---

## 9. What this stage does not authorize

- GPIO40 toggle or SC14448 reset;
- SC14448 firmware upload;
- ADSS/TDM/DMA start;
- pinmux, clock or reset changes;
- analog line/ring;
- any write to `/dev/mem`;
- loading a kernel module without separate review.

The only result of a successful run is evidence about the IPQ4019 input path.
