# Porting the FON transport to Linux 6.12 / OpenWrt 25.12

> **Status: historical analysis.**
> This document records the reasoning and evidence as of the date it was
> written.  Some of its `UNKNOWN` / `UNVERIFIED` markers have since been
> answered.
> - Current confirmed facts: `../fon-known-facts.md`
> - Current open questions: `../fon-open-questions.md`
> - This file is kept for the reasoning trail, not as a status report.

Status: **target OpenWrt SDK module built; full OpenWrt image and hardware
test not performed**

This document answers what exists in Linux 6.12, what must be ported, and how
the minimal FON transport avoids fighting existing audio/DMA drivers.

The exact hardware parameters are in `fon-tdm-hardware.md`.

---

## 1. Target facts

OpenWrt 25.12.6 uses Linux 6.12 for the `ipq40xx` target:

```text
target/linux/ipq40xx/Makefile:
  BOARD := ipq40xx
  KERNEL_PATCHVER := 6.12
  KERNELNAME := zImage Image dtbs
```

The target configuration at `target/linux/ipq40xx/config-6.12` contains:

```text
CONFIG_ARCH_QCOM=y
CONFIG_IPQ_GCC_4019=y
CONFIG_PINCTRL_IPQ4019=y
CONFIG_RESET_CONTROLLER=y
CONFIG_QCOM_BAM_DMA=y
CONFIG_DMA_OF=y
CONFIG_DMA_SHARED_BUFFER=y
CONFIG_OF=y
```

It contains **no** `CONFIG_SND*` setting, no QCA ADSS, no IPQ4019 PCM/TDM
audio driver, and no `qca,ipq4019-mbox` audio driver.

A full OpenWrt image build tree was not used; the official target SDK was
used for the module/package build.  The statements above are based on the
published v25.12.6 target Makefile/config and the SDK kernel tree; they are
not a substitute for a complete image build.

---

## 2. What Linux 6.12 already provides

| Component | Linux 6.12 mainline | Suitable for FON? |
|---|---|---|
| `sound/soc/qcom/` | LPASS/QDSP6 (APQ8016, APQ8096, SC7180, SC7280, q6*) | No.  These are DSP/LPASS paths, not IPQ4019 ADSS. |
| `qca,ipq4019-tdm` / `qca,ipq4019-pcm` | absent | No.  AVM out-of-tree only. |
| ADSS/PCM/MBOX audio registers | absent | No.  Must be implemented or ported. |
| `qcom,bam-dma` | present (`CONFIG_QCOM_BAM_DMA=y`) | No.  ADSS MBOX has its own descriptor engine; BAM is a different block. |
| GCC IPQ4019 reset | `gcc-ipq4019` has audio reset bits in mainline | Partly.  The AVM `adcc` audio clock provider is not mainline. |
| `pinctrl-ipq4019` | present | Yes for pinmux, but the FON pin functions need a correct DT state. |
| `qcom,smem`, SCM, NVMEM | present | Not a replacement for AVM's `hw_config` table. |
| ALSA SoC core | present if `CONFIG_SND_SOC` is enabled | No existing IPQ4019 ADSS CPU DAI/card. |

Conclusion: there is **no drop-in ALSA SoC backend** for this hardware in
Linux 6.12.  A port or a clean minimal transport is required.

---

## 3. Port options

### Option A — port the AVM GPL ADSS stack

Port `ipq-adss-avm.c` (about 2,900 lines), `ipq-avm.c`, `ipq-adss.h`, and the
out-of-tree ADCC clock/reset/DTS pieces into a new `sound/soc/qcom/ipq/`
directory.

Advantages:

- preserves the complete ADSS register sequence and the vendor MBOX DMA code;
- provides a known starting point for ALSA/DAI integration;
- the source is GPL-compatible and can be modified and redistributed.

Costs and risks:

- it is a Linux 4.4 vendor driver with AVM-specific globals, FIQ/IPI helpers
  and board-data lookups;
- it depends on the AVM ADCC clock provider, which is absent from mainline
  6.12/OpenWrt;
- it needs the AVM `hw_config` table, GPIO and `avm_event` APIs replaced;
- its interrupt/DMA locking model needs a careful 6.12 review;
- it is much larger than the first transport milestone.

This is the right long-term backend if full ALSA telephony is required.

### Option B — minimal raw ADSS/MBOX transport (this repository)

Implement only the proven transport in `src/fon-driver/`:

- map ADSS/PCM/MBOX/STEREO resources from DT;
- keep the 16-byte, 8-slot, 16-bit frame format;
- encode/decode the control/status slot offline;
- allocate 16-descriptor, 512-byte ping-pong rings;
- expose read-only diagnostics;
- do not start DMA, clocks, reset, or line voltage automatically.

Advantages:

- small, reviewable, and independent of the proprietary `pcmlink.ko`;
- avoids creating a second DMA controller driver;
- provides a testable base for later ALSA/DAHDI work;
- can be built as an external module before touching an OpenWrt image.

Limitation: it does not yet provide a user-visible audio device or a complete
MBOX start path.  That is intentional; the missing semantics are listed in the
final report.

### Option C — DAHDI first

Not recommended for this stage.  DAHDI would still require the same ADSS/TDM/
MBOX backend plus a DAHDI span/channel layer.  It does not remove the hardware
dependency.

**Recommendation:** Option B for this iteration, then reuse its verified frame
and ring code when porting Option A (or a clean ALSA DAI) later.

---

## 4. Linux 4.4 → 6.12 API port notes

The AVM driver is not directly compilable on 6.12.  The important changes are:

| AVM 4.4 pattern | Linux 6.12 approach |
|---|---|
| `struct platform_driver.remove` returning `int` | `void` since the 6.11 platform-driver change.  The diagnostic driver uses a version guard for 6.8/6.12 compatibility. |
| `dmac_flush_range()` / `dmac_inv_range()` | use `dma_wmb()`, `dma_sync_single_for_cpu/device()`, or coherent DMA APIs.  The old ARM cache helpers are not portable. |
| `avm_rte_local_irq_save()` / FIQ IPI helpers | use normal IRQ/threaded IRQ or a documented FIQ implementation; do not copy AVM's IPI layer. |
| global `mbox_dma[]` / `adss_audio_local_base` | per-device state in `struct fon_tdm_dev`; no cross-driver globals. |
| AVM `hw_config` table lookups | device tree properties/resources and standard GPIO/pinctrl APIs. |
| `dakota_gpio_ctrl()` / AVM GPIO register helpers | `gpiod_*`, pinctrl states, or a dedicated pin controller. |
| `_clk_set()` wrapper | `clk_set_rate()` plus `clk_prepare_enable()` / `clk_disable_unprepare()` with explicit ownership. |
| `request_resource()` and fixed MMIO | `platform_get_resource_byname()` + `devm_ioremap_resource()`; no hardcoded virtual addresses. |
| `register_sysctl_table()` debug interface | debugfs/sysfs attributes; the diagnostic driver uses sysfs. |
| `is_IPQ4019()` | `of_machine_is_compatible()` or DT match data. |
| AVM `PowerManagment*`, `avm_event_*` | runtime PM/notifier/uevent only after the transport is stable; not needed for first probe. |
| `__memzero`, `arm_delay_ops` | standard `memset`, `udelay`/`fsleep`. |
| `of_node_get()` / manual node lifetime | `of_device_get_match_data()` and devm-managed resources. |

The diagnostic driver deliberately uses only APIs available in 6.8 and 6.12:
`platform_driver`, `devm_ioremap_resource`, `devm_clk_get_optional`,
`devm_reset_control_get_optional_exclusive`, `devm_pinctrl_get`,
`dma_alloc_coherent`, `sysfs_emit_at`, and `devm_device_add_group`.

### 4.1 ADCC clock dependency

Mainline `gcc-ipq4019.c` provides GCC audio gates and `AUDIO_CLK_SRC`, but not
the AVM `adcc` clock provider used by the DTS names:

```text
ADCC_TXB_CLK_SRC, ADCC_TXM_CLK_SRC,
ADCC_RXB_CLK_SRC, ADCC_RXM_CLK_SRC,
ADCC_PCM_CLK_SRC
```

Those names come from the AVM GPL DTS/clock driver, not mainline.  A full
master-mode port therefore also needs the ADCC clock provider.  The diagnostic
driver treats all four clocks as optional and never enables them, so it can
probe without them and report what is missing.

### 4.2 DMA API

ADSS MBOX is not a BAM channel and has no standard `dmaengine` slave binding.
The correct minimal approach is:

- `dma_set_mask_and_coherent(dev, DMA_BIT_MASK(28))`;
- `dma_alloc_coherent()` for descriptors and ping-pong buffers;
- program the MBOX descriptor base/control registers directly (future step);
- use the MBOX interrupt/completion bits (future step);
- do not register a second generic DMA controller.

The current driver allocates and fills descriptors but does not program the
MBOX registers or request the IRQ.

---

## 5. Device-tree shape

The driver matches only:

```text
compatible = "avm,fon-tdm";
```

It does not match `qca,ipq4019-tdm`, `qca,ipq4019-pcm`, `qca,ipq4019-mbox`,
or `qca,ipq4019-stereo`.  This prevents binding to an AVM/vendor driver and
makes ownership explicit.

Reference node (the target 7530 patch keeps it disabled by default):

```dts
fon_tdm: fon-tdm@7700000 {
    compatible = "avm,fon-tdm";
    qcom,tdm-slots = <8>;

    reg = <0x07700000 0x34>,
          <0x07704000 0x2000>,
          <0x07708000 0x1000>,
          <0x0770e000 0x1000>,
          <0x07709000 0x1000>,
          <0x0770f000 0x1000>;
    reg-names = "adss", "pcm", "mbox_tx", "mbox_rx",
                "stereo_tx", "stereo_rx";

    interrupts = <GIC_SPI 156 IRQ_TYPE_LEVEL_HIGH>,
                 <GIC_SPI 159 IRQ_TYPE_LEVEL_HIGH>;
    interrupt-names = "mbox0", "mbox3";
    status = "disabled";
};
```

No `&adcc` phandle is used: mainline/OpenWrt 6.12 does not provide that
provider.  The driver treats the four TDM clocks and the audio block reset as
optional and never enables them.  Add real clock/reset phandles only after
the providers exist and the reset/clock sequence has been validated.

Important integration rules:

1. Do not enable the AVM `qca-pcm-tdm`, `qca-pcm`, `qca-audio-adss`, MBOX or
   STEREO drivers at the same time.  They claim the same MMIO regions.
2. The resource names and sizes must correspond to the actual DT; the driver
   maps only named resources and has no hardcoded addresses.
3. If the ADCC provider is not ported, omit the clocks or mark them optional;
   do not replace them with fake clocks.
4. The first test must leave `dma_prepare` and `dma_start` disabled; leave
   `diag_refresh` disabled until `allow_mmio_reads=1` and the clock/reset
   prerequisites are proven.
5. The node must not contain any ring/line voltage enable property.

The driver's `adss` resource only needs the global registers (`0x34`); `pcm`
is mapped for future use.  The MBOX and STEREO resources are optional in the
current probe, but a useful test should provide them.

---

## 6. Build integration

### 6.1 As an external module

From a Linux 6.12 kernel tree with a prepared build:

```sh
make -C /path/to/linux-6.12 \
     M=/path/to/repo/src/fon-driver \
     CONFIG_FON_TDM=m modules
```

Copy `fon_tdm_drv.ko` plus its license/module metadata to the target, and add
the DT node in a separate test overlay.  Do not install or load it in the
stock system without a rollback plan.

### 6.2 In an OpenWrt kernel tree

Add `src/fon-driver/` as an external kernel module package or place it under
the kernel source with:

```text
source "drivers/misc/fon-driver/Kconfig"
```

and add the corresponding `obj-$(CONFIG_FON_TDM)` to the parent Makefile.
The Kconfig symbol depends on `OF` and `ARCH_QCOM || COMPILE_TEST`.

The OpenWrt image build should keep `CONFIG_SND*` and the AVM QCA audio
drivers disabled for the first test, so there is no MMIO ownership conflict.

---

## 7. Build and test results in this workspace

### 7.1 Offline frame/control tests

Command:

```sh
cd src/fon-driver/tests
make run
```

Result: all tests passed.

Covered:

- 12-byte and 16-byte frame bounds;
- little-endian control/status word at offset `0x0a`;
- `0x48` → TX control mapping, including ring and marker bits;
- RX status → register `0x44` 32-bit value and hook bit 7;
- no write past the supplied frame.

### 7.2 Target OpenWrt 25.12.6 build

The actual target build is in `../runbook/fon-build-validation.md`:

```text
SDK: openwrt-sdk-25.12.6-ipq40xx-generic_gcc-14.3.0_musl_eabi
Kernel: Linux 6.12.112, arm, ipq40xx/generic
```

The package built a real target `fon_tdm_drv.ko` with clean `modpost` and
produced `kmod-fon-tdm-6.12.112-r1.apk`.  ELF architecture, vermagic and
undefined-symbol checks are recorded there.

### 7.3 Host compile check

The same sources also build cleanly against local Linux 6.8 headers for API
regression checks.  This is not the target kernel.

---

## 8. First safe hardware test plan

Do not start with ring or line voltage.  Suggested order:

1. Build the driver against the exact target kernel/toolchain.
2. Create a DT overlay/node with only the resources above; keep the AVM QCA
   audio drivers disabled.
3. Boot with the module unloaded.  Verify the DT node exists and that no
   other driver owns the MMIO regions.
4. Load `fon_tdm_drv.ko` with default parameters.  Check dmesg and read:
   - `/sys/.../stage`
   - `/sys/.../diagnostics`
   The default probe performs no MMIO reads and no DMA setup.
5. Only after the ADSS clock/reset prerequisites are independently proven,
   reload with `allow_mmio_reads=1` and write `1` to `diag_refresh`.  Confirm
   `ADSS_GLB_TDM_CTRL_REG` reports 8 TX and 8 RX slots.  If not, stop and
   update the DT/slot parameters; do not start DMA.
6. Write `1` to `dma_prepare` only.  Confirm the 28-bit DMA addresses and
   descriptor allocation in dmesg.  Do not write `dma_start`.
7. With a scope/logic analyzer on FSC/DCL (read-only), confirm the SC14448
   clock rate and frame timing.  Do not connect the analog line.
8. Only after a separate review of the slave/master configuration, MBOX
   direction inversion, and SC14448 firmware state may DMA start be enabled.
9. Only after a separate high-voltage review may line feed or ring be
   considered.  The LM324/BCP53-16 topology and safe voltages are not yet
   documented.

The `dma_start` attribute is present but deliberately returns
`-EOPNOTSUPP`; it is not a hidden automatic start.

---

## 9. Remaining port blockers

- ADCC clock provider absent from mainline/OpenWrt.
- AVM DTS audio nodes are not upstream; a target DT overlay is required.
- The AVM `ipq-adss-avm.c` driver is Linux 4.4 code and needs a real 6.12
  port if full ALSA/DAHDI support is desired.
- The exact SC14448 slot-5 semantics and firmware dependency are unresolved.
- The MBOX start/IRQ path has not been executed on hardware.
- The module has not been loaded on a FRITZ!Box 7530.
- A full OpenWrt firmware image was not built; only the target SDK module and
  package were built.
