# OpenWrt integration

This directory contains the target OpenWrt material for the diagnostic
FRITZ!Box 7530 FON transport.

```text
package/kernel/fon-tdm/Makefile       OpenWrt KernelPackage
package/kernel/fon-tdm/src -> ...     canonical src/fon-driver source symlink
target/linux/ipq40xx/patches-6.12/
  900-arm-dts-ipq4019-fritzbox-7530-fon.patch
dts/fon-tdm-7530-dtc-test.dts         standalone DTC syntax test
```

## Package source

The package `src` entry is a relative symlink to the repository's
`src/fon-driver` directory.  It resolves when this repository's
`openwrt/package` tree is used as an OpenWrt package feed.  If the package is
copied into a separate OpenWrt tree, replace the symlink with a copy of
`src/fon-driver`; `tools/build-fon-openwrt.sh` does this for the SDK test.

## Target SDK build

Tested with the official OpenWrt 25.12.6 ipq40xx/generic SDK:

```sh
SDK_DIR=/path/to/openwrt-sdk-25.12.6-ipq40xx \
sh tools/build-fon-openwrt.sh
```

The script cleans the package build, uses the target kernel tree and
`Module.symvers`, and produces:

```text
.../lib/modules/6.12.112/fon_tdm_drv.ko
.../packages/kmod-fon-tdm-6.12.112-r1.apk
```

OpenWrt 25.12 uses `apk`, not `.ipk`.

## DTS patch

The patch adds a board-specific `avm,fon-tdm` node to
`qcom-ipq4019-fritzbox-7530.dts` with `status = "disabled"`.  It does not
change any other IPQ4019 board.  The target DTS can be enabled only for a
bench test after the resource/clock review.

The standalone DTC test is:

```sh
KERNEL_INCLUDE=<target-kernel>/include \
DTS_BASE_DIR=<directory containing qcom-ipq4019.dtsi> \
DTC=<target-kernel>/scripts/dtc/dtc \
sh tools/build-fon-dts-test.sh
```

## Safety

The package has no automatic module load (`AUTOLOAD` is not set).  The driver
probe performs no MMIO access, no clock/reset enable, and no DMA start.  The
DT node is disabled by default and the line/ring voltage is never controlled.
