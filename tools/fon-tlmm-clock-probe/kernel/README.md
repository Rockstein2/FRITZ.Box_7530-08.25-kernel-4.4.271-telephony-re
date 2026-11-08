# Kernel-side alternative (one-shot, read-only)

`fon_tlmm_probe.c` is the preferred diagnostic path for the stock OpenWrt
image, which has `CONFIG_DEVMEM` disabled.

> **Status: offline build only.**
> The source has been compiled against the OpenWrt 6.12.112 tree as a compile
> check.  It has **not** been loaded or triggered on the router.  Loading and
> triggering are separate hardware actions and require the approval in
> `docs/runbook/fon-stage-c0plus-kernel-probe.md`.

## Architecture

```text
insmod
  -> module_init()
  -> create /sys/kernel/debug/fon_tlmm_probe
  -> no ioremap, no measurement, no GPIO/pinctrl/clock/reset action
  -> idle

echo 1 > /sys/kernel/debug/fon_tlmm_probe
  -> RUNNING
  -> one bounded measurement
  -> RESULT_READY or ERROR
  -> no restart until rmmod/insmod

echo 1 > ... (again)
  -> -EALREADY

cat /sys/kernel/debug/fon_tlmm_probe
  -> last result only; does not measure

rmmod
  -> debugfs_remove()
  -> no measurement
```

Only exactly `1` or `1\n` is accepted.  A second trigger in the same module
lifetime returns `-EALREADY`; a concurrent trigger returns `-EBUSY`.  Reading
the file returns the stored result and never starts a measurement.

Writing `1` to the debugfs file is a virtual-file write, not an MMIO write,
but it is an **active** request.  It is not a passive operation.

## Allowed hardware

Only:

| GPIO | Signal |
|---:|---|
| 21 | DCL / BCLK, PINMUX2 |
| 22 | FSC, PINMUX2 |
| 25 | DCL / BCLK, PINMUX3 |
| 26 | FSC, PINMUX3 |

GPIO40 is deliberately rejected.  There is no clock-probe mode for reset.

The module reads only:

```text
GPIO_CFG(n) = TLMM_BASE + n * 0x1000
GPIO_IO(n)  = TLMM_BASE + n * 0x1000 + 4
```

It maps exactly one 4 KiB page for the selected GPIO, with `ioremap()`.  It
does not claim the resource with `request_mem_region()`, does not write the
register, and does not call the GPIO, pinctrl, clock or reset frameworks.

## Duration and load

| Parameter | Default | Range |
|---|---:|---|
| `gpio` | 22 | 21, 22, 25, 26 |
| `duration_ms` | 20 | 20-50 |
| `expected_hz` | 0 | 0 = derive (8 kHz or 1.024 MHz) |

The measurement is a bounded busy loop with a `cond_resched()` every 1024
samples.  It does not disable preemption or interrupts and does not use
real-time scheduling.  A scheduler pause is detected as a timing gap and
downgrades the result to `INCONCLUSIVE`.

A 20 ms window at 8 kHz covers 160 frames (320 transitions).  A 20 ms window
at 1.024 MHz covers about 20,480 periods; a frequency estimate is honest only
if the observed sample rate is comfortably above 4x the signal.

The loop is not a hard real-time deadline.  `cond_resched()` and scheduler
preemption can make wall-clock execution longer than `duration_ms`; the
result records the actual elapsed time and marks a large gap inconclusive.
No watchdog/softlockup claim is made without a hardware run.

## Timing policy

Two intervals are deliberately separate:

- **gap checkpoints** every 32 reads: detect scheduler gaps and polling-rate
  changes;
- **frequency segments** of about 2 ms: compute
  `frequency = edges / (2 * segment_elapsed)` and compare segments.

A segment with fewer than 8 edges is not valid evidence.  Fewer than three
valid segments, any zero-edge segment, any low-edge segment, or a frequency
change beyond the per-signal tolerance makes the result `INCONCLUSIVE`.
FSC uses 10% absolute / 20% segment-ratio tolerance; BCLK uses 2% / 4%.
These are policy limits, not measured accuracy guarantees.

The logic is shared with host tests in `kernel/tests/test_logic.c`
(25 checks); the kernel source has no separate duplicate formula.

## Build (offline only)

```sh
make -C /path/to/linux-6.12.112 \
     M=$PWD/tools/fon-tlmm-clock-probe/kernel modules
```

Record the exact `.ko` SHA256, size, `modinfo vermagic`, kernel release,
`CONFIG_MODVERSIONS`, `CONFIG_DEBUG_FS` and `Module.symvers` identity before
any load.  See `docs/history/fon-c0plus-kernel-build-report.md`.  Do not copy
or load the module without the separate K1/K2 runbook review.

## Result fields

```text
gpio=... cfg=... io=... func=... oe=... input=...
samples=... edges=... elapsed_ns=... sample_rate_hz=... freq_hz=...
status=... cfg_changed=... max_gap_ns=... gap_total_ns=...
gap_count=... segments=... valid_segments=... zero_edge_segments=...
low_edge_segments=... min_freq_hz=... max_freq_hz=...
min_segment_edges=... max_segment_edges=... timing_suspect=...
```

Statuses:

- `FREQUENCY_ESTIMATED` — sufficient sampling, stable segments, plausible
  frequency;
- `DETECTED` — transitions seen, but frequency accuracy is not confirmed;
- `STATIC_OBSERVED` — no transitions with sufficient sampling;
- `INCONCLUSIVE` — gaps, CFG change, unstable segments or insufficient data;
- `ERROR` — parameter or mapping failure.

Even `FREQUENCY_ESTIMATED` does not prove a valid TDM clock or the physical
wire to the SC14448.
