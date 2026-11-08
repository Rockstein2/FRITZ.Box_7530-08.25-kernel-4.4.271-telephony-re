# FON go / no-go gates

Status: **probe-only preparation complete; no hardware gate is closed**

Each gate names the open question it closes (see `fon-open-questions.md`)
and the fact it relies on (see `fon-known-facts.md`).

The first hardware session may advance only the gates marked `pending`, one
stage at a time.  Do not skip from probe-only to DMA or line control.

| Gate | Evidence required | Produced by | Status |
|---|---|---|---|
| Target artifact integrity | `sha256sum` matches `bench/fon_tdm_drv.sha256` (`cd5c05fb…aff6`) | workstation + router | **PASS 2026-11-07** |
| Probe-only module loads (Q6) | `bench/load-probe-only.sh` PASS + dmesg | Stage B | **PASS 2026-11-07** |
| FON DT node binds (Q6) | `stage = 0x23`, `mode=probe-only` | Stage B | **PASS 2026-11-07** |
| IRQ not requested in probe-only (Q7) | `irq_spi=156/159`, `irq_intid=188/191`, `irq=-1` | Stage B diagnostics | **PASS 2026-11-07** |
| No resource overlap (Q1) | `/proc/iomem` identical before/after | Stage A/B | **PASS 2026-11-07** |
| Clock/reset/pinctrl ownership (Q2, Q3, Q14) | `/proc/iomem`, `/proc/interrupts`, pinctrl/clk export | Stage A + review | **PARTIAL 2026-11-07** — probe-only holds `clock_refs=0 reset_refs=0 pinctrl_ref=0`, GPIO40 unclaimed; real ownership under DMA still open |
| TDM clocks present (Q4, Q5) | passive FSC/DCL/MCL measurement | scope/logic analyzer | **pending** |
| SC14448 running (Q4) | passive UART/clock evidence | scope/logic analyzer | **pending** |
| GPIO40 not owned/unsafe (Q13, Q14, Q15) | DT/pinctrl export + bench review | Stage D0 | **pending** |
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
probe-only hardware:      pending user-authorized session
full MMIO/DMA:            NOT READY
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

They still need runtime confirmation on our kernel, which is what the gates
above ask for; the *expectation* is no longer unknown.

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
| C2 follows AVM order | `docs/fon-adss-avm-init-sequence.md` | **done** (code), not run |
| Clock warning explained | `docs/fon-audio-ahb-clock-warning.md` | **partly**: cause identified, gate state unproven |
| STEREO/MBOX map correct | `docs/fon-adss-clock-reset.md` correction | **done** |
| Stage C3 prepared | this iteration only documents; no code | **not started** |

**Stage C3 is NO-GO** until the clock-disable warning is understood well
enough to know whether the gate closes.  Running C3 with an unclosed gate
would leave the ADSS clocked while software believes it is off.

### Stage C3 gates (2026-11-08)

| Gate | Evidence | Status |
|---|---|---|
| FON audio node identified | `tdm@0` vs `pcm@7704000`; DTB + OEM log | **PASS** — `fon-adss-tdm-channel-map.md` |
| MBOX/stereo mapping matches AVM | stereo-tx 0 / stereo-rx 3, MBOX0/MBOX3 | **PASS** — our DTS already matches |
| `dma-tx-channel` is not a hardware selector | `ipq-adss-avm.c:2208,2216` | **PASS** |
| Control-only frame builder | `fon_tdm_buffer_*`, host tests | **PASS** |
| Driver builds against 6.12 | `fon_tdm_drv.ko` built from the target tree | **PASS** |
| Modules default to no transmission | `allow_dma`, `allow_hw_writes`, `probe_only` defaults | **PASS** |
| `dma_start` still refuses | returns `-EOPNOTSUPP` | **PASS (intentional)** |
| `fs_per_dma` confirmed | Q76 | **pending** |
| SC14448 clocks present (Q4/Q27) | passive scope | **pending — blocks C4** |
| Clock-disable gate understood | `fon-audio-ahb-clock-warning.md` | **pending** |

**C4 (active TDM) is NO-GO** until Q4/Q27 show the SC14448 supplies
BCLK/FSC **and** the clock gate is understood.  Dry-run frame building is
offline only and changes no hardware state.
