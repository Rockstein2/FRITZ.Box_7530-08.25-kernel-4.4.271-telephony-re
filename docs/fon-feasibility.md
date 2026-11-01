# FON standalone-driver feasibility

Status: stage 3 assessment, updated by stages 4 and 5. This is a
static/architectural conclusion, not a tested driver.

> Stage 4 update: `docs/fon-control-path.md` adds the Dialog SC14448
> hypothesis and the firmware/UART/PCM evidence. The conclusion remains
> **CONDITIONAL GO**, with a new firmware-dependency condition.
>
> Stage 5 update: `docs/fon-pcmlink-register-path.md` recovers the actual
> transport. FON registers are consumed by `TxDMA` and become a 16-bit control
> word in **TDM/MBOX slot 5**; hook status is read from RX slot 5 by
> `PutRxDMA`. The old “missing transport” risk is removed, but the QCA ADSS
> port and the SC14448 control-word semantics remain.

## 1. Direct answers

### 1. Can FXS be controlled independently of `isdn_fbox_fon5.ko`?

**CONDITIONAL. The transport is now recovered, but the line-interface
semantics and firmware dependency are not.**

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
QCA IPQ4019 TDM/PCM + ADSS driver for Linux 6.12
vendor tdm_if_config_init / tdm_if_dma_init / tdm_if_dma_start
  (4.4.271 source exists in the GPL tarball, not ported)
FON slot-5 control/status implementation in a standalone driver
  (transport recovered; implementation not written)
```

The 2016 QCA IPQ4019 ASoC driver series (`ipq4019-adss.c`,
`ipq4019-pcm-tdm.c`, `ipq4019-cpu-dai.c`, `ipq4019-mbox.c`) was an RFC and did
not become a mainline driver. The IPQ4019 TDM/PCM block is documented in QCA
material at `0x7709000`, but a clean 6.12 driver does not exist yet.

### 3. Can two-way PCM be obtained without the original `pcmlink.ko`?

**CONDITIONAL.**

The PCM path is 16-bit TDM with **ADSS MBOX DMA**, not a plain TDM FIFO:

```text
tdm_if_config_init(slots, rxdelay, txdelay, master)
tdm_if_dma_init(handle, TxData, RxData, cpu, only_rxirq,
                slots, fs_per_dma, 16)
  -> tdm_if_adss_dma_init()
  -> mbox_dma_init(PLAYBACK/CAPTURE)
```

`pcmlink` uses a 0x14-byte DSP slot descriptor (`slot`, `length`, `offset`) and
two buffer bases (`+0x38` TX, `+0x3c` RX). The QCA vendor source for
`tdm_if_adss_*` and MBOX DMA is available in the 08.25 GPL tarball, but it is
not a Linux 6.12 driver. It must be ported to DMA engine/ALSA or rewritten.

Without that driver, there is no PCM path.

### 4. Are closed firmware or hardware DSP required?

**LIKELY NO for basic audio; UNKNOWN for FON control.**

The stock log reports:

```text
DSP-EC: 0
```

No hardware echo canceller is active. `pcmlink` contains codec/EC/G.722 code,
but basic narrowband PCM should not require the AVM DSP firmware. `capi_codec`
is a CAPI codec layer, not a requirement for raw PCM.

FON control is different: the 16-bit control/status word is carried in the
TDM/MBOX frame and is most likely consumed by SC14448 firmware. If that
firmware is required, a standalone Linux driver must still run the stock
firmware (or implement its slot-5 protocol). This is not proven. Wideband/G.722
or echo cancellation would add further requirements.

### 5. Is there a compatible TDM/DMA driver in OpenWrt?

**NO, not in the current 6.12 target.**

There is no mainline `qca,ipq4019-pcm-tdm` driver in Linux 6.12. OpenWrt's
ipq40xx target does not ship the vendor `tdm_if_*` implementation. DAHDI does
not remove this blocker; it would still need a hardware TDM/DMA driver.

The closest starting points are:

```text
2016 QCA IPQ4019 ASoC RFC (not merged)
QCA ADSS/TDM register documentation
AVM 08.25 GPL source: ipq-adss-avm.c, ipq-avm.c, ipq-adss.h
pcmlink.ko call sites and TxDMA/PutRxDMA slot-5 layout
```

### 6. Can the functionality be implemented as GPL-compatible code?

**YES, in principle.**

The control and audio logic can be written clean-room from:

```text
virtual-register numbers and bit positions
TDM/MBOX slot-5 control/status layout
QCA ADSS/TDM source (GPL) and register documentation
PCMRoute routing model (reimplemented, not linked)
```

No AVM binary module needs to be linked. The QCA `tdm_if_adss_*`/MBOX source
is GPL-2.0 and can be ported; `pcmlink_ul.c`/`pcmlink_ll.c` source is not
published, so the register-ring/route logic must be reimplemented from the
confirmed binary behavior. The unresolved part is technical (SC14448
semantics and discrete line-interface topology), not licensing.

## 1.1 Stage 4 update: the Dialog SC14448 hypothesis

`docs/fon-control-path.md` investigates whether FON is an LM324 analog path
plus the SC14448 codec.

Result at stage 4: **largely supported at board level, with a new hard
condition for the project**. Stage 5 then recovered the transport (TDM/MBOX
slot 5); the remaining condition is the SC14448 slot-5 semantics/firmware.

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
- At stage 4 the exact transport from `pcmlink` to the discrete FON PHY was
  missing. Stage 5 resolved it: a command ring consumed by `TxDMA`, then a
  16-bit control word in TDM/MBOX slot 5; hook returns in RX slot 5. The
  SC14448 side of that word is still unproven.

This does not turn the project into GO. It makes the "small independent
module" harder to justify until the firmware dependency is resolved: with no
separate SLIC identified, the SC14448 is the only known plausible digital
controller.

## 1.2 Stage 5 update: actual transport recovered

`docs/fon-pcmlink-register-path.md` reconstructs the complete Linux-side path:

```text
slic_set_ring / Set_POTS_Line_FPGA
  -> pcmlink_ul_writeregister
  -> 8-byte command ring in TDMPriv+0x4a0+0x68
  -> TxDMA (TX DMA callback)
  -> build_slic_ctrl / _buildslic_ctrl_ring
  -> 16-bit control word at TX frame offset 0x0a (TDM slot 5)
  -> QCA ADSS MBOX/TDM DMA
  -> PCM/TDM/MBOX bus
```

Hook is the reverse:

```text
RX frame offset 0x0a (status word)
  -> PutRxDMA
  -> virtual register 0x44 at TDMPriv+0x4a0+0x26c+0x44
  -> pcmlink_ul_readregister(0x44)
  -> slic_get_hook_state -> bit 7
```

Confirmed details:

- `pcmlink_ul_writeregister` is asynchronous: it enqueues a ring entry, sets a
  shadow value and dirty bit, and does not touch MMIO.
- `TxDMA` consumes the ring; `PutRxDMA` updates the status table.
- The control/status word is in **slot 5** of the TDM/MBOX frame, alongside
  five audio/control slots. This matches `Codecslots=6 Slics=1 DECT=4`.
- Board DTS enables `tdm@0`, `pcm@7704000`, `mbox0..4` and `stereo0..3`;
  `tdm` uses MBOX0 TX/MBOX3 RX, `pcm` uses MBOX3 TX/MBOX0 RX.
- The QCA `tdm_if_adss_*`/MBOX DMA source is present in the 08.25 GPL tarball;
  `pcmlink_ul.c`/`pcmlink_ll.c` source is not present.

Consequences:

- The transport is no longer a blocker. A minimal driver can use the QCA
  ADSS/TDM/MBOX backend and slot-5 control/status, without recreating the AVM
  virtual-register transport.
- The remaining hard questions are the **SC14448 interpretation of the
  16-bit words**, the **discrete high-voltage/ring circuit**, and porting the
  QCA ADSS driver to Linux 6.12.
- A standalone module is still **CONDITIONAL GO**, but the next work is now
  concrete rather than speculative.

## 2. Risk table

| Risk | Status | Why |
|---|---|---|
| Discrete line-interface topology | **UNKNOWN** | LM324/BCP53-16 circuit and SC14448 pin mapping not traced; no separate SLIC IC |
| FON virtual-register bit map | **LIKELY** | hook/ring/line registers and bits recovered; full map incomplete |
| FON line reset/regulator/clock wiring | **UNKNOWN** | no direct GPIO/regulator references in `isdn_fbox_fon5` |
| Ring voltage/cadence safety | **UNKNOWN** | no discrete line schematic; ringing can use elevated voltage |
| QCA TDM/PCM driver in 6.12 | **BLOCKED** | 2016 RFC only, not mainline/OpenWrt; 08.25 vendor source found but not ported |
| `tdm_if_*` vendor API | **SOURCE AVAILABLE / PORT NEEDED** | `ipq-adss-avm.c`, `ipq-avm.c` in the 08.25 GPL tarball; AVM FASTIRQ/RTE dependencies must be removed |
| Basic 8 kHz PCM without DSP | **LIKELY** | `DSP-EC: 0`; 16-bit ADSS MBOX/TDM DMA |
| Two-way PCM without `pcmlink` | **CONDITIONAL** | possible after TDM/DMA backend |
| Hook detection | **CONFIRMED (Linux path)** | RX slot 5 status bit 3 -> reg 0x44 bit 7; `slic_get_hook_state` |
| Ring control | **CONFIRMED (Linux path)** | reg 0x48 bits 5/6 -> ring command -> TX slot 5 control word |
| Line feed | **LIKELY** | reg 0x48 line-state writes + `build_slic_ctrl`; exact SC14448 bits unproven |
| Userspace/Asterisk integration | **LIKELY** | ALSA PCM + small control interface |
| GPL-compatible clean implementation | **CONFIRMED** | no proprietary code required |
| DECT/ISDN/CAPI exclusion | **CONFIRMED** | not needed for one FXS port |
| Actual FON control transport | **CONFIRMED** | `TxDMA`/`PutRxDMA` use TDM/MBOX frame slot 5; QCA ADSS MBOX DMA; see `docs/fon-pcmlink-register-path.md` |
| SC14448 control-word semantics | **UNKNOWN / HIGH RISK** | 16-bit control/status slot is confirmed; exact SC14448 parsing/pins/firmware not proven |
| SC14448 firmware dependency | **UNKNOWN / HIGH RISK** | with no separate SLIC or CPLD identified, the SC14448 is the only known plausible digital controller; firmware role not proven |
| FON PHY topology | **UNKNOWN** | discrete LM324/BCP53-16; the 14-pin device is LM324, no separate SLIC identified; high-voltage/ring topology not known |
| FON UART protocol | **DISPROVED** | no UART imports in `pcmlink`/`isdn_fbox_fon5`/`avm_dect`; `Piglet` has no FON API |
| `pcmlink_ll_set_status` as FON-register transport | **DISPROVED** | actual link table is `FPGALink`/QCA-ADSS; register path is ring + `TxDMA`, not `Set_Status` |

## 3. Effort estimate

Assumes the discrete line-interface schematic/board wiring and a usable QCA
TDM/DMA reference are obtained.

| Work item | Estimate | Notes |
|---|---:|---|
| Discrete FON line-interface tracing and safe line/ring sequence | 1–2 weeks | LM324/BCP53-16 topology and SC14448 pin mapping; includes bench safety |
| Minimal control driver (hook/line/ring + slot 5) | 2–4 weeks | virtual-register policy and TX/RX slot-5 handling |
| QCA ADSS/PCM/MBOX backend port | 4–8 weeks | 08.25 GPL source exists; remove AVM FASTIRQ/RTE and port to 6.12 DMA/ALSA |
| SC14448 slot-5 semantics / firmware dependency | 2–8 weeks | read firmware/trace slot 5; unknown until proven |
| ALSA SoC integration / PCM device | 2–4 weeks | depends on backend |
| Asterisk/DAHDI integration | 1–2 weeks | after stable PCM |
| Hardware validation | 2–4 weeks | ring/line feed/PCM loopback |
| **Total** | **3–6 months** | one experienced kernel/telephony engineer, assuming no firmware dead end |

Without the discrete line-interface schematic or a successful QCA ADSS port,
the estimate is not meaningful; the project is blocked at SC14448
control-word semantics and hardware validation.

## 4. Recommended architecture

If the conditions are met:

```text
ALSA SoC
  - CPU DAI: QCA IPQ4019 TDM/PCM
  - DMA: ADSS MBOX DMA (TX/RX descriptors)
  - codec DAI: minimal FON PCM DAI (16-bit, 8 kHz)
  - control slot: TDM/MBOX slot 5, TX/RX 16-bit words
  - machine driver: FRITZ!Box 7530 FON

Control driver
  - /dev/fon0 or a small sysfs/ioctl interface
  - hook/on-hook/off-hook (RX slot 5 -> reg 0x44 bit 7)
  - line feed / ring cadence (TX slot 5)
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

1. Prove the SC14448 interpretation of TDM/MBOX slot 5: control-word bits,
   status-word bits, GPIO/PWM/ADC mapping and firmware involvement. Trace the
   discrete LM324/BCP53-16 high-voltage/ring circuit at the same time.
2. Port the QCA IPQ4019 ADSS/PCM/MBOX driver from the 08.25 GPL source to
   Linux 6.12, including DMA descriptors, interrupts, clocks/resets and
   pinctrl. This is now a known source port, not a missing reverse-engineering
   target.
3. Implement the slot-5 TX/RX control/status handling and one 8 kHz PCM path,
   then wire the ring/hook/line policy.
4. Validate hook/ring/line-feed and basic 8 kHz PCM on a safe bench setup
   before connecting a telephone. Confirm whether the stock SC14448 firmware
   is required for FON control.

If item 1 or 2 cannot be satisfied, the correct conclusion becomes **NO-GO**:
without the SC14448 slot-5 semantics or the ADSS/MBOX backend there is no safe,
independent FXS driver.

## 6. Next actions

1. Extract and study the 08.25 GPL QCA source (`ipq-adss-avm.c`,
   `ipq-avm.c`, `ipq-adss.h`) and the 7530 DTS; identify the exact `tdm`/`pcm`
   binding used by `pcmlink`.
2. Disassemble the SC14448 second-level firmware with a CR16C disassembler and
   locate the PCM/MBOX slot-5 handler, GPIO/PWM/ADC writes, hook debounce and
   ring control. Do not rely on strings.
3. Trace the discrete LM324/BCP53-16 line interface on the 7530 PCB/service
   manual: audio in/out, hook sense, line feed, ring drive and SC14448
   GPIO/PWM/ADC connections.
4. On a stock 7530, capture read-only TDM/MBOX frames during hook/ring/line
   transitions and compare slot 5 with `pcmlink` virtual-register writes.
5. Port the QCA ADSS/PCM/MBOX backend to Linux 6.12 and validate PCM DMA
   without FON control first.
6. Only then implement the minimal FON control/ALSA module in `src/fon-driver/`.
