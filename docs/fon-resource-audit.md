# FON resource and probe-safety audit

Status: **probe-only design is statically safe; full MMIO/DMA mode is NOT
READY for hardware**

This audit covers the FRITZ!Box 7530 `fon_tdm_drv` probe path after the
probe-only change.  No router was touched and no runtime `/proc/iomem` or
`/proc/interrupts` capture was taken.

Sources:

- target OpenWrt 25.12.6:
  `target/linux/ipq40xx/files-6.12/arch/arm/boot/dts/qcom/qcom-ipq4019-fritzbox-7530.dts`;
- mainline Linux 6.12 `qcom-ipq4019.dtsi`;
- OpenWrt 25.12.6 ipq40xx DTS patches;
- AVM GPL 08.25 `qcom-ipq4019-audio.dtsi`, `Fritz_Box_HW236.dtsi`,
  `ipq-adss-avm.c`, `ipq-adss.h`;
- prior AVM `pcmlink.ko` disassembly in `reports/` and the analysis documents.

---

## 1. Address map and current target ownership

The target OpenWrt DTS contains **no** `qca,ipq4019-audio-adss`, PCM, MBOX or
STEREO nodes.  Those nodes exist in the AVM GPL board DTS but are not part of
the OpenWrt 25.12.6 target DTS.

| Name | Address / length | AVM GPL owner | OpenWrt 25.12.6 owner |
|---|---|---|---|
| `adss` | `0x07700000` + `0x34` | AVM `audio@7700000` (`qca,ipq4019-audio-adss`) | none |
| `pcm` | `0x07704000` + `0x2000` | AVM `pcm@7704000` (`qca,ipq4019-pcm`) | none |
| `mbox_tx` | `0x07708000` + `0x1000` | AVM `mbox0@7708000` | none |
| `mbox_rx` | `0x0770e000` + `0x1000` | AVM `mbox3@770e000` | none |
| `stereo_tx` | `0x07709000` + `0x1000` | AVM `stereo0@7709000` | none |
| `stereo_rx` | `0x0770f000` + `0x1000` | AVM `stereo3@770f000` | none |

Additional cross-checks:

- The AVM `adcc` clock-controller node is at `0x07700038`.  The `adss`
  resource ends at `0x07700033`, so it does **not** overlap `0x07700038`.
  The target DTS also does not provide the AVM ADCC provider.
- The target UART console is `blsp1_uart1: serial@78af000`, length `0x200`.
  It is outside all FON resources and must not be touched.
- The target GCC is at `0x1800000`, also outside the FON ranges.
- The AVM `qca-pcm-tdm@7709000` node uses the same address as the
  `stereo_tx` resource.  It is absent from the target DTS; enabling both a
  vendor TDM/PCM driver and this node would be a real conflict.
- No target `dma-ranges`, IOMMU or DMA controller is associated with these
  MBOX registers; the MBOX DMA addresses are the 28-bit addresses from the
  AVM implementation.

The addresses in the current DTS patch are therefore consistent with the
AVM GPL map.  This is a **static DTS/source** result, not proof that the
running kernel has not mapped or reserved a region elsewhere.

---

## 2. IRQ mapping

AVM board DTS:

```text
MBOX0: <0 156 0>
MBOX3: <0 159 0>
```

The AVM MBOX driver requests these with `IRQF_TRIGGER_HIGH`.  The target
probe-only DTS patch uses:

```text
<GIC_SPI 156 IRQ_TYPE_LEVEL_HIGH>
<GIC_SPI 159 IRQ_TYPE_LEVEL_HIGH>
```

The probe-only path calls `platform_get_irq_optional()` only.  It does **not**
call `request_irq()`, enable the interrupt, or touch the MBOX interrupt
status/enable registers.

The exact runtime trigger configuration should still be checked from
`/proc/interrupts` after the test image boots.  The first test does not rely
on the IRQ.

---

## 3. Clocks, reset and pinctrl

### AVM sequence

The AVM audio probe maps the ADSS block, obtains `blk_rst`
(`AUDIO_BLK_ARES`), asserts it, waits 20–24 ms, deasserts it, enables the I2S
interface and sets B1K.  The TDM node separately owns the four ADCC clocks.

### Target OpenWrt

The target 7530 DTS has no FON `clocks`, `resets`, `pinctrl-0`, or ADCC
provider.  The current DTS patch deliberately does not invent `&adcc` or
`&gcc` phandles.

### Driver behavior

| Mode | Clocks | Reset | Pinctrl |
|---|---|---|---|
| probe-only (default) | not acquired | not acquired | not acquired |
| full (`probe_only=0`) | optional handles, never enabled | optional exclusive handle, never asserted/deasserted | handle only, **no state selection** |

The full mode has no clock/reset/pinctrl side effects, but obtaining an
exclusive reset handle can still conflict with another consumer.  That is one
reason full mode is not part of the first test.

The AVM board GPIO table (GPIO20–27 for FSC/DCL/MCL/DI/DO) is not automatically
applied by this driver.  The target `pinctrl-ipq4019` functions for these
signals are not proven; no state is selected.

---

## 4. Probe path safety

### 4.1 Default `probe_only=1`

The probe performs only:

1. `devm_kzalloc` of the software state;
2. `mutex_init`, `platform_set_drvdata`;
3. parse `qcom,tdm-slots`;
4. `platform_get_resource_byname` for six named MEM resources **without
   requesting or mapping them**;
5. `platform_get_irq_optional` **without requesting**;
6. count `clock-names`/`reset-names` strings and check for `pinctrl-0`
   **without acquiring clocks/reset/pinctrl**;
7. sibling DT `reg` overlap scan using `of_address_to_resource`;
8. register the sysfs group.

It does **not** call `devm_ioremap_resource`, `ioremap`, `readl`, `writel`,
`devm_clk_get`, `devm_reset_control_get`, `devm_pinctrl_get`,
`dma_alloc_coherent`, `request_irq`, GPIO reset, or firmware upload.

`of_address_to_resource` is an OF translation operation; it does not access
device MMIO or claim an iomem region.

### 4.2 Full `probe_only=0`

Full mode maps all present resources with `devm_ioremap_resource`, which
calls the exclusive `request_mem_region` path.  It then obtains optional clock
handles, an optional exclusive reset handle, and a pinctrl handle.  It still
does not read/write MMIO, enable a clock, assert reset, select a pinctrl
state, request IRQ, or allocate DMA.

Full mode remains **NOT READY** because it has not been exercised on hardware.

### 4.3 DT overlap result

The probe reports `dt_overlap=1` if any sibling DT node has an overlapping
`reg` range.  This catches obvious target-DTS mistakes such as enabling both
`stereo_tx` and `qca-pcm-tdm@7709000`.

It does **not** prove runtime iomem ownership.  `/proc/iomem` must be
captured in the first hardware test before any full-mode mapping.

---

## 5. sysfs, unbind and concurrency

The sysfs group is registered with `devm_device_add_group`; the device core
removes it as part of device teardown.  The driver keeps:

```text
mutex lock
removing flag
state: UNINITIALIZED -> RESOURCES_READY -> DMA_PREPARED
```

All state-changing sysfs handlers take `mutex_lock`.  `remove()` also takes
the mutex, sets `removing`, releases any prepared rings, sets state
`UNINITIALIZED`, unlocks and clears the platform drvdata.  A handler that
runs after removal sees either the `removing` flag or a NULL drvdata and
returns `-ENODEV`.

Probe-only never allocates DMA, so its unbind path has no DMA free operation
and no double-free risk.  Full DMA prepare/release is idempotent and was
already covered by the offline state/layout tests.

Remaining concurrency caveat: this is a normal kernel sysfs/device-removal
pattern, but it has not been stress-tested against unbind on a live system.

---

## 6. Error unwind

- Probe-only: all allocations are devm-managed; no MMIO/clock/reset/pinctrl
  claims exist.  If sysfs group registration fails, devm cleans up state.
- Full mode: each `devm_ioremap_resource` is devm-managed; a later failure
  unwinds earlier mappings automatically.  Optional clock/reset/pinctrl
  handles are devm-managed.  DMA is not allocated in probe, only by an
  explicit later sysfs action with its own unwind.
- No UART, GPIO40, firmware or line/ring operation exists in probe.

---

## 7. What is still unproven

1. Runtime `/proc/iomem` ownership on the actual 7530.
2. Actual IRQ type and interrupt ownership.
3. Whether any hidden firmware/secure mapping reserves `0x7700000` ranges.
4. Whether enabling the FON node and loading the module changes any GPIO or
   clock state indirectly through unrelated subsystems.
5. Full-mode mapping and reset/clock references on hardware.
6. ADCC provider availability on the target build.
7. The actual effect of SC14448 reset on the analog line.

## 8. Verdict

```text
overall hardware:  NOT READY (no runtime validation)
probe-only:        CONDITIONAL GO for a first read-only DT/platform test
full MMIO/DMA:     NOT READY
line/ring/firmware: NOT READY
```

The first hardware experiment must use the optional probe-only DTS
configuration and the default `probe_only=1`, with no `diag_refresh`,
`dma_prepare`, or `dma_start` writes.  See
`docs/fon-first-hardware-test.md`.
