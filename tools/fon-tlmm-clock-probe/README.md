# fon-tlmm-clock-probe

Read-only userspace probe for the IPQ4019 TLMM input levels used by the FON
TDM clock candidates.

> **Status: offline development only.**
> The tool has not been run on the router.  Running it is a hardware action
> and requires the separate approval in
> `docs/runbook/fon-stage-c0plus-software-clock-probe.md`.
> It maps MMIO read-only, but it still observes hardware.
>
> The stock OpenWrt image has no `/dev/mem`; the preferred hardware path is
> the one-shot kernel module in `kernel/`, documented in
> `docs/runbook/fon-stage-c0plus-kernel-probe.md`.

The program is a diagnostic instrument, not a driver.  It answers one narrow
question:

> Does the IPQ4019 input path see transitions on GPIO21/22/25/26?

It does **not** prove the physical connection to the SC14448, the signal
amplitude, the signal quality, or that a low result means the SC14448 is
silent.

---

## 1. What it reads

The IPQ4019 TLMM window is:

```text
TLMM base            0x01000000
GPIO_CFG(n)          base + n * 0x1000
GPIO_IO(n)           base + n * 0x1000 + 4
input level          GPIO_IO(n) bit 0
FUNC_SEL             GPIO_CFG(n) bits 5:2
output enable        GPIO_CFG(n) bit 9
```

This matches Linux 6.12
`drivers/pinctrl/qcom/pinctrl-ipq4019.c`:

```c
.ctl_reg = 0x0 + 0x1000 * id,
.io_reg  = 0x4 + 0x1000 * id,
.mux_bit = 2,
.oe_bit  = 9,
.in_bit  = 0,
```

The probe reads only `GPIO_CFG` and `GPIO_IO`.  It never writes a register.

Candidate addresses:

| GPIO | Signal | `GPIO_IO` address |
|---:|---|---|
| 21 | DCL / BCLK, PINMUX2 | `0x01015004` |
| 22 | FSC, PINMUX2 | `0x01016004` |
| 25 | DCL / BCLK, PINMUX3 | `0x01019004` |
| 26 | FSC, PINMUX3 | `0x0101a004` |
| 20 | MCL, PINMUX2 | `0x01014004` |
| 24 | MCL, PINMUX3 | `0x01018004` |
| 23 | DI | `0x01017004` |
| 27 | DO | `0x0101b004` |
| 40 | DECT reset | `0x01028004` |

`FUNC_SEL` is reported for context only.  It does not prove that a clock is
present.

---

## 2. Safety rules

The source contains:

- no `PROT_WRITE` mapping;
- no `O_RDWR`;
- no MMIO writes;
- no GPIO character-device request;
- no `gpiod_*` or `gpio_get_value()`;
- no pinctrl state change;
- no clock or reset operation;
- no interrupt configuration;
- no kernel module load.

`make test` runs a source guard for these rules.  The guard is not a proof of
runtime side effects; the runbook and code review are still required.

The probe does **not**:

- toggle GPIO40;
- reset the SC14448;
- upload firmware;
- enable ADSS or DMA;
- change pinmux;
- enable or disable clocks;
- feed or ring the analog line.

---

## 3. Build

Host build and offline tests:

```sh
cd tools/fon-tlmm-clock-probe
make
make test
```

Cross-build for the router (use the toolchain prefix installed in the
workspace; the exact prefix depends on the SDK):

```sh
make clean
make CC=arm-openwrt-linux-muslgnueabi-gcc
```

The binary is dynamically linked against the target libc.  Check it with
`file` and `readelf -d` before copying it to the router.

---

## 4. The stock OpenWrt blocker

The stock OpenWrt 25.12.6 build in this workspace has:

```text
# CONFIG_DEVMEM is not set
CONFIG_IO_STRICT_DEVMEM=y
```

Therefore `/dev/mem` is normally **not available** and the userspace probe
cannot run on the stock image.  `--dry-run` still works; `--inspect` and the
measurement modes will stop at `open /dev/mem`.

Two valid routes:

1. build a reviewed test kernel with `CONFIG_DEVMEM=y` and verify whether
   `CONFIG_STRICT_DEVMEM`/`CONFIG_IO_STRICT_DEVMEM` still block the TLMM
   range; or
2. use the one-shot kernel module in `kernel/`, which reads the same
   registers through `readl()`, is idle after `insmod`, and requires an
   explicit debugfs trigger.

Neither route is authorized by this document.  The stock-image result is
**NO-GO** for the userspace probe.

---

## 5. Usage

```sh
# Show the planned addresses without touching /dev/mem:
./fon-tlmm-clock-probe --measure-all --dry-run

# Inspect CFG/IO for GPIO20-27 and GPIO40:
./fon-tlmm-clock-probe --inspect

# Measure both FSC candidates:
./fon-tlmm-clock-probe --measure-fsc --duration-ms 200

# Measure both DCL/BCLK candidates:
./fon-tlmm-clock-probe --measure-bclk --duration-ms 200

# Measure all four candidates:
./fon-tlmm-clock-probe --measure-all --duration-ms 200
```

The default observation is 200 ms per pin.  The accepted range is 10 ms to
2000 ms; `--max-duration-ms` can lower the cap.

Each measurement prints one machine-readable line:

```text
gpio=22 signal=FSC address=0x01016004 cfg=... io=... func=... oe=... input=...
samples=... edges=... elapsed_s=... sample_rate_hz=... freq_hz=...
status=... cfg_changed=0 max_gap_ns=... gap_total_ns=... gap_count=...
segments=... zero_edge_segments=... min_segment_edges=...
max_segment_edges=... timing_suspect=0
```

Exit codes:

| Code | Meaning |
|---:|---|
| 0 | all requested measurements completed without `INCONCLUSIVE` |
| 1 | internal/measurement error |
| 2 | usage error |
| 3 | `/dev/mem` or mapping unavailable |
| 5 | at least one `INCONCLUSIVE` result |
| 6 | at least one `ERROR` result |

---

## 6. Interpreting the result

| Status | Meaning |
|---|---|
| `FREQUENCY_ESTIMATED` | transitions seen, sample rate ≥4× expected, timing stable, segments stable and frequency within 0.5–2× the expected value |
| `DETECTED` | transitions seen, but the sample rate is too low, the window is too short, fewer than two edges were counted, or the frequency is outside the plausible range; frequency is **not** reliable |
| `STATIC_OBSERVED` | no transitions over a long-enough window with at least 4× oversampling and no significant timing gap |
| `INCONCLUSIVE` | a significant gap, `CFG` change, unstable segment density, or insufficient sampling/duration |
| `ERROR` | invalid input or clock/MMIO failure |

Important:

- `STATIC_OBSERVED` does **not** prove the SC14448 is silent.  It proves only
  that this input path did not register edges at this sample rate.
- `DETECTED` does **not** prove a valid TDM clock.  Noise and unrelated
  digital activity can produce edges.
- `FREQUENCY_ESTIMATED` for BCLK is only credible if the reported
  `sample_rate_hz` is comfortably above 4.1 MHz.  A userspace loop may not
  reach that rate; the kernel skeleton exists for that reason.
- `cfg_changed=1` means another agent modified `GPIO_CFG`; the run is not a
  clean measurement.
- Timing is checked every 64 reads.  A scheduler gap larger than the normal
  checkpoint interval is reported in `max_gap_ns`/`gap_total_ns` and forces
  `INCONCLUSIVE`; this is deliberate and may reduce the maximum sample rate.
- A high average sample rate is not enough: a large local gap still makes the
  result inconclusive.
- A frequency outside the plausible range is reported as `DETECTED`, not as a
  confident clock.

---

## 7. OEM reference algorithm

The OEM boot message:

```text
[piglet]TDM: FS: 8000 Hz CLK: 1024355 Hz
```

comes from `Piglet_noemif.ko:Check_TDMInterface()`, not from the
`pcmlink.ko` diagnostic command.  Piglet uses a measured **100 ms** window
and reports:

```text
frequency = edges / (2 * 100 ms) = 5 * edges
```

`pcmlink.ko:ipq40xxtdm_checkhw()` is a separate diagnostic command with a
different, roughly 195 ms window and the same `5 * edges` expression.  Over
that window the expression is about 1.95× high; it is not the source of the
OEM boot line.  See
`docs/history/fon-tdm-clock-software-check.md` for the instruction-level
correction.

---

## 8. Tests

`make test` runs:

- `tests/test_core.c` — 52 checks: static, 8 kHz, 1.024 MHz, 1.025 MHz,
  4x/8x/16x oversampling, undersampled/aliased BCLK, scheduler gaps,
  high-average/local-gap, frequency change, short pulses, noise-like
  toggling, short window and invalid input;
- `kernel/tests/test_logic.c` — 25 checks for the shared kernel timing logic:
  stable FSC/BCLK, OEM BCLK 1.024355 MHz, zero/one-edge segments, frequency
  change, scheduler gaps, low edge density and the one-shot state machine;
- `tests/check_readonly.py` — source guard against MMIO writes, GPIO requests,
  pinctrl, clock and reset operations, plus an idle-`module_init` guard.

The repository-level `tools/tests/test_oem_tdm_timing.py` separately checks
the Piglet 100 ms magic constant and the PCMLINK 195 ms arithmetic.

The synthetic tests do not touch hardware.

---

## 9. Kernel alternative

`kernel/fon_tlmm_probe.c` is the preferred stock-image path.  It is idle
after `insmod`: `module_init` only creates
`/sys/kernel/debug/fon_tlmm_probe`.  Writing `1` to that file performs one
bounded 20–50 ms measurement of GPIO21/22/25/26; a second trigger in the same
module lifetime returns `-EALREADY`.  Reading returns the last result and
never measures.  It maps one 4 KiB TLMM page, uses `readl()` only, and calls
`cond_resched()` without disabling preemption or interrupts.

Gap checkpoints (32 reads) are separate from frequency segments (~2 ms).
Fewer than three valid segments, zero/low-edge segments, a frequency change
or a large gap makes the result `INCONCLUSIVE` rather than a confident
frequency.

It is deliberately excluded from the userspace `make` target.  It has been
compiled offline against 6.12.112 as a compile check, but it has not been
loaded.  The separate C0+-K runbook governs K1 (load/unload) and K2
(one-shot measurement); see also
`docs/history/fon-c0plus-kernel-safety-review.md` and
`docs/history/fon-c0plus-kernel-build-report.md`.

The kernel path can sample faster than userspace, but it has the same
limitations: it observes only the IPQ4019 input path, not the physical wire
to the SC14448.

---

## 10. Files

```text
Makefile
fon-tlmm-clock-probe.c
fon-tlmm-clock-probe-core.c
fon-tlmm-clock-probe-core.h
tests/test_core.c
tests/check_readonly.py
kernel/fon_tlmm_probe.c
kernel/fon_tlmm_probe_logic.h
kernel/tests/test_logic.c
kernel/Makefile
kernel/README.md
.gitignore
README.md
```
