# FON-C0+ offline validation (software TDM clock probe)

> **Status: offline only.**
> No router was touched, no `/dev/mem` on the router was opened, no module was
> loaded and no GPIO/pinmux/clock/reset action was performed.  The kernel
> skeleton was compiled offline and then cleaned.

Base revision before this work: `1f6ad7b`
(`research(fon): capture OEM P1 runtime and profile findings`).

---

## 1. Corrected OEM algorithm

| Item | Result | Evidence |
|---|---|---|
| Boot-time check | `Piglet_noemif.ko:Check_TDMInterface()` `0x3f0c..0x414c` | DISASM |
| Boot window | 100 µs, derived from `cyclefreq / 1,000,000 * 100` | DISASM |
| Boot formula | `frequency = edges / (2 * 100 us) = 5 * edges` | DISASM |
| Boot message | `[piglet]TDM: FS: 8000 Hz CLK: 1024355 Hz` | OEM-CAPTURE |
| Diagnostic check | `pcmlink.ko:ipq40xxtdm_checkhw()` `0xa3b4..0xa7f0`, called from `cmd_general` `0xa880` | DISASM |
| Diagnostic window | 64-bit constant `0x82de1b43db34b6d7`; ≈195 ms, not 0.38 s | DISASM |
| Diagnostic formula | same `5 * edges`; not the boot value | DISASM |

The previous clock document mixed the two functions.  The corrected version is
`docs/history/fon-tdm-clock-software-check.md`.

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
MCL 20/24, DI 23, DO 27 and RESET 40 are inspect-only.

## 3. Tool and tests

`tools/fon-tlmm-clock-probe/` contains:

- userspace probe with `--inspect`, `--measure-fsc`, `--measure-bclk`,
  `--measure-all`, `--dry-run`;
- pure edge-counter core;
- synthetic tests;
- static source guard;
- optional kernel skeleton.

| Check | Result |
|---|---|
| Host build | **PASS** |
| Synthetic core tests | **31 PASS, 0 FAIL** |
| Source guard (`PROT_WRITE`, GPIO request, pinctrl/clk/reset) | **PASS** |
| Cross build for ARMv7 musl | **PASS** |
| Kernel skeleton offline build against 6.12.112 | **PASS** (not loaded) |
| Docs consistency | **0 failures, 0 skips** |
| Router run | **NOT RUN** |

The cross-build binary for the current source was:

```text
ELF 32-bit LSB executable, ARM, EABI5, interpreter /lib/ld-musl-armhf.so.1
sha256 651e2cc94621f25a3e450a7157a4e7f55ac7c100ce4bd054c1b28eccad5b4a46
```

The hash is a build record, not a committed artifact.  Rebuild and record the
exact hash before any hardware use.

Synthetic cases include static 0/1, 8 kHz, 1.024 MHz, 1.025 MHz,
undersampled/missed-edge BCLK, a sampling gap, noise-like toggling, a single
edge and invalid input.

## 4. Stock OpenWrt blocker

The OpenWrt 25.12.6 build in this workspace has:

```text
# CONFIG_DEVMEM is not set
CONFIG_IO_STRICT_DEVMEM=y
```

`/dev/mem` is not available on the stock image, so the userspace probe is
**NO-GO** there.  The runbook requires a reviewed `CONFIG_DEVMEM=y` test
kernel or the separate kernel skeleton.  This is a software/build finding,
not a hardware measurement.

## 5. What remains

- The probe was not run on the router.
- No FSC/BCLK frequency was measured under OpenWrt.
- Q4/Q5/Q27/Q31 remain open; the tool can narrow them only in a separately
  approved hardware stage.
- A positive input-path result would not prove the physical wire, amplitude,
  signal quality, SC14448 reset state or firmware state.

## 6. Files

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

docs/runbook/fon-stage-c0plus-software-clock-probe.md
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
