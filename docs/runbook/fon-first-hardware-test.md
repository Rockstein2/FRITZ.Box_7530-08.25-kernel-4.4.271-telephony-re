# First safe hardware test — FRITZ!Box 7530 FON probe-only

> **Status: operational document.**
> This is a runbook, not an evidence record.  Hardware facts are maintained in
> `../fon-known-facts.md`; unresolved items in `../fon-open-questions.md`.

Status: **prepared, not executed**

This test loads the module with `probe_only=1` (the default), verifies the
platform device and driver lifecycle, and performs no MMIO, clock, reset, DMA,
GPIO40, firmware or line/ring operation.

The self-contained bench kit is in `bench/` and is the preferred way to run
this test.  Copy the exact `.ko` plus `bench/*.sh` to the test router; the
collector is read-only and the load/unload tools refuse without `--yes`.
Read `../history/fon-resource-audit.md` and `fon-recovery-plan.md` first.  The
expected verdict is:

```text
probe-only: GO
full MMIO/DMA: NOT READY
line/ring/firmware: NOT READY
```

---

## 0. Preconditions

Do not begin without:

- serial console or another independent recovery path;
- a known-good FRITZ!Box 7530 OpenWrt image and its recovery/backup procedure;
- physical access and controlled power;
- a copy of the exact built `fon_tdm_drv.ko` and its `modinfo`;
- confirmation that the test image contains the optional probe-only DTS
  configuration (see section 1);
- no expectation that FON audio, hook, ringing or line feed will work.

The normal OpenWrt image must keep the FON node `status = "disabled"`.  The
optional test patch is separate:

```text
openwrt/test-patches/
  901-arm-dts-ipq4019-fritzbox-7530-probe-only.patch
```

It changes only the FON node status from `disabled` to `okay` and is intended
for a **separate test image**, not the normal build.

Do not apply it to a working production image without a separate decision and
a tested recovery route.

---

## 1. Test-image / DTB preparation

### Normal image

```text
openwrt/target/linux/ipq40xx/patches-6.12/
  900-arm-dts-ipq4019-fritzbox-7530-fon.patch
```

`900` adds the node with `status = "disabled"`.  The module can be loaded in
this image, but it will not bind to a platform device.  This is a safe
module-load and ABI test only.

### Probe-only test image

Build a separate test tree with `900` first and the optional `901` patch
second:

```sh
# in the OpenWrt source tree, for the test build only
patch -p1 < /path/to/900-arm-dts-ipq4019-fritzbox-7530-fon.patch
patch -p1 < /path/to/901-arm-dts-ipq4019-fritzbox-7530-probe-only.patch
```

Then rebuild the target DTB/image with the normal OpenWrt build process.  Do
not install the resulting image automatically.

There is no confirmed general-purpose runtime DT overlay mechanism on this
IPQ4019 OpenWrt target.  If the bootloader/FIT layout does not support a
separate test DTB, treat the test image installation as a **flash operation**
and use the established recovery procedure.  Do not modify the bootloader.

For syntax-only validation of the node:

```sh
KERNEL_INCLUDE=<target-kernel>/include \
DTS_BASE_DIR=<dir-with-qcom-ipq4019.dtsi> \
DTC=<target-kernel>/scripts/dtc/dtc \
sh tools/build-fon-dts-test.sh
```

The test DTS is deliberately independent of the full image build.

---

## 2. Stage A — collect information (read-only)

Run as root, but only use read-only commands.  Save the output:

Use the portable collector; busybox ash has no process substitution:

```sh
sh bench/collect-stage-a.sh /tmp/fon-stage-a
```

It writes a snapshot directory and tarball without changing hardware state.

### A.1 System and kernel

```sh
uname -a
cat /etc/openwrt_release
cat /proc/cmdline
cat /sys/firmware/devicetree/base/model 2>/dev/null || cat /proc/device-tree/model
```

### A.2 FON DT node

```sh
find /sys/firmware/devicetree/base -maxdepth 2 -iname '*fon*' -print 2>/dev/null
find /proc/device-tree -maxdepth 2 -iname '*fon*' -print 2>/dev/null

tr -d '\0' < /sys/firmware/devicetree/base/soc/fon-tdm@7700000/status 2>/dev/null || true
tr -d '\0' < /proc/device-tree/soc/fon-tdm@7700000/status 2>/dev/null || true
```

Expected in the normal image:

```text
disabled
```

Expected in the probe-only test image:

```text
okay
```

### A.3 Memory map

```sh
grep -E '0770[0-9a-f]{3}|78af000|audio|mbox|stereo' /proc/iomem
cat /proc/iomem > /tmp/fon-test/iomem-before.txt
```

Record whether any of these ranges are already owned:

```text
0x07700000
0x07704000
0x07708000
0x07709000
0x0770e000
0x0770f000
0x078af000
```

Do not continue to full mode if any range is already owned by another driver.

### A.4 Interrupts

```sh
cat /proc/interrupts
grep -E '(^|[^0-9])(156|159)([^0-9]|$)' /proc/interrupts || true
```

The FON IRQ may not appear before the module requests it; probe-only does not
request it.  The UART IRQ 107 may appear as the console.

### A.5 Clocks and pinctrl

```sh
cat /sys/kernel/debug/clk/clk_summary 2>/dev/null | head -n 120
find /sys/kernel/debug/pinctrl -maxdepth 2 -type f -print 2>/dev/null
```

If debugfs is not mounted, do not mount/change anything during the test; note
that the information is unavailable.

### A.6 Console / UART

```sh
cat /proc/consoles
ls -l /dev/ttyMSM* /dev/ttyS* 2>/dev/null
cat /proc/tty/driver/* 2>/dev/null | head -n 80
```

The DECT/console UART is at `0x078af000` with GPIO16/17.  Do not stop the
console and do not reset GPIO40 in this test.

### A.7 dmesg baseline

```sh
dmesg -T | tail -n 200
```

Save it.  Any later `WARNING`, `BUG`, `Oops`, lockdep or driver-core complaint
is a stop condition.

Expected Stage A: no changes to hardware state.

---

## 3. Stage B — module probe-only lifecycle

### B.1 Verify the artifact

```sh
sha256sum /tmp/fon_tdm_drv.ko
modinfo /tmp/fon_tdm_drv.ko
file /tmp/fon_tdm_drv.ko
```

Expected hash for this build:

```text
b867b8c5e362c397bc2ce5f8120cfc069d9eacd09dae2534e6343dc5dcdad870
```

The hash must be regenerated and re-recorded whenever the source changes.
Expected metadata:

```text
vermagic=6.12.112 SMP mod_unload ARMv7 p2v8
depends=
license=GPL
ELF 32-bit LSB relocatable, ARM, EABI5
```

The exact SHA-256 must match the artifact recorded by the build.  `depends=`
must be empty.

### B.2 Load with probe-only

```sh
insmod /tmp/fon_tdm_drv.ko probe_only=1
dmesg -T | tail -n 100
```

Expected dmesg contains:

```text
probe-only: resources=0x3f irq_spi=156/159 irq_intid=188/191 clock_refs=0 reset_refs=0 pinctrl_ref=0 dt_overlap=0
FON probe-only ready; no MMIO/clock/reset/IRQ/DMA access
```

`resources=0x3f` means all six named resources (bits 0–5) are described by
the test DTS.  `irq_spi=156/159` is the raw DT specifier;
`irq_intid=188/191` is GIC INTID (SPI + 32).  **Probe-only does not request a
Linux virq**, so `diagnostics` prints `irq=-1`.  Do not substitute 188 for an
unknown runtime virq.

If the normal disabled image is used, no `probe-only` probe message appears;
that is expected because the device is disabled.  In that image, only module
load/unload and ABI checks are possible.

### B.3 Locate and inspect the device

```sh
DEV=$(find /sys/bus/platform/devices -maxdepth 1 -name '*fon*' -print -quit)
echo "DEV=$DEV"
ls -la "$DEV"
cat "$DEV/stage"
cat "$DEV/diagnostics"
```

Expected `stage`:

```text
0x23
```

Expected `diagnostics`:

```text
mode=probe-only
state=1
diag_valid=0
stage=0x23
resource_mask=0x3f
dt_overlap=0
clock_refs=0
reset_refs=0
pinctrl_ref=0
slots=8
resource[0]=adss start=0x7700000 end=0x7700033
resource[1]=pcm start=0x7704000 end=0x7705fff
resource[2]=mbox_tx start=0x7708000 end=0x7708fff
resource[3]=mbox_rx start=0x770e000 end=0x770efff
resource[4]=stereo_tx start=0x7709000 end=0x7709fff
resource[5]=stereo_rx start=0x770f000 end=0x770ffff
adss_tx_slots=0
adss_rx_slots=0
irq_spi=156/159
irq_intid=188/191
irq=-1
clk_present=0
reset_present=0
pinctrl_present=0
audio_mode=0x00000000
tdm_ctrl=0x00000000
clk_ctrl=0x00000000
i2s_rst=0x00000000
stereo_tx_cfg=0x00000000
stereo_rx_cfg=0x00000000
fon_ctrl_slot=5
fon_ctrl_offset=0xa
dma_prepared=0
dma_started=0
```

`irq=-1` is intentional: probe-only parses the raw DT specifier with
`of_irq_parse_one()` and never calls `platform_get_irq_optional()`.  That
call would create a Linux IRQ mapping and could set the domain trigger type.
The Linux virq exists only in full mode and must be read at runtime; it may
not exist at all in probe-only.

The register fields remain zero because no `diag_refresh` was issued.  Do not
write to `diag_refresh`, `dma_prepare` or `dma_start` in this test.

### B.4 Confirm no memory claim or hardware access

```sh
cat /proc/iomem > /tmp/fon-test/iomem-after.txt
diff -u /tmp/fon-test/iomem-before.txt /tmp/fon-test/iomem-after.txt || true
dmesg -T | tail -n 80
```

Probe-only must not create an iomem claim.  If `/proc/iomem` changes, stop.

Also check that no unexpected GPIO/clock state changed:

```sh
cat /sys/kernel/debug/clk/clk_summary 2>/dev/null | head -n 120
cat /proc/interrupts | head -n 80
```

### B.5 Unload and verify cleanup

```sh
rmmod fon_tdm_drv
dmesg -T | tail -n 100
DEV=$(find /sys/bus/platform/devices -maxdepth 1 -name '*fon*' -print -quit)
ls -la "$DEV" 2>/dev/null || true
ls "$DEV"/driver 2>/dev/null || true
```

Expected: module unload succeeds; the driver's sysfs attributes are gone; no
`WARNING`, `BUG`, `Oops`, double-free, refcount or lockdep message appears.
The platform device node may remain, but it must have no bound FON driver.

### B.6 Reload / unload cycle

Repeat twice:

```sh
insmod /tmp/fon_tdm_drv.ko probe_only=1
dmesg -T | tail -n 40
rmmod fon_tdm_drv
dmesg -T | tail -n 40
```

Expected: no failures, no leaked resources, same probe-only result.

### B.7 Do not do

Do not run any of the following in the first test:

```text
echo 1 > $DEV/diag_refresh
echo 1 > $DEV/dma_prepare
echo 1 > $DEV/dma_start
insmod ... probe_only=0
```

No GPIO40 reset, no firmware upload, no DMA, no line/ring.

---

## 4. Stage C — stop criteria

Abort immediately and restore/recover on any of:

- `WARNING`, `BUG`, `Oops`, `panic`, lockdep or refcount complaint in dmesg;
- any MMIO region conflict or unexpected `/proc/iomem` change;
- clock/reset/pinctrl error;
- Ethernet or Wi-Fi instability;
- unexpected GPIO state change;
- console/UART disruption;
- `rmmod` failure, module refcount leak, sysfs callback after remove;
- inability to reload or reach the shell.

After a failure:

1. disconnect the analog line;
2. do not run further driver operations;
3. preserve dmesg and `/proc/iomem` output;
4. reboot via the serial console;
5. if the test image is unbootable, use the known-good recovery path and
   bootloader/initramfs procedure;
6. do not flash, restore, or modify the bootloader without a separate review.

Do not attempt to “recover” by writing arbitrary registers or resetting
GPIO40.

---

## 5. Expected final result

```text
module ABI OK
probe-only binds and reports six DT resources
no MMIO mapping or claim
no clock/reset/pinctrl acquisition
no DMA
no UART/GPIO/firmware access
clean unload and reload
```

This proves only the platform/DT/module lifecycle.  It does not prove that the
FON hardware is operational, that the clocks are correct, or that SC14448 is
running.

Next possible stage after a successful probe-only report: a separately
reviewed read-only clock/reset/MMIO diagnostic, with `probe_only=0` and
`diag_refresh`, not DMA or line control.
