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
  -> one bounded measurement
  -> result stored in the same debugfs file
  -> idle again; no automatic repeat

cat /sys/kernel/debug/fon_tlmm_probe
  -> last result only; does not measure

rmmod
  -> debugfs_remove()
  -> no measurement
```

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

## Build (offline only)

```sh
make -C /path/to/linux-6.12.112 \
     M=$PWD/tools/fon-tlmm-clock-probe/kernel modules
```

Record the exact `.ko` SHA256, `modinfo vermagic` and kernel release before any
load.  Do not copy or load the module without the separate runbook review.

## Result fields

```text
gpio=... cfg=... io=... func=... oe=... input=...
samples=... edges=... elapsed_ns=... sample_rate_hz=... freq_hz=...
status=... cfg_changed=... max_gap_ns=... gap_total_ns=...
gap_count=... segments=... zero_edge_segments=...
min_rate_q=... max_rate_q=... timing_suspect=...
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
