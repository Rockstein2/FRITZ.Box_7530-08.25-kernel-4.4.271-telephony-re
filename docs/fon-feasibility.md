# FON standalone-driver feasibility

Status: stage 3 assessment, updated by stage 4. This is a
static/architectural conclusion, not a tested driver.

> Stage 4 update: `docs/fon-control-path.md` adds the Dialog SC14448
> hypothesis and the firmware/UART/PCM evidence. The conclusion remains
> **CONDITIONAL GO**, with a new firmware-dependency condition.

## 1. Direct answers

### 1. Can FXS be controlled independently of `isdn_fbox_fon5.ko`?

**LIKELY, but not yet proven.**

The low-level control is not in `isdn_fbox_fon5`; it is a virtual register
bank implemented by `pcmlink`:

```text
pcmlink_ul_readregister  (0x3444)
pcmlink_ul_writeregister (0x3b60)
registers 0x40, 0x44, 0x48, 0x4c, 0x50
```

`isdn_fbox_fon5` only supplies the policy:

```text
slic_set_ring        0x408d0
slic_get_hook_state  0x4093c
slics_reset          0x40994
Set_POTS_Line_FPGA   0x419c4
```

A clean driver can reimplement that policy if the virtual-register transport
and the discrete line-interface topology are known. They are not fully known
today.

### 2. Are the necessary hardware interfaces available in Linux 6.12?

**Partially. BLOCKED for the TDM/PCM part.**

Available in mainline/OpenWrt:

```text
IPQ4019 pinctrl/GPIO
QCOM clock/reset frameworks
ALSA SoC core
DMA engine framework
```

Not available:

```text
QCA IPQ4019 TDM/PCM + ADSS driver
vendor tdm_if_config_init / tdm_if_dma_init / tdm_if_dma_start
vendor FON/SLIC virtual-register transport
```

The 2016 QCA IPQ4019 ASoC driver series (`ipq4019-adss.c`,
`ipq4019-pcm-tdm.c`, `ipq4019-cpu-dai.c`, `ipq4019-mbox.c`) was an RFC and did
not become a mainline driver. The IPQ4019 TDM/PCM block is documented in QCA
material at `0x7709000`, but a clean 6.12 driver does not exist yet.

### 3. Can two-way PCM be obtained without the original `pcmlink.ko`?

**CONDITIONAL.**

The PCM path itself is standard 16-bit TDM with 16 DMA descriptors:

```text
tdm_if_config_init(slot_size, tx_slots, rx_slots, config)
tdm_if_dma_init(handle, TxData, RxData, 1, 1,
                slot_size, slot_ratio, 16)
```

`pcmlink` uses a 0x14-byte DSP slot descriptor (`slot`, `length`, `offset`) and
two buffer bases (`+0x38` TX, `+0x3c` RX). This is a normal TDM/DMA design and
can be reimplemented with ALSA SoC/DAI + DMA engine **if** the QCA ADSS/TDM
register programming is recovered.

Without that driver, there is no PCM path.

### 4. Are closed firmware or hardware DSP required?

**LIKELY NO for basic 8 kHz PCM.**

The stock log reports:

```text
DSP-EC: 0
```

No hardware echo canceller is active. `pcmlink` contains codec/EC/G.722 code,
but basic narrowband PCM should not require the AVM DSP firmware. `capi_codec`
is a CAPI codec layer, not a requirement for raw PCM.

This must still be confirmed on hardware. Wideband/G.722 or echo cancellation
would add requirements.

### 5. Is there a compatible TDM/DMA driver in OpenWrt?

**NO, not in the current 6.12 target.**

There is no mainline `qca,ipq4019-pcm-tdm` driver in Linux 6.12. OpenWrt's
ipq40xx target does not ship the vendor `tdm_if_*` implementation. DAHDI does
not remove this blocker; it would still need a hardware TDM/DMA driver.

The closest starting points are:

```text
2016 QCA IPQ4019 ASoC RFC (not merged)
QCA ADSS/TDM register documentation
vendor tdm_if_* call sites recovered from pcmlink.ko
```

### 6. Can the functionality be implemented as GPL-compatible code?

**YES, in principle.**

The control and audio logic can be written clean-room from:

```text
virtual-register numbers and bit positions
TDM slot descriptor layout
PCMRoute routing model
QCA ADSS/TDM register documentation
```

No AVM source code or binary module needs to be linked. The unresolved part is
technical (discrete line-interface topology/TDM programming), not licensing.

## 1.1 Stage 4 update: the Dialog SC14448 hypothesis

`docs/fon-control-path.md` investigates whether FON is an LM324 analog path
plus the SC14448 codec.

Result: **largely supported at board level, with a new hard condition for the
project** (the control/audio transport remains unproven).

- Public board data lists LM324 and BCP53-16 as FON components, and the
  SC14448 as the DECT chip. The 14-pin device near the DECT antenna is the
  LM324; no separate SLIC IC is listed or identified. The FON PHY is a
  discrete LM324/BCP53-16 line interface. A standard SPI/I2C SLIC controlled
  directly by Linux is not present.
- FON control is still the `pcmlink` virtual-register bank. It is **not** a
  FON UART protocol: `Piglet_noemif` owns the Dialog UART but exports no FON
  API; `avm_dect` and `pcmlink` import no UART.
- The SC14448 has dual codec, 6-channel PCM+, ADC/opamps and GPIO, so it is a
  plausible FON codec/line controller. The 6 codec slots match 4 DECT + 1
  SLIC + 1 spare. With no separate SLIC IC identified, its codec/GPIO is now
  the most likely FON audio/control target.
- The exact transport from `pcmlink` to the discrete FON PHY is still missing.
  It may be a QCA TDM control slot, a shared-memory mailbox, or a PCM+ mailbox
  to the SC14448. If the SC14448 firmware is in the loop, a standalone Linux
  module must implement that mailbox protocol or bypass the SC14448 in
  hardware.

This does not turn the project into GO. It makes the "small independent
module" harder to justify until the firmware dependency is resolved: with no
separate SLIC identified, the SC14448 is the only known plausible digital
controller.

## 2. Risk table

| Risk | Status | Why |
|---|---|---|
| Discrete line-interface topology | **UNKNOWN** | LM324/BCP53-16 circuit and SC14448 pin mapping not traced; no separate SLIC IC |
| FON virtual-register bit map | **LIKELY** | hook/ring/line registers and bits recovered; full map incomplete |
| FON line reset/regulator/clock wiring | **UNKNOWN** | no direct GPIO/regulator references in `isdn_fbox_fon5` |
| Ring voltage/cadence safety | **UNKNOWN** | no discrete line schematic; ringing can use elevated voltage |
| QCA TDM/PCM driver in 6.12 | **BLOCKED** | 2016 RFC only, not mainline/OpenWrt |
| `tdm_if_*` vendor API | **BLOCKED** | implementation absent; only call sites recovered |
| Basic 8 kHz PCM without DSP | **LIKELY** | `DSP-EC: 0`; standard 16-bit TDM |
| Two-way PCM without `pcmlink` | **CONDITIONAL** | possible after TDM/DMA backend |
| Hook detection | **LIKELY** | reg 0x44 bit 7 for SLIC0 |
| Ring control | **LIKELY** | reg 0x48 bits 5/6 for SLIC0 |
| Line feed | **LIKELY** | reg 0x48 line-state writes + PCMRoute |
| Userspace/Asterisk integration | **LIKELY** | ALSA PCM + small control interface |
| GPL-compatible clean implementation | **CONFIRMED** | no proprietary code required |
| DECT/ISDN/CAPI exclusion | **CONFIRMED** | not needed for one FXS port |
| Actual FON control transport | **UNKNOWN** | QCA backend has no `set_status`; transport is in missing `tdm_if_*`/shared memory |
| SC14448 firmware dependency | **LIKELY / HIGH RISK** | with no separate SLIC or CPLD identified, the SC14448 is the only known plausible digital controller; PCM+ mailbox protocol not proven |
| FON PHY topology | **UNKNOWN** | discrete LM324/BCP53-16; the 14-pin device is LM324, no separate SLIC identified; high-voltage/ring topology not known |
| FON UART protocol | **RULED OUT** | no UART imports in `pcmlink`/`isdn_fbox_fon5`/`avm_dect`; `Piglet` has no FON API |

## 3. Effort estimate

Assumes the discrete line-interface schematic/board wiring and a usable QCA
TDM/DMA reference are obtained.

| Work item | Estimate | Notes |
|---|---:|---|
| Discrete FON line-interface tracing and safe line/ring sequence | 1–2 weeks | LM324/BCP53-16 topology and SC14448 pin mapping; includes bench safety |
| Minimal control driver (hook/line/ring) | 2–4 weeks | virtual-register or direct control path |
| QCA TDM/PCM + DMA backend | 6–12 weeks | port 2016 ADSS or write minimal DAI/DMA |
| SC14448 PCM+ mailbox / firmware protocol | 4–12 weeks | only if the Dialog firmware is in the FON path; unknown |
| ALSA SoC integration / PCM device | 2–4 weeks | depends on backend |
| Asterisk/DAHDI integration | 1–2 weeks | after stable PCM |
| Hardware validation | 2–4 weeks | ring/line feed/PCM loopback |
| **Total** | **4–7 months** | one experienced kernel/telephony engineer, assuming no firmware dead end |

Without the discrete line-interface schematic or QCA TDM reference, the
estimate is not meaningful; the project is blocked at hardware identification
and the SC14448 firmware dependency.

## 4. Recommended architecture

If the conditions are met:

```text
ALSA SoC
  - CPU DAI: QCA IPQ4019 TDM/PCM
  - DMA: 16-descriptor TDM DMA
  - codec DAI: minimal FON PCM DAI (16-bit, 8 kHz)
  - machine driver: FRITZ!Box 7530 FON

Control driver
  - /dev/fon0 or a small sysfs/ioctl interface
  - hook/on-hook/off-hook
  - line feed
  - ring cadence
  - FON line reset/error

Userspace
  - Asterisk via ALSA PCM or a small DAHDI shim
```

DAHDI is not recommended as the primary architecture: it is out-of-tree and
would still require the same QCA TDM/DMA backend. ALSA SoC is the better fit
for the IPQ4019 audio block.

## 5. Conclusion

**CONDITIONAL GO.**

The project is technically realistic, but only after these conditions are met:

1. Trace the discrete LM324/BCP53-16 line interface to the SC14448
   GPIO/PWM/ADC pins and recover the high-voltage/ring topology, **or** obtain
   the AVM GPL `pcmlink_ll.c`/`tdm_if_*`/`isdn_fon5` source that contains the
   virtual-register transport and discrete-line model.
2. Prove whether the SC14448 firmware participates in FON control/audio. If
   it does, either recover the PCM+ mailbox protocol or show that the stock
   board can be driven without that firmware.
3. Recover or port the QCA IPQ4019 TDM/PCM + ADSS/DMA programming
   (`tdm_if_*` equivalent).
4. Validate hook/ring/line-feed and basic 8 kHz PCM on a safe bench setup
   before connecting a telephone. Confirm that no closed DSP firmware is
   required for the basic PCM path.

If item 1, 2 or 3 cannot be satisfied, the correct conclusion becomes
**NO-GO**: without the discrete-line model, the firmware dependency answer, or
the TDM/DMA backend there is no safe, independent FXS driver.

## 6. Next actions

1. Trace the discrete LM324/BCP53-16 line interface on the 7530 PCB/service
   manual: audio in/out, hook sense, line feed, ring drive and the SC14448
   GPIO/PWM/ADC connections.
2. Request the AVM GPL source package for FRITZ!OS 08.25 and search for
   `pcmlink_ll.c`, `slic*.c`, `tdm_if_*`, `ipq40xxtdm_*`, and any SC14448
   mailbox/PCM+ code.
3. Recover the QCA ADSS/TDM register map from the IPQ4019 datasheet or QSDK.
4. If a stock 7530 is available, capture the `pcmlink` virtual-register writes
   during hook/ring/line-feed transitions (read-only trace, no flash changes).
5. Trace whether any PCM+ control slot or shared-memory mailbox reaches the
   SC14448 during the same transitions.
6. Disassemble the SC14448 second-level firmware with the peripheral map and
   look for the PCM+ interrupt handler/GPIO writes; do not rely on strings.
7. Only then start `src/fon-driver/`.
