# Stage C0+-K — one-shot kernel TLMM probe

> **Status: prepared, never executed.**
> This document is not authorization.  K1 and K2 require separate explicit
> approvals.  The module has not been loaded or triggered on the router.

The module is:

```text
tools/fon-tlmm-clock-probe/kernel/fon_tlmm_probe.c
tools/fon-tlmm-clock-probe/kernel/fon_tlmm_probe_logic.h
```

It is the preferred path for stock OpenWrt because `CONFIG_DEVMEM` is not set.
It does not require a kernel rebuild.

The module is split into two independently approved hardware stages:

| Stage | Action | Not included |
|---|---|---|
| **K1** | verify ABI, `insmod`, read idle, `rmmod`, verify cleanup | no `echo 1`, no ioremap by the measurement path, no TLMM measurement |
| **K2** | one-shot measurement of one GPIO after K1 passes | no automatic loop, no DMA/reset/firmware |

K2 is **NO-GO** until K1 has a written PASS.

---

## 1. Preconditions common to K1 and K2

| Condition | Requirement |
|---|---|
| Running system | OpenWrt 6.12.112 test image; **not** OEM 4.4.271 |
| Kernel release | exactly matches the build tree |
| Module ABI | `modinfo` vermagic matches `uname -r` |
| Debugfs | `/sys/kernel/debug` mounted |
| FON driver | not loaded; no DMA/reset/firmware |
| Analog line | disconnected |
| Power | physical power-cycle available |
| Approval | separate recorded approval for the specific stage |

Do **not** switch the board from OEM to OpenWrt, reflash, RAM-boot or reboot
as part of this runbook.  If the board is still on OEM 08.25, stop; the
6.12.112 module cannot be used on 4.4.271.

The current build record is:

```text
source baseline: 3127558
kernel:          6.12.112
vermagic:        6.12.112 SMP mod_unload ARMv7 p2v8
module sha256:   31173cc9eacf34c8487442cc1fd89270d3b48067fead164301b917ed79312a60
module size:     53248 bytes
```

See `../history/fon-c0plus-kernel-build-report.md`.  Rebuild and record the
exact hash again if the source or tree changes.

---

## 2. Preflight (read-only)

```sh
uname -a
cat /etc/openwrt_release
uname -r

ls -ld /sys/kernel/debug
lsmod | grep -E 'fon|adss|pcmlink' || true
dmesg | tail -n 80

ls -l /tmp/fon_tlmm_probe.ko
sha256sum /tmp/fon_tlmm_probe.ko
modinfo /tmp/fon_tlmm_probe.ko
```

Stop if:

- vermagic does not match;
- the SHA256 differs from the recorded build;
- debugfs is not mounted;
- another FON/ADSS/DMA/reset/firmware action is active;
- the module is already loaded.

---

## 3. K1 — Module Load/Unload Safety

**Approval scope:** load and unload only.  No trigger, no measurement.

### 3.1 Load

```sh
insmod /tmp/fon_tlmm_probe.ko gpio=22 duration_ms=20
dmesg | tail -n 10
cat /sys/kernel/debug/fon_tlmm_probe
```

Expected:

```text
fon_tlmm_probe: idle; write 1 to trigger one bounded measurement
idle
```

`module_init()` creates the debugfs node only.  There must be no TLMM
mapping or measurement at this point.

### 3.2 K1 checks

| Check | PASS condition |
|---|---|
| `insmod` | succeeds |
| idle log | present |
| `cat` | returns `idle` |
| second load attempt | not performed |
| `echo 1` | **not performed in K1** |
| `rmmod` | succeeds |
| debugfs node | disappears |
| dmesg | no warning/oops/panic/lockdep |
| GPIO/clock/reset state | no unexpected change |

### 3.3 Unload

```sh
rmmod fon_tlmm_probe
dmesg | tail -n 20
ls /sys/kernel/debug/fon_tlmm_probe 2>&1 || true
```

K1 PASS requires clean removal and no measurement.

### 3.4 K1 stop conditions

Stop and recover immediately if:

- `insmod` or `rmmod` fails;
- a warning/BUG/Oops/panic/lockdep appears;
- console or network is lost;
- the debugfs node is created with unexpected behavior;
- any measurement or MMIO access is observed during load;
- the module cannot be unloaded cleanly.

Do not “fix” K1 by triggering a measurement or writing registers.

---

## 4. K2 — One-shot TLMM Measurement

**Approval scope:** after K1 PASS and a separate approval, measure one GPIO
once per module load.

### 4.1 Recommended order

1. GPIO22 — FSC, PINMUX2.
2. GPIO26 — FSC, PINMUX3.
3. GPIO21 — BCLK, PINMUX2.
4. GPIO25 — BCLK, PINMUX3.

Each GPIO is a separate `insmod`/trigger/`rmmod` cycle.  Do not script a loop.

### 4.2 Procedure per GPIO

```sh
insmod /tmp/fon_tlmm_probe.ko gpio=22 duration_ms=20
cat /sys/kernel/debug/fon_tlmm_probe

# one explicit trigger only
echo 1 > /sys/kernel/debug/fon_tlmm_probe
cat /sys/kernel/debug/fon_tlmm_probe

rmmod fon_tlmm_probe
dmesg | tail -n 20
```

If a second `echo 1` is deliberately tested, it must return `-EALREADY`
without a new measurement.  Do not repeat it.

### 4.3 Result

```text
gpio=... cfg=... io=... func=... oe=... input=...
samples=... edges=... elapsed_ns=... sample_rate_hz=... freq_hz=...
status=... cfg_changed=... max_gap_ns=... gap_total_ns=...
gap_count=... segments=... valid_segments=... zero_edge_segments=...
low_edge_segments=... min_freq_hz=... max_freq_hz=...
min_segment_edges=... max_segment_edges=... timing_suspect=...
```

Interpretation:

| Status | Meaning |
|---|---|
| `FREQUENCY_ESTIMATED` | stable segments, sufficient sampling, plausible frequency |
| `DETECTED` | transitions seen, frequency not confirmed |
| `STATIC_OBSERVED` | no transitions with sufficient sampling |
| `INCONCLUSIVE` | gap, CFG change, unstable/low-edge segments or insufficient data |
| `ERROR` | parameter, mapping or measurement failure |

Even `FREQUENCY_ESTIMATED` does not prove the physical wire, amplitude,
signal quality, SC14448 reset state or firmware state.

### 4.4 K2 stop rules

- If FSC gives `ERROR`, `INCONCLUSIVE` with a load/timing problem, or the
  system shows any warning, do not proceed to BCLK.
- If BCLK sampling is insufficient, accept `DETECTED`/`INCONCLUSIVE`; do not
  increase duration beyond 50 ms or add repeated triggers.
- Do not use real-time scheduling, CPU pinning, governor changes or interrupt
  disabling.

---

## 5. Safe return to OpenWrt — future check only

This section is a **plan**, not an action.  If the board is currently running
OEM 08.25, do not execute it now.

A future return check must confirm, without writing NAND:

- the restore image and recovery assets still match their SHA256 records;
- the EVA/U-Boot recovery route and power-cycle access are known;
- the host network addresses and TFTP root are correct;
- no `sysupgrade`, RAM-boot, reboot or NAND write is performed as part of the
  check;
- the operator has a separate decision to leave OEM and return to OpenWrt.

The check must not be used as an excuse to start K2 or to alter the router
during this stage.

---

## 6. Load and timing limitations

- The target window is 20–50 ms, but wall-clock execution can be longer if
  `cond_resched()` or the scheduler preempts the loop; actual elapsed time is
  in the result.
- No preemption/interrupt disabling, RT scheduling or CPU-frequency changes
  are used.
- The measurement can consume one CPU for the interval.  The exact polling
  rate on IPQ4019 is not measured offline.
- A low rate or long gap must produce `DETECTED`/`INCONCLUSIVE`; it must not
  be reported as a confident frequency.
- Watchdog, UART, Ethernet and process-latency impact are not measured.

---

## 7. Explicitly forbidden

- GPIO40 toggle or SC14448 reset;
- SC14448 firmware upload;
- ADSS/TDM/DMA start;
- pinmux, clock or reset changes;
- analog line/ring;
- any MMIO write;
- loading the module on OEM 4.4.271;
- automatic repeats or a loop over all GPIOs;
- treating K1 as permission for K2;
- treating this runbook as permission to flash or reboot.

K1 is the only stage that can be recommended next.  K2 needs its own decision.
