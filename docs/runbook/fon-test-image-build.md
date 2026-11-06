# FON probe-only test-image preparation

> **Status: operational document.**
> This is a runbook, not an evidence record.  Hardware facts are maintained in
> `../fon-known-facts.md`; unresolved items in `../fon-open-questions.md`.

Status: **DTB preparation verified offline; no full firmware image was built,
nothing was flashed**

This document describes how the optional probe-only test image is derived from
the OpenWrt 25.12.6 `avm_fritzbox-7530` target, what has been verified, and
what remains `UNVERIFIED` until a real image is built and booted on the bench.

---

## 1. What the test image changes

Production-safe (default) and probe-only images differ by exactly one DT
value:

```diff
-			status = "disabled";
+			status = "okay";
```

That is patch `901`, applied after `900`.  Everything else is the normal
OpenWrt 25.12.6 `avm_fritzbox-7530` build.

The test image must not be deployed on the production network.  See
`fon-test-image-safety.md`.

---

## 2. Preparation command

```sh
OPENWRT_DIR=/path/to/openwrt-25.12.6-source \
OUT_DIR=/tmp/opencode/fon-dtb \
FON_PROBE_ONLY=1 \
    sh tools/prepare-fon-image.sh
```

The script:

1. refuses invalid `FON_PROBE_ONLY` values;
2. installs the package and applies `900` then `901` idempotently (never
   reverse-applying);
3. locates a kernel include tree (`KERNEL_INCLUDE=...` override supported) and
   a `dtc` (`DTC=...` override supported);
4. compiles the **actual board DTS** to a DTB;
5. records the DTB SHA-256 and the decompiled FON node.

It does **not** build a firmware image and never flashes anything.

It was run against the full OpenWrt 25.12.6 tree with the target kernel
prepared (`make target/linux/prepare`).  Recorded results:

```text
FON_PROBE_ONLY=0  fritzbox-7530-normal.dtb  9023d18e6a50c65faa5a2c3424f07a861154c651268da12a30663b7406d986c2
FON_PROBE_ONLY=1  fritzbox-7530-probe.dtb   e2223064178199c19bd4dec918d22d4d203d85e6e15bdeee202aac3f4df0428b
```

The decompiled FON nodes differ only in `status`.

### 2.1 Why a prepared kernel tree is required

A pristine OpenWrt source tree does not contain
`arch/arm/boot/dts/qcom/qcom-ipq4019.dtsi`; that file comes from the kernel
tree and only exists after the target kernel is prepared and its OpenWrt DTS
patches (`100`, `705`, `707`, `710`, `712`) are applied.  On a source-only
tree the script therefore stops with a clear error.

The practical options are:

- point `KERNEL_INCLUDE` at an already prepared target kernel (for example the
  kernel tree produced by `tools/build-fon-openwrt.sh`, or the
  `build_dir/target-*/linux-ipq40xx_generic/linux-6.12.*/include` of the full
  tree after `make target/linux/prepare`), or
- run the normal target preparation first and let the script find the
  generated include tree.

`dtc` from `device-tree-compiler` 1.7.0 was used; the kernel's own `dtc` is
not built by target preparation alone, so `DTC=` is needed unless the host
tool is installed.

---

## 3. Verified offline

Using the OpenWrt 25.12.6 SDK kernel headers together with the OpenWrt
ipq40xx DTS patches:

```text
normal:     dtc exit 0, fon-tdm@7700000 status = "disabled"
            interrupts = <0x00 0x9c 0x04 0x00 0x9f 0x04>
probe-only: dtc exit 0, fon-tdm@7700000 status = "okay"
            interrupts = <0x00 0x9c 0x04 0x00 0x9f 0x04>
```

Only the upstream `/memory` unit-address warning appears.  The FON node is the
only DT delta between the two DTBs.

---

## 4. Full image build (not performed)

The target profile is the standard one:

```text
target:    ipq40xx
subtarget: generic
device:    avm_fritzbox-7530
package:   kmod-fon-tdm
```

A full build needs a complete toolchain and network access for source
downloads, and produces a firmware image under `bin/targets/ipq40xx/generic/`.
With `900` and then `901` already applied to the tree, the resulting image
would carry the probe-only DTB.

`UNVERIFIED` until an image is actually built:

- that the final FIT contains the probe-only DTB rather than a stale one;
- the image size and SHA-256;
- that the bootloader accepts it on this board;
- that the kernel boots with the FON node enabled;
- that `kmod-fon-tdm` is installed in that image.

No probe-only firmware image exists yet, and no image hash can be recorded.

---

## 5. Installing the test image

Do not install it from this repository.  Follow `fon-recovery-plan.md`:
the rollback path must be verified on the bench first, using the currently
installed OpenWrt image.

The recovery procedure for this specific FRITZ!Box 7530/OpenWrt combination
remains `UNVERIFIED`.
