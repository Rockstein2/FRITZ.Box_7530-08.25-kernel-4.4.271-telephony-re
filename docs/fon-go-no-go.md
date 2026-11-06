# FON go / no-go gates

Status: **probe-only preparation complete; no hardware gate is closed**

Each gate names the open question it closes (see `fon-open-questions.md`)
and the fact it relies on (see `fon-known-facts.md`).

The first hardware session may advance only the gates marked `pending`, one
stage at a time.  Do not skip from probe-only to DMA or line control.

| Gate | Evidence required | Produced by | Status |
|---|---|---|---|
| Target artifact integrity | `sha256sum` matches `bench/fon_tdm_drv.sha256` (`b867b8c5…ad870`) | workstation + router | **pending** |
| Probe-only module loads (Q6) | `bench/load-probe-only.sh` PASS + dmesg | Stage B | **pending** |
| FON DT node binds (Q6) | `stage = 0x23`, `mode=probe-only` | Stage B | **pending** |
| IRQ not requested in probe-only (Q7) | `irq_spi=156/159`, `irq_intid=188/191`, `irq=-1` | Stage B diagnostics | **pending** |
| No resource overlap (Q1) | `/proc/iomem` identical before/after | Stage A/B | **pending** |
| Clock/reset/pinctrl ownership (Q2, Q3, Q14) | `/proc/iomem`, `/proc/interrupts`, pinctrl/clk export | Stage A + review | **pending** |
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
