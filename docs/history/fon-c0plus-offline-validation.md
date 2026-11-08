# FON-C0+ and C0+-R1 offline validation

> **Status: offline only.**
> No router was touched, no `/dev/mem` on the router was opened, no module was
> loaded and no GPIO/pinmux/clock/reset action was performed.  The kernel
> module was compiled offline as a compile check and then cleaned.

Baseline before this work: `b90a72c`
(`feat(fon): prepare read-only TLMM TDM clock probe`).

---

## 1. Corrected OEM algorithm

### 1.1 Piglet — 100 ms, not 100 µs

`Piglet_noemif.ko:Check_TDMInterface()` `0x3f0c..0x414c`:

```text
magic = 0x10624dd3 = 274,877,907
umull r2,r3, cyclefreq, magic
lsr   r6, r3, #6
mul   r6, 100
```

`high32(cyclefreq * magic)` is about `cyclefreq * 0.064`; `>>6` is about
`cyclefreq / 1000`; `*100` is `cyclefreq / 10` cycles = **0.1 s = 100 ms**.
For 25 MHz this is 2,500,000 cycles.

At 8 kHz over 100 ms: 800 periods, 1600 transitions, and
`frequency = edges / (2 * 100 ms) = 5 * edges = 8000 Hz`.
A 100 µs window would contain only 1.6 transitions and could not reach the
100-edge threshold.

FSC and DCL are measured in **sequential** windows, not simultaneously.

### 1.2 PCMLINK — ~195 ms diagnostic

`pcmlink.ko:ipq40xxtdm_checkhw()` `0xa3b4..0xa7f0` uses a 64-bit fixed-point
constant `0x82de1b43db34b6d7`; the recovered window is about
`cyclefreq * 0.19500792` cycles, i.e. **≈195 ms**, and the same `5 * edges`
expression.  Over 195 ms that expression is about **1.95× high**.  It is a
`cmd_general` diagnostic, not the source of the `[piglet]TDM` boot line.

| Item | Result | Evidence |
|---|---|---|
| Boot-time check | `Piglet_noemif.ko:Check_TDMInterface()` `0x3f0c..0x414c` | DISASM |
| Boot window | **100 ms** | DISASM |
| Boot formula | `frequency = edges / (2 * 100 ms) = 5 * edges` | DISASM |
| Boot message | `[piglet]TDM: FS: 8000 Hz CLK: 1024355 Hz` | OEM-CAPTURE |
| Diagnostic check | `pcmlink.ko:ipq40xxtdm_checkhw()` `0xa3b4..0xa7f0` | DISASM |
| Diagnostic window | **≈195 ms** | DISASM |
| Diagnostic formula | same `5 * edges`; ≈1.95× high over 195 ms | DISASM |

Numerical regression test: `tools/tests/test_oem_tdm_timing.py`
(**20 PASS, 0 FAIL**).

## 2. TLMM map

Linux 6.12 `pinctrl-ipq4019.c`:

```text
GPIO_CFG(n) = 0x01000000 + n * 0x1000
GPIO_IO(n)  = 0x01000000 + n * 0x1000 + 4
input       = GPIO_IO(n) bit 0
FUNC_SEL    = GPIO_CFG(n) bits 5:2
OE          = GPIO_CFG(n) bit 9
```

Candidate pins: GPIO21/22 (PINMUX2 DCL/FSC), GPIO25/26 (PINMUX3 DCL/FSC).
MCL 20/24, DI 23, DO 27 and RESET 40 are inspect-only in the userspace tool;
the kernel module allows only 21, 22, 25 and 26.

## 3. Tool and tests

`tools/fon-tlmm-clock-probe/` contains:

- userspace probe with `--inspect`, `--measure-fsc`, `--measure-bclk`,
  `--measure-all`, `--dry-run`;
- pure edge-counter core with timing checkpoints;
- synthetic tests;
- static source guard;
- one-shot kernel module (idle after `insmod`).

| Check | Result |
|---|---|
| Host build | **PASS** |
| Synthetic core tests | **52 PASS, 0 FAIL** |
| Source guard (MMIO writes, GPIO/pinctrl/clk/reset, idle init) | **7 PASS, 0 FAIL** |
| OEM numeric timing test | **20 PASS, 0 FAIL** |
| Cross build for ARMv7 musl | **PASS** |
| Kernel module offline build against 6.12.112 | **PASS** (not loaded) |
| Docs consistency | **0 failures, 0 skips** |
| Router run | **NOT RUN** |

Cross-build binary for the current source:

```text
ELF 32-bit LSB executable, ARM, EABI5, interpreter /lib/ld-musl-armhf.so.1
sha256 f1e8ee5cd665442347dffba8fb3cf73d4647f72da69a9d159655347d80973588
```

Kernel module compile check:

```text
sha256 1d4bf8788dcadf83dbf8bf3beea467e9efa057b8b8063003e40d387445c7247a
vermagic 6.12.112 SMP mod_unload ARMv7 p2v8
```

The hashes are build records, not committed artifacts.  Rebuild and record
the exact hashes before any hardware use.

### 3.1 Confidence changes

The userspace core now tracks:

- checkpoints every 64 reads;
- maximum gap and the number of samples collected during it;
- total significant gap time and count;
- per-segment edge density;
- zero-edge segments when enough periods are expected;
- frequency plausibility against the expected 8 kHz / 1.024 MHz.

A scheduler gap, unstable segment density or `CFG` change forces
`INCONCLUSIVE`.  Low sampling, a short window, too few edges or a frequency
outside 0.5–2× expected produce `DETECTED`, not a confident estimate.

Synthetic cases include static 0/1, 8 kHz at 4×/8×/16×, 1.024 MHz,
1.025 MHz, undersampled/aliased BCLK, scheduler gaps, high-average/local-gap,
frequency change, short pulses, noise-like toggling, short window and invalid
input.

## 4. Kernel-side architecture

`tools/fon-tlmm-clock-probe/kernel/fon_tlmm_probe.c`:

```text
insmod   -> create /sys/kernel/debug/fon_tlmm_probe; idle
echo 1   -> one bounded 20–50 ms measurement of one allowed GPIO
cat      -> last result only
rmmod    -> remove the debugfs node
```

- `module_init()` does not call `ioremap()` and does not measure.
- Only GPIO21/22/25/26 are accepted; GPIO40 is rejected.
- One 4 KiB TLMM page is mapped per trigger.
- Only `readl()` is used; no MMIO writes, GPIO request, pinctrl, clock, reset,
  interrupt or DMA.
- `cond_resched()` every 1024 samples; no preemption/interrupt disabling and
  no real-time scheduling.
- A timing gap or `CFG` change forces `INCONCLUSIVE`.

This is the preferred path for stock OpenWrt because it does not require
rebuilding the kernel with `CONFIG_DEVMEM=y`.

## 5. Userspace vs kernel

| | Userspace `/dev/mem` | One-shot kernel module |
|---|---|---|
| Stock OpenWrt | **blocked**, `CONFIG_DEVMEM` not set | usable after separate approval |
| Build change | test kernel needed | only an external module |
| Access scope | maps TLMM window | maps one 4 KiB GPIO page |
| Max credible sample rate | scheduler-limited | kernel loop, but still scheduler-limited |
| Trigger | process start | explicit debugfs write |
| Load impact | none | `insmod` + 20–50 ms busy loop |
| Main risk | broad physical-memory access | module ABI/load and debugfs active trigger |

The kernel module is preferred, but it is **not** authorized for load by this
document.

## 6. Remaining risks

| Risk | State |
|---|---|
| Physical wire/amplitude/signal quality | **not measured**; requires electrical evidence |
| `ioremap()` vs existing TLMM/pinctrl owner | mapping is read-only and does not claim the resource; runbook review required |
| Scheduler pause during measurement | detected as a timing gap; result downgraded |
| BCLK sample rate below 4.1 MS/s | result is `DETECTED`/`INCONCLUSIVE`, not a frequency |
| CFG changed by another consumer | `cfg_changed=1` -> `INCONCLUSIVE` |
| Debugfs trigger is an active action | documented; not called passive |
| Module ABI/vermagic mismatch | checked in the C0+-K runbook |
| GPIO40/reset/firmware/DMA | still forbidden |

## 7. What remains

- No measurement was run on the router.
- No FSC/BCLK frequency was measured under OpenWrt.
- Q4/Q5/Q27/Q31 remain open; a later approved C0+-K run can narrow them.
- A positive input-path result would not prove the physical wire, amplitude,
  signal quality, SC14448 reset state or firmware state.

## 8. Files

```text
tools/fon-tlmm-clock-probe/
  Makefile
  README.md
  .gitignore
  fon-tlmm-clock-probe.c
  fon-tlmm-clock-probe-core.c
  fon-tlmm-clock-probe-core.h
  tests/test_core.c
  tests/check_readonly.py
  kernel/fon_tlmm_probe.c
  kernel/Makefile
  kernel/README.md

tools/tests/test_oem_tdm_timing.py

docs/runbook/fon-stage-c0plus-software-clock-probe.md
docs/runbook/fon-stage-c0plus-kernel-probe.md
docs/history/fon-tdm-clock-software-check.md
docs/history/fon-c0plus-offline-validation.md
docs/fon-known-facts.md
docs/fon-open-questions.md
docs/fon-go-no-go.md
docs/fon-tdm-control-only-plan.md
docs/runbook/fon-tdm-passive-test.md
docs/README.md
tools/README.md
tools/tests/test_docs_consistency.py
```
