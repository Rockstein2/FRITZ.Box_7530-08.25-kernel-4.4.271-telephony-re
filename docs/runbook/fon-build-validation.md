# FON build validation

> **Status: operational document.**
> This is a runbook, not an evidence record.  Hardware facts are maintained in
> `../fon-known-facts.md`; unresolved items in `../fon-open-questions.md`.

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
python mock suite: Ran 40 tests, OK
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

### 3.2 ELF, hash and module metadata

Artifact hash for the runbook:

```text
module sha256:  cd5c05fb408f7f928fd7f6a786a189d22992fe5e12c2c44d9f61fe94c726aff6
module size:    74796 bytes   (built from openwrt-25.12.6-source)
package sha256: 69373c99c93490f5baea6622e716cf62e35ad892104701acfc610450ad49c09b
package size:   8198 bytes
```

The package contains a **stripped** `.ko` (17976 bytes, different SHA-256)
because OpenWrt runs `scripts/strip-kmod.sh` before packaging.  The bench
manifest records the unstripped staging artifact, which is what must be copied
to `/tmp/fon_tdm_drv.ko`.  Do not compare the package member hash with the
manifest hash.

```text
ELF 32-bit LSB relocatable, ARM, EABI5 version 1 (SYSV)
BuildID[sha1] present (value depends on the build timestamp)
```

```text
license:        GPL
depends:
name:           fon_tdm_drv
vermagic:       6.12.112 SMP mod_unload ARMv7 p2v8
parm:           allow_dma:bool
parm:           allow_hw_writes:bool
parm:           allow_mmio_reads:bool
parm:           probe_only:bool
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

The optional `901` patch was checked after `900` in a pristine OpenWrt DTS
git tree:

```text
900 apply:        rc=0
901 apply --check: rc=0
```

See `../../openwrt/test-patches/README.md` for the order and production warning.

The patch was tested with GNU patch and the DTS tree was compiled with the
target `dtc` after applying the relevant OpenWrt ipq40xx DTS patches
(`100`, `705`, `707`, `710`, `712`):

```sh
# from the OpenWrt source root, where the patch path begins with target/
patch -p1 < /path/to/repo/openwrt/target/linux/ipq40xx/patches-6.12/900-arm-dts-ipq4019-fritzbox-7530-fon.patch

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

## 4a. Full-image build (stock initramfs)

A complete OpenWrt 25.12.6 tree was built on this workstation:

```text
tree:    openwrt-25.12.6-source (88 MiB unpacked)
profile: ipq40xx / generic / avm_fritzbox-7530
config:  CONFIG_ALL / CONFIG_ALL_KMODS disabled,
         CONFIG_TARGET_ROOTFS_INITRAMFS=y
command: make -j4 world V=s
result:  EXIT=0
version: r33311-981c978eff
packages in manifest: 148
```

Artifacts (`bin/targets/ipq40xx/generic/`):

| Artifact | Size | SHA-256 |
|---|---|---|
| `openwrt-ipq40xx-generic-avm_fritzbox-7530-initramfs-uImage.itb` | 8 335 848 | `c570f7284c647a50dddd6f10852ae4c857ef01dc3eeeaf72ecd6b9309e832e4f` |
| `openwrt-ipq40xx-generic-avm_fritzbox-7530-squashfs-sysupgrade.bin` | — | see `sha256sums` |
| `u-boot-fritz7530/uboot-fritz7530.bin` | 524 288 | `37faab9c…cffdd1e` (matches upstream) |

FIT contents (parsed from the image itself):

```text
kernel-1   8 316 845 B  lzma   ARM OpenWrt Linux-6.12.112
fdt-1         17 618 B  DTB    model "AVM FRITZ!Box 7530"
                              compatible "avm,fritzbox-7530"
                              fon-tdm node: absent (stock tree)
```

The stock image is smaller than the official release (8 335 848 vs
8 713 764 bytes) because `CONFIG_ALL*` is disabled.

Build-note: the log contains `install-bin-u-boot-fritz75{20,30}] Error 1
(ignored)` entries, yet the resulting `uboot-fritz7530.bin` matches the
upstream hash.  The ignored error concerns re-copying to `bin/`, not the
artifact itself.

## 4b. Full-image build (probe-only test image)

Same tree and toolchain, with the FON package and DT patches `900` + `901`:

```text
config additions:
  CONFIG_PACKAGE_kmod-fon-tdm=y
  CONFIG_PACKAGE_kmod-usb-dwc3 / -qcom / -usb-xhci-hcd =y
  CONFIG_PACKAGE_kmod-usb-storage / -uas =y
  CONFIG_PACKAGE_kmod-fs-ext4, kmod-nls-cp437, kmod-nls-iso8859-1 =y
  CONFIG_PACKAGE_block-mount, blkid, e2fsprogs =y
patches:  900 (FON node, disabled) then 901 (status okay, test image only)
command:  make -j4 world V=s
result:   EXIT=0
```

Artifacts:

| Artifact | Size | SHA-256 |
|---|---|---|
| `openwrt-ipq40xx-generic-avm_fritzbox-7530-initramfs-uImage.itb` | 9 129 136 | `7b06c830c4d34e261e3fd81a8674658ef9f4f54699165c3b5457ec20a24162f4` |
| `openwrt-ipq40xx-generic-avm_fritzbox-7530-squashfs-sysupgrade.bin` | — | `29ff7e2a…` |
| `packages/kmod-fon-tdm-6.12.112-r1.apk` | 8 192 | — |

FIT contents verified by extraction:

```text
kernel-1  9 109 854 B  (lzma)
fdt-1        17 897 B
```

The embedded DTB is byte-identical to the built board DTB:

```text
33398b584c385536349362cd75cb21d3bc554e9cb69d270f39641593f84a6f04
  build_dir/.../image-qcom-ipq4019-fritzbox-7530.dtb
  == extracted FIT fdt-1
```

Decompiled FON node inside the image:

```text
fon-tdm@7700000 {
    compatible = "avm,fon-tdm";
    reg = <0x7700000 0x34 0x7704000 0x2000 0x7708000 0x1000
           0x770e000 0x1000 0x7709000 0x1000 0x770f000 0x1000>;
    reg-names = "adss", "pcm", "mbox_tx", "mbox_rx", "stereo_tx", "stereo_rx";
    qcom,tdm-slots = <0x08>;
    interrupts = <0x00 0x9c 0x04 0x00 0x9f 0x04>;   /* SPI 156, 159 */
    interrupt-names = "mbox0", "mbox3";
    status = "okay";
};
```

Driver and USB support present in the initramfs (`initramfs_data.cpio`):

```text
lib/modules/6.12.112/fon_tdm_drv.ko
etc/modules.d/30-fs-ext4
etc/modules.d/53-usb-dwc3-qcom
etc/modules.d/54-usb-dwc3
etc/modules.d/54-usb-xhci-hcd
etc/modules.d/usb-storage
etc/modules.d/usb-storage-uas
```

The driver ships as a **loadable module**, so `bench/load-probe-only.sh` and
`bench/unload.sh` apply unchanged.

Note: the embedded kernel's build timestamp is inherited from the stock build
(`Wed Oct 17 23:45:38 2026`) because the DTS change only rebuilds the DTB and
relinks the FIT; the kernel binary itself is unchanged.

## 5. What was not validated

- The module was **not loaded** on a FRITZ!Box 7530.
- No `probe`, sysfs or MMIO behavior was observed on hardware.
- The stock image was **built but never booted**; boot behaviour on the bench
  remains `UNVERIFIED`.
- No MBOX DMA start was executed.
- No SC14448 firmware was uploaded.
- No line/ring voltage or GPIO reset was applied.

## 6. Probe-only mode and static analysis

The current module defaults to `probe_only=1`.  In this mode it parses the DT
resources, IRQ and clock/reset/pinctrl *references* without acquiring or
mapping any of them.  It does not call `devm_ioremap_resource`,
`devm_clk_get_optional`, `devm_reset_control_get_optional_exclusive`,
`devm_pinctrl_get`, `dma_alloc_coherent`, `request_irq`, GPIO or firmware
code.  See `../history/fon-resource-audit.md`.

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

### 6.0 Probe-only IRQ handling

Probe-only no longer calls `platform_get_irq_optional()`.  On Linux 6.12,
`of_irq_get()` → `irq_create_of_mapping()` → `irq_create_fwspec_mapping()`
can allocate a Linux virq mapping and store the DT trigger type in the irq
domain.  Probe-only parses the raw specifier with `of_irq_parse_one()` and
reports:

```text
irq_spi=156/159   raw DT GIC SPI
irq_intid=188/191 GIC INTID (SPI + 32)
irq=-1            no Linux virq requested
```

Full mode keeps `platform_get_irq_optional()`.

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

### 6.2b Bench-script tests

`sh bench/tests/run.sh` runs the loader/unload scripts against a fake root
and stub commands (`insmod`, `rmmod`, `modinfo`, `lsmod`, ...).  No real
module operation is possible.  Last result:

```text
32 passed, 0 failed
```

Covers no `--yes`, wrong SHA, wrong board/compatible/kernel/module, the exact
DT model string (`AVM FRITZ!Box 7530`, with `!`, and the near-miss
`FRITZ.Box` spelling must be refused), missing or
disabled FON node, already loaded, insmod failure, bind failure, wrong stage,
changed `/proc/iomem`, output-dir reuse, unload failure, leftover sysfs, and
cleanup after failed verification.  Every pre-load refusal proves the
`insmod` stub was not invoked.

`sh tools/tests/prepare-fon-tree.sh` runs the DT preparation script against
temporary OpenWrt-like trees.  Last result:

```text
13 passed, 0 failed
```

Covers disabled/okay states, symlink correctness, no extra DTS changes,
idempotent re-runs, invalid `FON_PROBE_ONLY`, and refusal to reverse an
already-probe tree.  `PRISTINE_DTS=` must point at an unpatched board DTS so
the test is independent of the state of the host OpenWrt tree.

`sh tools/tests/prepare-fon-image.sh` tests the DTB preparation script against
isolated temporary trees with a real prepared kernel include tree and `dtc`.
It requires `PRISTINE_DTS`, `KERNEL_INCLUDE` and `DTC`.  Last result:

```text
10 passed, 0 failed
```

Covers normal/probe DTB generation, the exact `status` value in each, the
recorded SHA-256 file, the normal-vs-probe node diff being only the status
line, refusal of an invalid `FON_PROBE_ONLY`, and refusal of a missing `dtc`.

### 6.3 Probe-only DTS

The normal patch keeps `status = "disabled"`.  A separate optional patch:

```text
openwrt/test-patches/901-arm-dts-ipq4019-fritzbox-7530-probe-only.patch
```

changes only the FON node to `status = "okay"` for a dedicated test image.
Both patches were regenerated against the pristine board DTS and applied in
order to the full OpenWrt 25.12.6 tree; the target DTC then compiled the board
DTS.  Resulting DTBs (`tools/prepare-fon-image.sh`, SHA-256):

```text
normal  qcom-ipq4019-fritzbox-7530-normal.dtb  9023d18e6a50c65faa5a2c3424f07a861154c651268da12a30663b7406d986c2
probe   qcom-ipq4019-fritzbox-7530-probe.dtb   e2223064178199c19bd4dec918d22d4d203d85e6e15bdeee202aac3f4df0428b
```

Both contain the six resources and `interrupts = <GIC_SPI 156 ...>, <GIC_SPI
159 ...>`; the decompiled FON nodes differ only in the `status` line.

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
