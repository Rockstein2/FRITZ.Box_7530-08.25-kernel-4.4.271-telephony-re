# FON go / no-go gates

Status: **probe-only and C1 completed; D0.6 offline reconstruction completed;
C0+ R1 corrected the OEM window and hardened the probe; C0+-K kernel module
is prepared offline; C4 and every active SC14448 action remain NO-GO**

Each gate names the open question it closes (see `fon-open-questions.md`)
and the fact it relies on (see `fon-known-facts.md`).

The first hardware session may advance only the gates marked `pending`, one
stage at a time.  Do not skip from probe-only to DMA or line control.

| Gate | Evidence required | Produced by | Status |
|---|---|---|---|
| Target artifact integrity | `sha256sum` matches `bench/fon_tdm_drv.sha256` (`cd5c05fb…aff6`) | workstation + router | **PASS 2026-11-07** |
| Probe-only module loads (closed Stage B check) | `bench/load-probe-only.sh` PASS + dmesg | Stage B | **PASS 2026-11-07** |
| FON DT node binds (closed Stage B check) | `stage = 0x23`, `mode=probe-only` | Stage B | **PASS 2026-11-07** |
| IRQ not requested in probe-only (closed Stage B check) | `irq_spi=156/159`, `irq_intid=188/191`, `irq=-1` | Stage B diagnostics | **PASS 2026-11-07** |
| No visible resource overlap (closed Stage A/B check) | `/proc/iomem` identical before/after | Stage A/B | **PASS 2026-11-07** |
| Clock/reset/pinctrl ownership (Q2, Q3) | `/proc/iomem`, `/proc/interrupts`, pinctrl/clk export | Stage A + review | **PARTIAL 2026-11-07** — probe-only holds `clock_refs=0 reset_refs=0 pinctrl_ref=0`; GPIO40 unclaimed was confirmed in D0.6; real ownership under DMA still open |
| TDM clocks present (Q4, Q5) | read-only TLMM software probe (C0+) and/or passive FSC/DCL/MCL measurement | C0+ under a `CONFIG_DEVMEM=y` test kernel; scope/analyzer for the electrical answer | **pending** |
| SC14448 running (Q4) | read-only TLMM edge evidence and/or passive UART/clock evidence | C0+ test kernel or scope/logic analyzer | **pending** |
| GPIO40 software ownership | OEM DTB + `Piglet_noemif.ko` disassembly + OpenWrt pinctrl state | Stage D0.6 | **PASS (software path)** — GPIO40 belongs to `dect_loader` under FRITZ!OS and is unclaimed under OpenWrt |
| GPIO40 electrical net/polarity/safety (Q13, Q15, Q39) | identified net plus passive electrical evidence | future bench stage | **pending — blocks any toggle** |
| Recovery proven (Q23) | tested rollback to known-good image | bench dry-run | **pending** |
| Full MMIO read path | explicit reviewed clock/reset proof | separate future stage | **not started** |
| MBOX DMA | MBOX start/IRQ review | separate future stage | **not started** |
| Firmware upload | reviewed loader + isolated line | separate future stage | **not started** |
| Line/ring | high-voltage review and test plan | separate future stage | **not started** |

## What probe-only does NOT prove

- It does not prove that no hardware access happened: the driver core runs
  `pinctrl_bind_pins()` and clock/assigned-clock defaults **before** the
  driver's `probe()`, and debugfs reads can touch registers.
- An unchanged `/proc/iomem` means only that no new visible claim appeared;
  it is not proof of absence of all mappings, conflicts or hidden
  firmware/secure regions.
- A successful `insmod` is not a successful probe; only `stage/mode` and
  the diagnostics checks count.
- It says nothing about SC14448, analog polarity, clock correctness or line
  hardware.

## Decision rules

1. Any `WARNING`/`BUG`/`Oops`/lockdep during Stage B closes the session as
   **NO-GO**.
2. Any unexpected `/proc/iomem` change closes the session.
3. A missing runtime IRQ/clock/reset explanation means **NO-GO** for the
   next stage.
4. Probe-only success only closes probe-only gates; it does not authorize
   `probe_only=0`, `diag_refresh`, DMA, GPIO40 or firmware.
5. The hardware session ends with a written result: commands, outputs,
   checksums and the next gate.

## Overall status

```text
probe-only preparation:   READY
probe-only hardware:      PASS (2026-11-07)
C1 MMIO read:             PASS (2026-11-07)
D0.6 offline RE:          COMPLETE
C0+ offline preparation:  PASS (tool + tests + runbook)
C0+ R1 correction:        PASS (Piglet 100 ms; gap/stability logic)
C0+-K offline:            PASS (one-shot kernel module built offline; not loaded)
C0+ userspace hardware:   NO-GO on stock image (no /dev/mem)
C0+-K hardware run:       NOT RUN (needs separate approval)
OEM 08.25 live readback:  PASS (read-only console)
D0.6 read-only snapshot:  NOT RUN
C2 rerun / C4 DMA:        NOT READY
SC14448 reset/upload:     NOT READY
line/ring:                NOT READY
```

See `runbook/fon-first-hardware-test.md`, `runbook/fon-recovery-ram-boot.md` and
`fon-open-questions.md`.

## Already confirmed (not gates any more)

These were open before the OEM bootlog was cross-checked; see
`fon-known-facts.md`:

- GIC INTID for mbox3 is 191 (`GIC_SPI 159` + 32).
- DMA channels are TX 0 / RX 7, stereo ports 0 / 3.
- GPIO35 is the FON LED; GPIO40 is the DECT reset line.
- ADSS is the TDM **slave**; the SC14448 supplies BCLK/FSC.
- The SC14448 firmware is uploaded before any TDM client exists.
- `dect_loader` holds reset API value 0 while initialising the UART, then
  supplies API value 1 before firmware transfer.
- PINMUX2/PINMUX3 compile to profile values 2/3; `pcmlink.ko` applies the
  profile through `dakota_gpio_pinconfig()`. The actual TLMM `FUNC_SEL` field
  and PCB connectivity are still UNKNOWN (Q27/Q31/Q77).

They still need runtime confirmation on our kernel, which is what the gates
above ask for; the *expectation* is no longer unknown.

### Stage D0.6 gates (2026-11-08)

| Gate | Evidence | Status |
|---|---|---|
| OEM HW236 DTBs extracted | three self-consistent blobs at `0x98d038`, `0x993990`, `0x99a2e8`; FON properties identical; only `subrevision` differs | **PASS (extraction)** |
| Board subrevision | OEM 08.25 capture reports `HWS(2)`, matching the first blob | **PASS (OEM-CAPTURE)** |
| Which DTB the OEM bootloader selects | Q80 | **UNKNOWN** |
| GPIO40 software path | `get_profile()` → `profile+0x28` → `dect_loader()` | **PASS** |
| UART/reset API order | `0xb54` value 0 → `0xb80` UART init → `0xb9c` value 1 | **PASS** |
| PINMUX2/PINMUX3 numeric values | OEM DTB `function=<2>/<3>` + Linux pinctrl indices | **PASS** |
| Actual OEM live TLMM `FUNC_SEL` | GPIO21/22=2; GPIO23/25/26/27=3; GPIO20/24=0 (`/proc/avm/gpio/list`) | **PASS (OEM-CAPTURE)** |
| OpenWrt TLMM `FUNC_SEL` / physical wiring | Q27/Q31 | **UNKNOWN** |
| `Check_TDMInterface` pad side effects | `dakota_gpio_ctrl()` body (Q81) | **UNKNOWN** |
| GPIO40 OEM live pad | `OUT func=0 val=1`, `CFG=0x00004a02` | **PASS (OEM-CAPTURE)** |
| Physical reset polarity/net | Q13/Q39 | **pending** |
| `dakota_gpio_*` electrical/register transformation | Q77 | **pending** |
| Inverter role | no connection to GPIO40 or reset proven | **UNKNOWN** |
| Active reset/upload/TLMM write | requires separate future authorization | **NO-GO** |

Current D0.6 result: `fon-d06-summary.md`. Detailed reverse-engineering is in
`history/fon-d06-*.md`; procedures are under `runbook/`.

### Stage C gates

| Gate | Evidence required | Produced by | Status |
|---|---|---|---|
| C0 collector runs and archives | `bench/collect-stage-c0.sh` exits 0, summary archived | Stage C0 | **PASS 2026-11-07** |
| C0 shows no ADSS owner | `adss-ranges.txt` = "no ADSS ranges claimed" | Stage C0 | **PASS 2026-11-07** |
| C0 shows audio clocks at enable 0 | `audio-clocks.txt` | Stage C0 | **PASS 2026-11-07** |
| Passive TDM measurement | FSC 8 kHz / BCLK 1.0257 MHz present or absent | scope | **not done** |
| FON node has clock/reset links | DT contains `clocks` and `resets` | DT change + review | **not done** |
| C1 module built in kernel tree | new SHA-256 recorded, Stage B still passes | build | **PASS**: module `2b523aec...9e40` (94 180 B) built from the kernel tree, Stage B re-passed, C1 executed |
| Physical power-cycle path | operator confirms | operator | pending |

Stage C0: **PASS, executed 2026-11-07** on the probe-only image; the
collector needed three fixes found only on the real device (busybox awk has
no `strtonum`, `od` is absent, and the iomem owner test must match only the
ADSS window).  Bench tests: 20 passed, 0 failed.
Stage C1: **EXECUTED 2026-11-07** (`probe_only=0 run_c1=1`).  The block
answered: `TDM_CTRL=0x00010001`, `STEREO_CONFIG=0x102`, all other registers
zero.  The board did not hang and the module unloaded cleanly.

Result: the ADSS window is readable with the AHB clock enabled, TDM is
**not** configured for 8 slots, and the block comes up as **master**, not
slave.  A clock-framework warning on the disable path means the gate stop
is unconfirmed.
Dialog firmware upload: **NO-GO** until C0 and the passive measurement
separate "no firmware" from "no clocks".

### Stage C2.1 gates (code only, no hardware run)

| Gate | Evidence | Status |
|---|---|---|
| C1 returns real errors | offline review + header contract | **done** |
| C2 readback is strict | `src/fon-driver/tests/fon_c2_test.c`, 19 checks | **done** |
| C2 follows AVM order | `history/fon-adss-avm-init-sequence.md` | **done** (code), not run |
| Clock warning explained | `history/fon-audio-ahb-clock-warning.md` | **partly**: cause identified, gate state unproven |
| STEREO/MBOX map correct | `fon-adss-clock-reset.md` correction | **done** |
| Stage C3 prepared | this iteration only documents; no code | **not started** |

**Stage C3 is NO-GO** until the clock-disable warning is understood well
enough to know whether the gate closes.  Running C3 with an unclosed gate
would leave the ADSS clocked while software believes it is off.

### Stage C3 gates (2026-11-08)

| Gate | Evidence | Status |
|---|---|---|
| FON audio node identified | `tdm@0` vs `pcm@7704000`; DTB + OEM log | **PASS** — `history/fon-adss-tdm-channel-map.md` |
| MBOX/stereo mapping matches AVM | stereo-tx 0 / stereo-rx 3, MBOX0/MBOX3 | **PASS** — our DTS already matches |
| `dma-tx-channel` is not a hardware selector | `ipq-adss-avm.c:2208,2216` | **PASS** |
| Control-only frame builder | `fon_tdm_buffer_*`, host tests | **PASS** |
| Driver builds against 6.12 | `fon_tdm_drv.ko` built from the target tree | **PASS** |
| Modules default to no transmission | `allow_dma`, `allow_hw_writes`, `probe_only` defaults | **PASS** |
| `dma_start` still refuses | returns `-EOPNOTSUPP` | **PASS (intentional)** |
| `fs_per_dma` confirmed | Q76 | **pending** |
| SC14448 clocks present (Q4/Q27) | passive scope | **pending — blocks C4** |
| Clock-disable gate understood | `history/fon-audio-ahb-clock-warning.md` | **pending** |

**C4 (active TDM) is NO-GO** until Q4/Q27 show the SC14448 supplies
BCLK/FSC **and** the clock gate is understood.  Dry-run frame building is
offline only and changes no hardware state.

### Stage C0+ gates (software TDM clock probe, 2026-11-08)

| Gate | Evidence | Status |
|---|---|---|
| OEM Piglet algorithm recovered | 100 ms window, `5 * edges`, `[piglet]TDM` call site | **PASS (DISASM)** |
| OEM pcmlink diagnostic separated | ~195 ms window; not the boot line | **PASS (DISASM)** |
| TLMM register map verified | base `0x01000000`, stride `0x1000`, `IO+4` bit 0 | **PASS (GPL source)** |
| Userspace read-only tool | `tools/fon-tlmm-clock-probe/`, `PROT_READ` only, no GPIO/pinctrl/clk/reset calls | **PASS (offline build)** |
| Synthetic signal tests | 52 core checks: 8 kHz at 4×/8×/16×, 1.024 MHz, undersampled/aliased BCLK, gaps, frequency change, pulses, noise, short window | **PASS** |
| OEM numeric timing test | Piglet 100 ms and PCMLINK ≈195 ms arithmetic | **PASS** |
| Source write guard | no `PROT_WRITE`, `writel`, GPIO request, pinctrl/clock/reset; idle `module_init` | **PASS** |
| Stock OpenWrt `/dev/mem` | `# CONFIG_DEVMEM is not set` | **NO-GO for userspace probe on stock image** |
| C0+-K kernel module | one-shot debugfs trigger, allowed GPIO21/22/25/26, 20–50 ms, one page, `readl` only | **PASS (offline build)**; not loaded |
| C0+-K hardware run | requires separate review | **NO-GO until approved** |
| Physical wire/amplitude/quality | still requires electrical evidence | **pending** |
| Physical wire/amplitude/quality | still requires electrical evidence | **pending** |

The C0+ tool is an observation aid.  A clean FSC/BCLK result would narrow Q4,
Q5, Q27 and Q31, but it would **not** authorize reset, firmware, DMA or
line/ring, and it would not prove the physical connection to the SC14448.
