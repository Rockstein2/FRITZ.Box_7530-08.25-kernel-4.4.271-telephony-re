# FON build validation

Status: **target kernel module and OpenWrt package built; no hardware load**

This is the validation record for the diagnostic FON TDM module.  The build
used an actual OpenWrt 25.12.6 SDK for `ipq40xx/generic`, not a host-kernel
approximation.

---

## 1. Toolchain and inputs

```text
SDK:
  openwrt-sdk-25.12.6-ipq40xx-generic_gcc-14.3.0_musl_eabi.Linux-x86_64.tar.zst
  SHA-256: 72b2a064190a46b8026e192e29b8ff357dc040850eb3309573124509acbb8a05

Kernel:
  Linux 6.12.112
  target: ipq40xx/generic
  ARCH: arm
  toolchain: arm-openwrt-linux-muslgnueabi-gcc 14.3.0
  package manager: apk-tools 3.0.5 -> .apk output
```

The target kernel was prebuilt inside the SDK, with a real `Module.symvers`.
`CONFIG_MODVERSIONS` and `CONFIG_MODULE_SIG` are disabled in this target
configuration.

---

## 2. Host-side offline tests

```sh
make -C src/fon-driver/tests run
make -C src/fon-firmware/tests run
```

Result:

```text
fon_tdm_test: all tests passed
fon_dma_test: all tests passed
fon_dialog_test: all tests passed
parsed dectfw_firstlevel_441_slow.hex: 629 bytes, 1 blocks
parsed dectfw_secondlevel_441.hex: 54124 bytes, 9 blocks
parsed dectfw_secondlevel_441p2test.hex: 49805 bytes, 8 blocks
```

The `fon_dma_test` checks the descriptor size, cache-aligned stride, next
pointer wrapping, padding zeroing, 28-bit address validation, guard bytes and
state-transition helpers.

The `fon_dialog_test` checks Intel HEX checksums, extended addressing,
contiguous blocks, outer lengths, XOR checksums and boot helpers.  It also
exercises the mockable slow/fast handshakes with an in-memory UART queue.
The real image checks are skipped if the local firmware directory is absent.

KUnit was not added for this iteration: the target SDK has no configured
KUnit runner, and the testable frame/descriptor/state logic is deliberately
kernel-independent.  The same functions are exercised by the userspace tests.

---

## 3. Target OpenWrt module build

The package is at:

```text
openwrt/package/kernel/fon-tdm/
```

Reproducible command, with an extracted SDK:

```sh
SDK_DIR=/path/to/openwrt-sdk-25.12.6-ipq40xx \
    sh tools/build-fon-openwrt.sh
```

The script copies the package into the SDK, points its `src` symlink at the
canonical `src/fon-driver`, cleans the package build and runs:

```sh
make package/fon-tdm/clean
make package/fon-tdm/compile V=s
```

Observed successful build:

```text
CC [M] fon_tdm.o
CC [M] fon_dma.o
CC [M] fon_hw.o
LD [M] fon_tdm_drv.o
MODPOST
CC [M] fon_tdm_drv.mod.o
LD [M] fon_tdm_drv.ko
```

There were **no modpost errors** and no fake symbol exports.  The target
kernel's `Module.symvers` was used.

### 3.1 Output

```text
staging_dir/target-arm_cortex-a7+neon-vfpv4_musl_eabi/
  root-ipq40xx/lib/modules/6.12.112/fon_tdm_drv.ko

bin/targets/ipq40xx/generic/packages/
  kmod-fon-tdm-6.12.112-r1.apk
```

The package manager is `apk`, so the package is `.apk`, not `.ipk`.

### 3.2 ELF and module metadata

```text
ELF 32-bit LSB relocatable, ARM, EABI5 version 1 (SYSV)
BuildID[sha1] present (value depends on the build timestamp)
```

```text
license=GPL
depends=
name=fon_tdm_drv
vermagic=6.12.112 SMP mod_unload ARMv7 p2v8
```

`depends=` is empty.  The unresolved symbol list consists of standard kernel
exports (`_dev_info`, `dma_alloc_attrs`, `mutex_lock`, `platform_*`,
`sysfs_emit`, etc.); there are no unresolved module-private symbols.  The
module has no AVM `.ko` dependency.

`srcversion` is not embedded in this target configuration; that is not a
build error.

---

## 4. DTS validation

The target board change is:

```text
openwrt/target/linux/ipq40xx/patches-6.12/
  900-arm-dts-ipq4019-fritzbox-7530-fon.patch
```

It applies to the OpenWrt 25.12.6 `qcom-ipq4019-fritzbox-7530.dts` and adds a
`status = "disabled"` node, so the module is not activated merely by booting
the DT.

The patch was tested with GNU patch and the DTS tree was compiled with the
target `dtc` after applying the relevant OpenWrt ipq40xx DTS patches
(`100`, `705`, `707`, `710`, `712`):

```sh
patch -p5 < openwrt/target/linux/ipq40xx/patches-6.12/900-arm-dts-ipq4019-fritzbox-7530-fon.patch

cpp -x assembler-with-cpp -D__DTS__ -nostdinc \
    -I<target-kernel>/include -I<dts-dir> \
    <dts-dir>/qcom-ipq4019-fritzbox-7530.dts -o /tmp/7530-pre.dts
<target-kernel>/scripts/dtc/dtc -I dts -O dtb \
    -o /tmp/7530.dtb /tmp/7530-pre.dts
```

Result: `dtc` exit status 0.  The only warning is the upstream
`qcom-ipq4019.dtsi` `/memory` unit-address warning.  The resulting DTB contains:

```text
fon-tdm@7700000
  compatible = "avm,fon-tdm"
  reg = <0x07700000 0x34>, <0x07704000 0x2000>, ...
  reg-names = "adss", "pcm", "mbox_tx", "mbox_rx", "stereo_tx", "stereo_rx"
  qcom,tdm-slots = <8>
  interrupts = <GIC_SPI 156 IRQ_TYPE_LEVEL_HIGH>,
               <GIC_SPI 159 IRQ_TYPE_LEVEL_HIGH>
  status = "disabled"
```

The repository also contains a standalone DTC test:

```sh
KERNEL_INCLUDE=<target-kernel>/include \
DTS_BASE_DIR=<dir-with-qcom-ipq4019.dtsi> \
DTC=<target-kernel>/scripts/dtc/dtc \
sh tools/build-fon-dts-test.sh
```

This is a syntax/regression test, not a substitute for a full OpenWrt image
build.

---

## 5. What was not validated

- The module was **not loaded** on a FRITZ!Box 7530.
- No `probe`, sysfs or MMIO behavior was observed on hardware.
- No full OpenWrt firmware image was built in this workspace.
- The target DTS was compiled as a standalone DTS with OpenWrt DTS patches;
  it was not injected into a complete image build.
- No MBOX DMA start was executed.
- No SC14448 firmware was uploaded.
- No line/ring voltage or GPIO reset was applied.

## 6. Probe-only mode and static analysis

The current module defaults to `probe_only=1`.  In this mode it parses the DT
resources, IRQ and clock/reset/pinctrl *references* without acquiring or
mapping any of them.  It does not call `devm_ioremap_resource`,
`devm_clk_get_optional`, `devm_reset_control_get_optional_exclusive`,
`devm_pinctrl_get`, `dma_alloc_coherent`, `request_irq`, GPIO or firmware
code.  See `docs/fon-resource-audit.md`.

The target build was repeated after this change and remained clean:

```text
CC [M] fon_tdm.o
CC [M] fon_dma.o
CC [M] fon_hw.o
LD [M] fon_tdm_drv.o
MODPOST
LD [M] fon_tdm_drv.ko
```

The target `.apk` is now 7.8 KiB.  The exact BuildID changes with the build
timestamp and is not a functional identifier.

### 6.1 checkpatch

```text
checkpatch.pl --no-tree -f src/fon-driver/*.c src/fon-driver/*.h
```

Result: 0 errors.  The only warnings are the deliberate
`LINUX_VERSION_CODE` guard around the 6.8/6.12 `platform_driver.remove`
signature.  The module is intended to compile in both API environments during
development; the guard is not hiding a warning from the target build.

### 6.2 sparse

The module was checked with `sparse` through the host 6.8 build:

```sh
make -C /lib/modules/$(uname -r)/build      M=$PWD/src/fon-driver CONFIG_FON_TDM=m C=1      CHECK=/path/to/sparse modules
```

Result: `sparse` emitted no diagnostics for `fon_tdm.c`, `fon_dma.c` or
`fon_hw.c`.  This is a host API check; the real target build is the SDK build
above.

### 6.3 Probe-only DTS

The normal patch keeps `status = "disabled"`.  A separate optional patch:

```text
openwrt/test-patches/901-arm-dts-ipq4019-fritzbox-7530-probe-only.patch
```

changes only the FON node to `status = "okay"` for a dedicated test image.
It was applied after `900` and compiled with the target DTC; the resulting DTB
contains the six resources, IRQ 156/159 and `status = "okay"`.

Do not include this optional patch in the production image.

---

## 7. Safety result

```text
probe-only module:        built, no hardware touched
probe-only DT test DTB:   compiled
full MMIO/DMA mode:       NOT READY
hardware test:            not executed
```

The real target `.ko` and `.apk` prove that the code, target kernel headers,
cross compiler, symbol table and packaging path are consistent.  They do not
prove that the hardware configuration is correct.
