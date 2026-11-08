# Stage C0+-K — one-shot kernel TLMM clock probe

> **Status: prepared, never executed.**
> This is a procedure, not authorization.  The module has not been loaded or
> triggered.  Do not run any step here without separate operator approval.

Purpose: on the stock OpenWrt image (which has `CONFIG_DEVMEM` disabled), load
a minimal kernel module that is idle after `insmod`, then perform **one**
bounded read-only measurement of one allowed TLMM GPIO.

The module is:

```text
tools/fon-tlmm-clock-probe/kernel/fon_tlmm_probe.c
```

It reads only `GPIO_CFG`/`GPIO_IO` with `readl()`.  It contains no MMIO
writes, no GPIO request, no pinctrl/clock/reset call, no interrupt setup and
no DMA.

---

## 1. Preconditions

| Condition | Requirement |
|---|---|
| Running system | OpenWrt 6.12.112 test image; **not** the OEM 4.4.271 system |
| Kernel release | exactly matches the kernel tree used to build the module |
| Module ABI | `modinfo` vermagic matches `uname -r` |
| Debugfs | `/sys/kernel/debug` mounted |
| FON driver | not loaded; no DMA/reset/firmware activity |
| Analog line | disconnected |
| Power | physical power-cycle available |
| Approval | separate explicit approval for C0+-K |

The C0+-K hardware run is **NO-GO** until that approval is recorded.

Do **not** switch the board from OEM to OpenWrt, do not reflash and do not
RAM-boot as part of this runbook.  If the board is still on OEM 08.25, stop:
the 4.4.271 module cannot be used on that kernel.

---

## 2. Build and artifact check (offline)

Build in a copy of the target kernel tree:

```sh
make -C /path/to/linux-6.12.112 \
     M=$PWD/tools/fon-tlmm-clock-probe/kernel modules
sha256sum tools/fon-tlmm-clock-probe/kernel/fon_tlmm_probe.ko
modinfo tools/fon-tlmm-clock-probe/kernel/fon_tlmm_probe.ko
```

Record:

- source commit;
- `.ko` SHA256;
- `vermagic`;
- kernel release and `uname -r` of the test image.

Copy the exact `.ko` to `/tmp` on the router and compare SHA256 there.  Do not
load a module from an unrecorded build.

---

## 3. Preflight on the router (read-only)

```sh
uname -a
cat /etc/openwrt_release
uname -r

ls -ld /sys/kernel/debug
ls -l /tmp/fon_tlmm_probe.ko
sha256sum /tmp/fon_tlmm_probe.ko
modinfo /tmp/fon_tlmm_probe.ko

lsmod | grep -E 'fon|adss|pcmlink' || true
dmesg | tail -n 80
```

Expected:

- vermagic matches the running kernel;
- no FON/ADSS module is active;
- debugfs is mounted;
- no DMA/reset/firmware action is in progress.

Stop if any check fails.

---

## 4. Load (idle only)

```sh
insmod /tmp/fon_tlmm_probe.ko gpio=22 duration_ms=20
```

The module parameters:

| Parameter | Default | Allowed |
|---|---:|---|
| `gpio` | 22 | 21, 22, 25, 26 |
| `duration_ms` | 20 | 20-50 |
| `expected_hz` | 0 | 0 = derive (8 kHz or 1.024 MHz) |

After load:

```sh
dmesg | tail -n 5
cat /sys/kernel/debug/fon_tlmm_probe
```

Expected:

```text
fon_tlmm_probe: idle; write 1 to trigger one bounded measurement
idle
```

**No measurement has happened yet.**  If the module does anything else at
load, stop and `rmmod`.

---

## 5. MMIO addresses

| GPIO | Signal | `GPIO_CFG` | `GPIO_IO` |
|---:|---|---|---|
| 21 | DCL / BCLK, PINMUX2 | `0x01015000` | `0x01015004` |
| 22 | FSC, PINMUX2 | `0x01016000` | `0x01016004` |
| 25 | DCL / BCLK, PINMUX3 | `0x01019000` | `0x01019004` |
| 26 | FSC, PINMUX3 | `0x0101a000` | `0x0101a004` |

Only a 4 KiB page at `TLMM_BASE + gpio*0x1000` is mapped.  There is no write
to any address.

---

## 6. One-shot trigger

For each selected GPIO, one command, one measurement, then read the result:

```sh
# FSC, PINMUX2
echo 1 > /sys/kernel/debug/fon_tlmm_probe
cat /sys/kernel/debug/fon_tlmm_probe
```

For a different GPIO, unload and reload with the new parameter:

```sh
rmmod fon_tlmm_probe
insmod /tmp/fon_tlmm_probe.ko gpio=26 duration_ms=20
echo 1 > /sys/kernel/debug/fon_tlmm_probe
cat /sys/kernel/debug/fon_tlmm_probe
```

Rules:

- one GPIO per load;
- no automatic repeats;
- do not script a loop over all four pins;
- do not trigger while another process is changing pinmux/GPIO/clock/reset;
- do not use `SCHED_FIFO`, CPU pinning or interrupt disabling;
- 20 ms is the default; 50 ms is the hard maximum;
- writing `1` is an **active** request, even though it is not an MMIO write.

Expected result fields:

```text
gpio=22 cfg=... io=... func=... oe=... input=...
samples=... edges=... elapsed_ns=... sample_rate_hz=... freq_hz=...
status=... cfg_changed=... max_gap_ns=... gap_total_ns=...
gap_count=... segments=... zero_edge_segments=...
min_rate_q=... max_rate_q=... timing_suspect=...
```

---

## 7. Interpretation

| Status | Meaning |
|---|---|
| `FREQUENCY_ESTIMATED` | stable segments, sufficient sampling, frequency within 0.5–2× expected |
| `DETECTED` | transitions seen, but rate/window/frequency is not reliable |
| `STATIC_OBSERVED` | no transitions with sufficient sampling and no significant gap |
| `INCONCLUSIVE` | gap, `CFG` change, unstable segments or insufficient data |
| `ERROR` | parameter or mapping failure |

Even `FREQUENCY_ESTIMATED` does not prove:

- the physical wire to the SC14448;
- the 1.8 V amplitude or signal quality;
- that the SC14448 is out of reset;
- that firmware is loaded;
- that the signal is a valid TDM clock rather than noise.

A `STATIC_OBSERVED` result does not authorize a reset or firmware upload.

---

## 8. Stop conditions

Stop and `rmmod` (or power-cycle if the console is lost) if:

- `insmod` performs or logs a measurement;
- `cfg_changed=1`;
- `timing_suspect=1` and the operator does not accept an inconclusive result;
- kernel `WARNING`, `BUG`, `Oops`, panic, lockdep or refcount complaint;
- console loss, hang or unexpected reboot;
- `/proc/iomem` or pinctrl ownership changes unexpectedly;
- another driver claims the TLMM range or the selected GPIO;
- the module cannot be removed cleanly.

Do not repair a stop condition by writing MMIO, toggling GPIO40, uploading
firmware, changing pinmux or starting DMA.

---

## 9. Unload and recovery

```sh
rmmod fon_tlmm_probe
dmesg | tail -n 20
```

Expected: debugfs node removed, no measurement, no GPIO/clock/reset state
change.

If `rmmod` fails, stop; do not force-unload or patch state.  Power-cycle only
if the documented recovery route permits it.

---

## 10. Explicitly forbidden

- GPIO40 toggle or SC14448 reset;
- SC14448 firmware upload;
- ADSS/TDM/DMA start;
- pinmux, clock or reset changes;
- analog line/ring;
- any MMIO write;
- automatic repeats or long loops;
- loading the module on the OEM 4.4.271 kernel;
- treating this runbook as permission to flash or reboot.

This runbook prepares a hardware review.  It does not grant it.
