# FON test-image safety

> **Status: operational document.**
> This is a runbook, not an evidence record.  Hardware facts are maintained in
> `../fon-known-facts.md`; unresolved items in `../fon-open-questions.md`.

Status: **static analysis only; no test image was built or deployed**

This document separates what is known about the optional probe-only test
image from what still requires a real image/config comparison.

## 1. DT delta between normal and probe-only

The normal patch `900` adds the FON node with `status = "disabled"`.
The optional test patch `901` changes only that node:

```diff
-			status = "disabled";
+			status = "okay";
```

No other DT property, node, board, GPIO or clock is changed by `901`.
The production-safe state is `900` only.

## 2. Image/package delta versus production

The exact production image package set, firewall policy, AdGuard,
Knopikson schedule and other services are **not available in this workspace**.
No SSH to the production router was performed.

Therefore the full image-to-image diff is **UNVERIFIED**.  Do not claim that
the test image is safe merely because the DTS delta is small.

Before a bench image is accepted, the operator must capture from both images:

```sh
opkg list-installed > /tmp/packages.txt 2>/dev/null || apk info > /tmp/packages.txt
uci export > /tmp/uci.txt
cat /etc/config/firewall > /tmp/firewall.txt
cat /etc/openwrt_release
cat /proc/cmdline
lsmod
```

and compare them.  The test image must be a deliberate, isolated build, not
the production configuration plus an unknown set of changes.

The test image must not be deployed on the production network segment.  Use
an isolated bench network/recovery path; no WAN access is required for the
probe-only test.

## 3. Kernel configuration symbols

The target SDK kernel `.config` was checked for the options used by this
module:

```text
CONFIG_OF=y
CONFIG_DMA_OF=y
CONFIG_DMA_ENGINE=y
CONFIG_DMA_SHARED_BUFFER=y
CONFIG_COMMON_CLK_QCOM=y
CONFIG_PINCTRL=y
CONFIG_PINCTRL_IPQ4019=y
CONFIG_RESET_CONTROLLER=y
CONFIG_IPQ_GCC_4019=y
CONFIG_MODULES=y
CONFIG_MODULE_UNLOAD=y
```

The module also uses the kernel `of`, `of_address`, `platform`, `dma-mapping`,
`clk`, `reset`, `pinctrl`, `mutex` and `sysfs` APIs.  The target build
resolved all of them through the target `Module.symvers`; `depends=` is empty.

`CONFIG_SND=m` and `CONFIG_SND_SOC=m` are present in the target config, but
the current diagnostic module does **not** register an ALSA card or use ALSA
APIs.  They are not a dependency of this iteration.

`CONFIG_KALLSYMS` was not present in the checked `.config`; this does not
affect the module build or the probe-only lifecycle.  `CONFIG_MODVERSIONS`
and `CONFIG_MODULE_SIG` are disabled in this target.

Confirm the final image's `/proc/config.gz` or build config, not only the SDK
config, before deployment.

## 4. Test-image isolation rules

- No production credentials, keys or private config in the test image.
- No production firewall/AdGuard/Knopikson state copied blindly.
- No automatic `fon_tdm_drv` load.
- No automatic DTS patch `901` in a production build.
- No line/ring hardware connected.
- No DECT UART write or GPIO40 reset.
- Serial or independent recovery must be available.

## 5. Remaining UNVERIFIED

- Exact package/service diff between production and test images.
- Actual image/FIT layout and whether a separate DTB can be loaded without
  flashing.
- Actual production config, kernel command line and loaded modules.
- Actual `/proc/iomem` and `/proc/interrupts` ownership.
- Whether the target image has debugfs mounted for clock/pinctrl dumps.

These must be filled from the real bench image, not inferred from the SDK.
