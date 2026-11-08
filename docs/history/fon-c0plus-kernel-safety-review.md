# FON-C0+-K final safety review

> **Status: offline review only.**
> No module was loaded, no debugfs trigger was written, no MMIO was accessed
> on the router and no router state was changed.

Scope: `tools/fon-tlmm-clock-probe/kernel/fon_tlmm_probe.c` and
`fon_tlmm_probe_logic.h`, baseline `3127558` plus the R2 working-tree changes.

---

## 1. Safety invariants

| Invariant | Implementation | Review status |
|---|---|---|
| `insmod` is idle | `module_init()` only calls `debugfs_create_file()` | **PASS by source** |
| No measurement at load | no `ioremap`, no `readl`, no `run_measurement` in init | **PASS by source** |
| One trigger per module lifetime | `PROBE_IDLE` -> `RUNNING` -> `RESULT_READY`/`ERROR`; second trigger returns `-EALREADY` | **PASS by source + state test** |
| No concurrent trigger | `mutex_trylock()`; `-EBUSY` if already held | **PASS by source** |
| Read does not measure | `result_read()` only copies `last_result` | **PASS by source** |
| Allowed pins only | 21, 22, 25, 26; GPIO40 and all others rejected | **PASS by source** |
| Bounded duration | 20–50 ms target; actual elapsed reported | **PASS by source; hardware timing unverified** |
| One page mapping | `ioremap(TLMM_BASE + gpio*0x1000, 0x1000)` | **PASS by source** |
| Read-only MMIO | only `readl()`; no `writel`/`iowrite`/MMIO store | **PASS by source guard** |
| No GPIO/pinctrl/clock/reset API | no such calls; source guard rejects known APIs | **PASS by source guard** |
| No IRQ/DMA | no IRQ request, no DMA API | **PASS by source** |
| No automatic retry | state moves to result/error; no loop in trigger | **PASS by source** |
| CFG change detection | `cfg_before`/`cfg_after`; mismatch -> `INCONCLUSIVE` | **PASS by source** |
| Clean unload | `debugfs_remove()`, no hardware action | **PASS by source; K1 must verify** |

The source guard is a static check.  It is not proof that the module is safe
to load on the running system.

## 2. State machine

```text
insmod
  -> IDLE

write "1" or "1\n"
  -> RUNNING
  -> RESULT_READY  (measurement completed)
  -> ERROR_STATE   (parameter, mapping or measurement failure)

write again
  -> -EALREADY

write while another trigger is active
  -> -EBUSY

cat
  -> last result; no state change

rmmod
  -> cleanup
```

Accepted trigger bytes are exactly `1` or `1\n`.  Longer input, CRLF,
whitespace, and trailing bytes are rejected with `-EINVAL`.

## 3. Frequency-segment policy

Gap checkpoints and frequency segments are separate:

- gap checkpoint: every 32 reads, for scheduler gaps/polling continuity;
- frequency segment: about 2 ms, for edge-count stability.

Per segment:

```text
frequency = edges / (2 * segment_elapsed)
```

Policy:

| Signal | Absolute segment tolerance | Segment-to-segment ratio |
|---|---:|---:|
| FSC | 10% | 20% |
| BCLK | 2% | 4% |

A segment with fewer than 8 edges is not valid evidence.  The result is
`INCONCLUSIVE` if there are fewer than 3 valid segments, any zero-edge
segment when enough edges are expected, any low-edge segment, any frequency
outside the absolute tolerance, or too much segment-to-segment spread.

These tolerances are engineering policy, not a hardware accuracy claim.

## 4. Gap and aliasing limitations

Detected:

- a scheduler pause that produces a gap with zero samples >= 1 ms;
- a gap disproportionate to the samples collected in it;
- total significant gap time >5% of the window;
- a frequency change across 2 ms segments;
- zero/low-edge segments;
- CFG change by another consumer.

Not guaranteed:

- a very short pause entirely between two checkpoint reads;
- a missing edge hidden inside a high-rate polling group;
- aliasing that makes a clock look static at the chosen sample rate;
- every missed edge when the average polling rate is high but locally
  variable;
- physical wire, amplitude, duty cycle or jitter.

`FREQUENCY_ESTIMATED` therefore means "consistent with the expected clock at
the observed sample rate", not "no edges were missed" and not "the physical
signal is valid".

## 5. Load and timing limitations

- The target window is 20–50 ms, but `cond_resched()` and scheduler
  preemption can extend wall-clock execution; actual elapsed time is reported.
- No real-time scheduling, CPU-frequency change, preemption disable or
  interrupt disable is used.
- The loop can consume one CPU for the measurement interval.  The exact
  polling rate on IPQ4019 is not measured.  As a planning range only, a
  1–10 MS/s loop over 20 ms is 20k–200k reads (50 ms: 50k–500k reads); this
  is an estimate, not a hardware result.
- A low rate or a long gap must produce `DETECTED`/`INCONCLUSIVE`.
- Watchdog/softlockup behavior has not been tested on hardware.
- UART/Ethernet/process latency impact has not been measured on hardware.

## 6. Build/ABI limitations

- Vermagic matches the offline 6.12.112 tree:
  `6.12.112 SMP mod_unload ARMv7 p2v8`.
- `CONFIG_MODVERSIONS` is off; vermagic is necessary but not sufficient ABI
  proof.
- K1 must verify the exact running kernel, module SHA256, `insmod`/`rmmod`,
  debugfs mount, and dmesg.
- The module does not claim the TLMM resource with `request_mem_region()`;
  read-only `ioremap()` coexistence with the system pinctrl owner is not
  proven on hardware.

## 7. Hardware-unverified checklist

| Item | Status |
|---|---|
| `insmod` succeeds | **NOT RUN** |
| `module_init()` is idle on the router | **NOT RUN** |
| debugfs node exists and is writable | **NOT RUN** |
| `cat` before trigger returns idle | **NOT RUN** |
| one trigger returns a result | **NOT RUN** |
| second trigger returns `-EALREADY` | **NOT RUN** |
| `rmmod` is clean | **NOT RUN** |
| TLMM mapping does not disturb pinctrl | **NOT RUN** |
| FSC/BCLK physical signal | **NOT MEASURED** |
| BCLK sample-rate adequacy | **NOT MEASURED** |

## 8. Readiness

| Stage | Readiness |
|---|---|
| Kernel logic tests | **PASS, 25/25** |
| K1 — load/unload safety | **READY for separate approval** |
| K2 — one-shot measurement | **blocked by K1** |
| CONFIG_DEVMEM rebuild | **not needed / not recommended** |
| DMA/reset/firmware | **NO-GO** |
| Physical electrical proof | **still required** |

Recommended next action: approve only K1, with no `echo 1`.  K2 must be a
separate decision after K1 passes.
