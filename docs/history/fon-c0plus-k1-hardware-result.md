# FON-C0+-K1 hardware result

> **Status: BLOCKED — hardware not touched after the stop instruction.**
> K1-HARDWARE was not run.  No `insmod`, no debugfs write/read, no `rmmod`, no
> reboot, no `sysupgrade`, no NAND write and no TDM measurement occurred.

Baseline commit: `c0cfc6b2c350b316b6b518d539bee5b8e73cc4b0`.
Session date: 2026-11-08.

---

## 1. Result summary

| Item | Result |
|---|---|
| K1-PREFLIGHT offline build | **PASS** |
| Artifact SHA256 matches prior record | **PASS** |
| ABI/vermagic check | **PASS (offline)** |
| K1-HARDWARE | **BLOCKED / NOT RUN** |
| K2 one-shot measurement | **BLOCKED / NOT RUN** |
| Hardware in use by other operators | **yes — stop requested** |
| Explicit K1-HARDWARE approval | **not present** |

A read-only OS query was made before the operator stopped hardware access:
it reported OpenWrt 25.12.6 `r33311-981c978eff`, Linux `6.12.112`.  That is
recorded only as context.  No further router access was made after the stop
instruction.

## 2. Offline artifact

Rebuilt from the exact current commit against the 6.12.112 tree:

```text
source commit: c0cfc6b2c350b316b6b518d539bee5b8e73cc4b0
kernel tree:   openwrt-25.12.6-source/.../linux-6.12.112
toolchain:     OpenWrt GCC 14.3.0 r33311-981c978eff
size:          53248 bytes
sha256:        31173cc9eacf34c8487442cc1fd89270d3b48067fead164301b917ed79312a60
vermagic:      6.12.112 SMP mod_unload ARMv7 p2v8
depends:       empty
```

The rebuilt hash matches the prior build record.  The artifact is outside Git:

```text
/home/rck/Downloads/OpenWrt7530/builds/c0plus-k1/fon_tlmm_probe.ko
```

with `SHA256SUMS`, `modinfo.txt` and `undefined-symbols.txt` beside it.

Kernel config relevant to K1:

```text
CONFIG_MODULES=y
CONFIG_MODULE_UNLOAD=y
CONFIG_DEBUG_FS=y
CONFIG_DEBUG_FS_ALLOW_ALL=y
# CONFIG_MODVERSIONS is not set
# CONFIG_MODULE_SIG is not set
```

`CONFIG_MODVERSIONS` being off means vermagic is necessary but not complete
ABI proof.  K1 would still have to compare the exact running kernel and
`insmod` result.

## 3. What was not executed

The following K1-HARDWARE commands were **not** run:

```text
insmod /tmp/fon_tlmm_probe.ko gpio=22 duration_ms=20
cat /sys/kernel/debug/fon_tlmm_probe
rmmod fon_tlmm_probe
echo 1 > /sys/kernel/debug/fon_tlmm_probe
```

No measurement output exists.  There is no PASS claim for load/unload,
debugfs, module cleanup, pinctrl coexistence or MMIO mapping.

## 4. GO / NO-GO

| Stage | Decision |
|---|---|
| K1-PREFLIGHT | **GO** from the offline artifact/ABI side |
| K1-HARDWARE now | **NO-GO** — hardware in use; no explicit approval |
| K2 now | **NO-GO** — blocked by K1 |
| CONFIG_DEVMEM rebuild | **not needed / not recommended** |
| DMA/reset/firmware | **NO-GO** |

K1 can be reconsidered only when:

1. the hardware is released by the other operators;
2. the running system is confirmed OpenWrt 6.12.112;
3. the exact module SHA256 and ABI are rechecked;
4. a separate explicit K1-HARDWARE approval is recorded.

K1 still would not prove `ioremap()`/MMIO safety, because K2 is the first
stage that maps TLMM.  K2 remains a separate decision after K1 PASS.

## 5. Files

```text
docs/history/fon-c0plus-k1-hardware-result.md
docs/history/fon-c0plus-kernel-build-report.md
docs/history/fon-c0plus-kernel-safety-review.md
docs/runbook/fon-stage-c0plus-kernel-probe.md
```

Raw device-specific logs, if any are later collected, belong under the
external evidence area, not in this public report.
