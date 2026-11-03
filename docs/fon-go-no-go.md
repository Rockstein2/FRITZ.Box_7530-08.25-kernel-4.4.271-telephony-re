# FON go / no-go gates

Status: **probe-only preparation complete; no hardware gate is closed**

The first hardware session may advance only the gates marked `pending`, one
stage at a time.  Do not skip from probe-only to DMA or line control.

| Gate | Evidence required | Produced by | Status |
|---|---|---|---|
| Target artifact integrity | `sha256sum` matches `bench/fon_tdm_drv.sha256` | workstation + router | **pending** |
| Probe-only module loads | expected dmesg lines, no warning/Oops | Stage B | **pending** |
| FON DT node binds | `/sys/bus/platform/devices/.../stage = 0x23` | Stage B | **pending** |
| No resource overlap | `/proc/iomem` before/after identical | Stage A/B | **pending** |
| Clock/reset/pinctrl ownership | `/proc/iomem`, `clk_summary`, pinctrl dump | Stage A + review | **pending** |
| TDM clocks present | passive FSC/DCL/MCL measurement | scope/logic analyzer | **pending** |
| SC14448 running | passive UART/clock evidence | scope/logic analyzer | **pending** |
| GPIO40 not owned/unsafe | DT/pinctrl export + bench review | Stage D0 | **pending** |
| Recovery proven | tested rollback to known-good image | bench dry-run | **pending** |
| Full MMIO read path | explicit reviewed clock/reset proof | separate future stage | **not started** |
| MBOX DMA | MBOX start/IRQ review | separate future stage | **not started** |
| Firmware upload | reviewed loader + isolated line | separate future stage | **not started** |
| Line/ring | high-voltage review and test plan | separate future stage | **not started** |

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

See `docs/fon-first-hardware-test.md`, `docs/fon-recovery-plan.md` and
`docs/fon-dialog-hardware-test-plan.md`.
