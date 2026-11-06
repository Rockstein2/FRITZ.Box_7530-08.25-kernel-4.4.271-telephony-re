# OEM bootlog cross-check (FRITZ!OS reference)

> **Status: historical analysis.**
> This document records the reasoning and evidence as of the date it was
> written.  Some of its `UNKNOWN` / `UNVERIFIED` markers have since been
> answered.
> - Current confirmed facts: `../fon-known-facts.md`
> - Current open questions: `../fon-open-questions.md`
> - This file is kept for the reasoning trail, not as a status report.

Status: **analysis only; no hardware action**

This document records what the AVM OEM boot logs prove about the FON/TDM/
PCMLINK subsystem, and what they do not prove.  It exists so that the driver
assumptions in `fon-hardware.md`, `fon-resource-audit.md` and
`fon-dialog-hardware-test-plan.md` can be compared against a working
FRITZ!OS boot instead of only against static source.

---

## 1. Sources and their exact identity

### 1.1 Local log

```text
`wiki-fritzos-oem-bootlog-reference.txt` (60450 bytes, 1213 lines, in this repository)
```

Identity fields found in the file itself:

```text
S - QC_IMAGE_VERSION_STRING=AVM_BOOT.BF.3.1.1
S - IMAGE_VARIANT_STRING=DAABANAZA
S - OEM_IMAGE_VERSION_STRING=1204
Linux version 4.4.60 (jenkins@jenkins-ci.avm.de)
  (gcc 5.5.0, Buildroot 2018.11.4-g908cf03c90) #1 SMP PREEMPT 2021-04-26
```

So the local log is a **4.4.60** build from **2021-04-26**, not a 4.4.271
kernel.  It is an AVM FRITZ!OS log for HW236 (7530/7520 family).

### 1.2 Wiki log

A second boot log is referenced by the OpenWrt Wiki page for the 7530.  Its
FRITZ!OS version could **not** be confirmed (the wiki page is behind a bot
challenge and the indexed copy does not state the version).

**Consequence:** the repository source tree is `08.25` with kernel `4.4.271`.
Neither log is proven to come from `08.25`.  Do not treat either log as a
byte-exact reference for the `08.25` driver.  They are evidence about the
**hardware configuration**, not about a specific software release.

---

## 2. Timeline observed in the local log

| Time | Event |
|---|---|
| 0.388 s | `msm_dectuart_probe: set dectuart_port to ttyMSM0` |
| 0.388 s | `78af000.serial: ttyMSM0 at MMIO 0x78af000 (irq = 24, base_baud = 115200)` |
| 1.397 s | `console [ttyMSM0] enabled` |
| 11.9 s | `piglet.service` starts |
| 12.02 s | `[piglet]patch_dectfw`, `dectmode 5` |
| 12.03 s | `[piglet]slow: dect_loader-bootmode` |
| 17.77 s | `dect_file_process: upload of '/lib/modules/dectfw_secondlevel_441.hex' successfull` |
| 19.98 s | `[piglet]TDM: FS: 8000 Hz CLK: 1025720 Hz` |
| 20.12 s | `pcmlink` module loaded |
| 20.33 s | `isdn_fbox_fon5` module loaded |
| 20.39 s | `mbox_dma_init: irq=107 hwirq=191` … `success` |
| 20.69 s | `[isdn]PCMLINK: Codecslots=6 Slics=1 Pots=0 TE=0 NT=0 DECT=4 no HwCross DSP-EC: 0` |
| 21.01 s | `capi_codec` loaded |
| 21.12 s | `avm_dect` loaded |

Two ordering facts matter for our driver:

1. **The Dialog firmware upload happens before any PCMLINK/TDM user exists.**
   `piglet` uploads `dectfw_secondlevel_441.hex` at 17.77 s; `pcmlink` only
   appears at 20.12 s.  Our probe-only test therefore must not assume the
   SC14448 is idle or unprogrammed.
2. **TDM frame sync/clock is reported before `pcmlink` loads.**  The clock is
   already running when the first TDM client opens; we do not have to bring it
   up.

---

## 3. Facts confirmed by the logs

### 3.1 IRQ mapping

```text
mbox_dma_init: irq=107 hwirq=191
[avm_request_fiq_on] Forcing HW-IRQ 191 instead
```

- HW IRQ (GIC INTID) **191** is the MBOX3 interrupt.
- The Linux virq assigned to it at that moment was **107**.
- The DT in our tree uses `GIC_SPI 159` for mbox3 (`159 + 32 = 191`), which is
  consistent with the AVM DT (`qcom-ipq4019-audio.dtsi` in the GPL tarball:
  `mbox3: mbox@770e000 { interrupts = <0 159 0>; }`).
- This confirms the **INTID arithmetic**, not a specific virq.  The virq is a
  runtime allocation and must still be read on the bench.

Additional data point: AVM asks for this interrupt as a **FIQ**, not a normal
IRQ (`Forcing HW-IRQ 191 instead`).  Our driver uses a normal threaded IRQ;
that is a deliberate difference, not a bug, but it means AVM's handler timing
cannot be reproduced exactly in a first test.

### 3.2 TDM clocks

```text
[piglet]TDM: FS: 8000 Hz CLK: 1025720 Hz
```

- Frame sync is **8 kHz**.
- Bit/audio clock measured **1 025 720 Hz**, i.e. ~1.0257 MHz.
- The "ideal" 8 slots × 16 bit × 8 kHz = 1.024 MHz value used in our notes is
  close but **not exact**.  The measured clock is **higher** than
  8×16×8 kHz by about 1.7 kHz (0.17 %).
- Because the log is FRITZ!OS 4.4.60, the exact PLL configuration in 08.25
  may differ.  **Do not use 1 025 720 Hz as a hard reference; do not use it to
  tune a PLL.**  It is a sanity check only (the clock exists and is near
  1.024 MHz).

### 3.3 DMA channels and ports

```text
intf_tdm_probe: ena: dma-tx-channel=0 stereo-tx-port=0
               ena: dma-rx-channel=7 stereo-rx-port=3
```

Matches the AVM DT `tdm: tdm@0` node:

```text
dma-tx-channel  = MBOX0_TX_ID   (0)
dma-rx-channel  = MBOX3_RX_ID   (7)
stereo-tx-port  = STEREO0_ID    (0)
stereo-rx-port  = STEREO3_ID    (3)
```

Our own DT does not encode channels explicitly; it lists only the register
blocks.  The numbers above are the authoritative values if the driver ever
programs channels itself.

### 3.4 SLIC / codec configuration

```text
[isdn]PCMLINK:  Codecslots=6 Slics=1 Pots=0 TE=0 NT=0 DECT=4 no HwCross DSP-EC: 0
```

- **One SLIC** logical interface.
- **Four DECT** channels.
- **Zero** POTS/TE/NT.
- Six codec slots in use.

Interpretation limits:

- `Slics=1` is a **logical** count.  It does not prove a separate SLIC chip.
- `Pots=0` does **not** mean the analog FON is absent.  The `isdn_fbox_fon5`
  module is a separate FON subsystem; the PCMLINK counter describes its own
  slot allocation.  This must be resolved in the GPL source, not inferred
  from the log.

### 3.5 GPIO numbers

From the same log plus `Fritz_Box_HW236.dtsi` in the GPL tarball:

| Function | GPIO | Source |
|---|---|---|
| DECT reset | **40**, `AVM_DEF_HW_PARAM_GPIO_OUT_ACTIVE_HIGH` | HW236 dtsi, `gpio_avm_dect_reset` |
| DECT RD | 16 | HW236 dtsi, `gpio_avm_dect_rd` |
| LED power | 39 | log + HW236 dtsi |
| LED FON (`gpio_avm_led_fon`) | **35** | log |
| LED WLAN | 34 | log |
| LED connect | 45 | log |
| Button WLAN | 42 | log |
| Button connect | 41 | log |
| Button DECT | 43 | log |
| USB power enable | 49 | HW236 dtsi |

**Important:** GPIO40 (DECT reset) is **not** the FON LED (GPIO35).  These are
different signals on different pins.  Any document that conflates them is
wrong.  GPIO40 is still only statically known: its electrical connection to
the SC14448 reset pin remains **UNVERIFIED**.

### 3.6 PCMLINK pin mux (from the GPL board file)

```text
gpio_avm_pcmlink_fsc  = 22 (PINMUX2) / 26 (PINMUX3)
gpio_avm_pcmlink_dcl  = 21 (PINMUX2) / 25 (PINMUX3)
gpio_avm_pcmlink_mcl  = 20 (PINMUX2) / 24 (PINMUX3)
gpio_avm_pcmlink_di   = 23 (PINMUX3)
gpio_avm_pcmlink_do   = 27 (PINMUX3)
```

These are **board-specific AVM pin choices**, not SoC-fixed.  Our OpenWrt DT
does not set a `pinctrl` state for the FON node, so the kernel does not apply
them.  On a probe-only load this is harmless (no TDM traffic is generated),
but it means a full test must not expect AVM-like pin assignment until the
pinctrl state is added deliberately.

---

## 4. Open discrepancy: `qcom,tdm-slots`

| Evidence | Value |
|---|---|
| Our DT patch `900` | `qcom,tdm-slots = <8>` |
| AVM log | `Codecslots=6` |
| Driver constraint | `FON_TDM_MAX_SLOTS 16`, `slots >= 2` |

These are **not the same quantity**:

- `Codecslots` is a PCMLINK software allocation counter: how many codec slots
  the stack assigned.
- `qcom,tdm-slots` in our DT describes the TDM frame width used to size the
  DMA frame (`frame_bytes = slots * 2`, see `fon_hw.c`).

Therefore 6 vs 8 is **not a contradiction by itself**.  It is still an
unresolved question: our 8-slot frame has never been validated against AVM's
actual frame layout.  Treat it as `UNVERIFIED` and do not derive the frame
size from `Codecslots`.

---

## 5. What these logs do NOT prove

- `/proc/iomem` contents; no region ownership is shown.
- The actual Linux virq numbers that will appear on our kernel.
- The state of the SC14448 after boot (only that firmware was uploaded).
- The electrical polarity or the physical net of GPIO40.
- Anything about `08.25` / kernel `4.4.271` specifically.
- That `Pots=0` means "no analog FON".

---

## 6. Actions derived from this analysis

1. **Keep `qcom,tdm-slots = <8>` but mark it `UNVERIFIED`.**  Do not change it
   to 6 on the basis of the log; the quantities differ.  Record both numbers
   in the Stage A expectation file.
2. **Remove any suggestion that GPIO40 is the FON LED.**  GPIO35 is the LED;
   GPIO40 is the DECT reset line.
3. **Add the OEM values to the Stage A checklist** as known-good *reference*
   values (8 kHz FS, ~1.024 MHz clock, channels 0/7, ports 0/3, INTID 191
   for mbox3).
4. **Keep the FIQ/IRQ difference documented** so nobody "fixes" the driver to
   imitate AVM without understanding it.
5. **Do not attempt to reproduce the 1 025 720 Hz clock exactly** until 08.25
   evidence exists.

---

## 7. References

- `wiki-fritzos-oem-bootlog-reference.txt` (this repository).
- GPL tarball `source-files-FRITZ.Box_7530-cortexa9-08.25.tar.gz`:
  `sources/kernel/linux/arch/arm/boot/dts/Fritz_Box_HW236.dtsi`
  (GPIO table, TDM node status), `qcom-ipq4019-audio.dtsi` (register blocks,
  interrupts, DMA channel IDs).
- `src/fon-driver/fon_hw.c`, `fon_tdm.h` (frame sizing).
- OpenWrt Wiki 7530 page (external, bot-protected; version unconfirmed).
