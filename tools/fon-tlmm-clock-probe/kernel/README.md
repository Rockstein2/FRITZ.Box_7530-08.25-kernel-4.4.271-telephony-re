# Kernel-side alternative (not built, not loaded)

`fon_tlmm_probe.c` is the optional kernel-side version of the read-only TLMM
probe.  It exists because a userspace loop may not reach the sample rate
needed for a credible 1.024 MHz BCLK estimate.

> **Status: source skeleton only.**
> It has not been built against the target kernel or loaded on the router.
> Loading it is a hardware action and requires a separate approval; see
> `docs/runbook/fon-stage-c0plus-software-clock-probe.md`.

## What it does

At module load it:

1. reads `GPIO_CFG(gpio)` and `GPIO_IO(gpio)` from the TLMM window;
2. polls the input bit for `duration_ms`;
3. counts transitions;
4. prints one `pr_info` line with the same status vocabulary as the
   userspace tool;
5. unmaps the window.

It does **not** write MMIO, request a GPIO line, change pinmux, enable a
clock/reset, configure an interrupt, or perform DMA.

## Build (offline only)

```sh
make -C /path/to/linux-6.12.112 \
     M=$PWD/tools/fon-tlmm-clock-probe/kernel modules
```

Do not copy or load the resulting `.ko` without a separate hardware review.

## Parameters

| Parameter | Default | Range |
|---|---:|---|
| `gpio` | 22 | 20-27 or 40 |
| `duration_ms` | 200 | 10-2000 |
| `expected_hz` | 8000 | > 0 |

## Limits

Exactly the same as the userspace tool: the module observes the IPQ4019 input
path.  It cannot prove the physical wire, amplitude, signal quality or the
SC14448 reset/firmware state.  A `STATIC_OBSERVED` result is not proof that
the SC14448 is silent.
