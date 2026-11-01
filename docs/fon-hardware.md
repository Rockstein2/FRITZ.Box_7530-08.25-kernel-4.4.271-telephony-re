# FON hardware architecture — FRITZ!Box 7530

Status: stage 1 static analysis. No router was accessed, no module was loaded.

## 1. Scope and method

This document answers the hardware questions needed before writing an
independent FXS driver:

- what controls the analog FON port;
- whether it is a separate SPI/I2C SLIC or an AVM-specific interface;
- where PCM/TDM audio comes from;
- which clocks, GPIOs, IRQs and DMA resources exist;
- which parts are already supported by Linux 6.12.

Sources used:

```text
reference/init.d/E41-capi
modules/ubik2/pcmlink.ko          (local, not in git)
modules/isdn_fon5/isdn_fbox_fon5.ko (local, not in git)
reports/imports/, exports/, functions/, symbols/
notes/pcmlink.md, notes/avm_dect.md, notes/pcmlink-sharedmem.md
OpenWrt FRITZ!Box 7530 device support and dmesg log
QCA IPQ4019 public product brief and the 2016 IPQ4019 ASoC RFC
```

No AVM binary is included in this repository.

## 2. Confirmed platform facts

```text
SoC             Qualcomm IPQ4019, ARMv7 Cortex-A7
DECT baseband   Dialog SC14448 (not used by this project)
DSL AFE         Intel/Lantiq PSB 80518 / VRX518 (not used by this project)
Ethernet        QCA8075 (not used by this project)
FON             one analog FXS port (TAE/RJ11)
```

The FON port is not a second DECT interface. It is a separate analog line
interface managed by the AVM FON kernel stack.

## 3. Exactly one SLIC is configured

The stock init script loads `pcmlink` with `abmode=1`:

```sh
# reference/init.d/E41-capi
modprobe pcmlink abmode=1 $capi_force
modprobe isdn_fbox_fon5
modprobe capi_codec
modprobe dect_io
```

`pcmlink` documents `abmode` as:

```text
bit0  slic1 exists
bit1  slic2 exists
bit2  pots instead of slic2
bit3  pots (clare2) instead of slic2
bit4  nt2 replaces te
bit7  fpga
bit8  fpga2
bit9  pef
bit10 spitdm
bit11 slot-shift workaround
```

Therefore the 7530 configuration is:

```text
SLIC1 present
SLIC2 absent
POTS absent
NT2/TE absent
FPGA/FPGA2 absent
PEF absent
SPI-TDM option absent
```

This is independently confirmed by the stock boot log quoted in the OpenWrt
device page:

```text
[isdn]PCMLINK: Codecslots=6 Slics=1 Pots=0 TE=0 NT=0 DECT=4 no HwCross DSP-EC: 0
```

So the 7530 has:

```text
1 SLIC channel
4 DECT codec channels
6 codec slots total
no hardware cross-switch
no DSP echo canceller
```

## 4. What the SLIC part is — and what it is not

### Confirmed

- There is exactly one SLIC channel.
- The SLIC is controlled through AVM `pcmlink`, not through a dedicated
  Linux SPI/I2C/GPIO SLIC driver.
- `isdn_fbox_fon5.ko` does not import SPI, I2C, `gpiod_*`, `regmap` or
  `readl/writel`. Its hardware-facing imports are the `pcmlink_*` register,
  slot and PCM-route APIs.
- `pcmlink.ko` imports only `dakota_gpio_ctrl`, `dakota_gpio_get_membase` and
  `dakota_gpio_pinconfig` for GPIO; these are used for the six TDM pins
  (`gpio_avm_pcmlink_fsc/fsc_2/dcl/dcl_2/di/do`), not for a SLIC bus.
- The SLIC control path is a **virtual register bank**:
  `pcmlink_ul_readregister()` / `pcmlink_ul_writeregister()` accept register
  numbers up to `0x64`. `isdn_fbox_fon5` uses registers `0x40`, `0x44`, `0x48`,
  `0x4c` and `0x50` for line/ring/hook/status.
- The hardware transport for those virtual registers is inside the selected
  `pcmlink` link backend (`pcmlink_ll_set_status`, vtable `+0x3c`) and the
  vendor `tdm_if_*` layer. It is not exposed as a standard Linux bus.

### Not confirmed

The exact SLIC part number is **not present** in any string, symbol or
device-tree artifact available locally:

```text
no "Si321x", "Si3217x", "PEF", "LE58", "ZL880", "VE880",
   "Legerity", "Zarlink", "Silicon Labs" strings
no separate SLIC driver module
no SLIC node in the OpenWrt 7530 DTS
no SLIC entry in the public 7530 chip lists
```

The available public chip lists name only the Dialog SC14448 and the Lantiq
VRX518. The SLIC is either on the unphotographed side of the PCB or is part of
an AVM-specific line interface. It must not be assumed to be a particular
Silicon Labs/Infineon/Legerity part without board inspection or AVM GPL
source.

What can be said safely:

```text
The SLIC is a programmable single-channel FXS interface.
Its host-visible model is an AVM 16-bit control/status register bank
at virtual registers 0x40..0x50.
```

The register map and the 16-bit control word are consistent with a
programmable SLIC/ProSLIC class device, but a datasheet match is not proven.

## 5. Block diagram

```text
                    IPQ4019
 +------------------------------------------------------+
 |  Cortex-A7            QCA TDM/PCM + DMA + ADCC       |
 |                           |          |               |
 |                    tdm_if_* vendor   | clocks/reset  |
 |                           |          |               |
 |                    pcmlink.ko        |               |
 |                     |        |       |               |
 |          virtual regs|        | PCM/TDM slots          |
 |                     |        |                         |
 +---------------------|--------|-------------------------+
                       |        |
                 isdn_fbox_fon5  |
                       |        |
                 +-----v--------v-----+
                 |  single SLIC/FXS   |
                 |  (part unknown)    |
                 +---------+----------+
                           |
                        TAE/RJ11
                     analog telephone
```

The DECT Dialog SC14448 also shares the PCM/TDM/codec-slot infrastructure,
but it is outside this project.

## 6. Control plane

### 6.1 Virtual registers

`pcmlink` exposes a register bank to `isdn_fbox_fon5`:

```text
pcmlink_ul_readregister(reg)       0x3444
pcmlink_ul_writeregister(reg,val,mask) 0x3b60
```

Register numbers above `0x64` are rejected. The bank is held in
`pcmlink_ul_manager`; the link backend turns it into the hardware-specific
status/control stream.

### 6.2 Hook detection

`isdn_fbox_fon5.ko`, `slic_get_hook_state` at `0x4093c`:

```text
r0 = 0x44
bl pcmlink_ul_readregister
slic index 0 -> bit 7
slic index 1 -> bit 11
slic index 2 -> bit 15
```

So the hook state of the 7530's single SLIC is bit 7 of virtual register
`0x44`.

### 6.3 Ring control

`isdn_fbox_fon5.ko`, `slic_set_ring` at `0x408d0`:

```text
slic 0: write register 0x48, mask 0x0060, bits 5/6
slic 1: write register 0x48, mask 0x0600, bits 9/10
slic 2: write register 0x48, mask 0x6000, bits 13/14
```

`pcmlink` also contains:

```text
build_slic_ctrl        0x8f68
_buildslic_ctrl_ring   0x8fb0
set_slic_ring_state    0x90b0
set_slic_ringfreq      0x9084
slic_ring              global bitmask
```

`build_slic_ctrl` builds a 16-bit word with a `0x4000` marker, four bits from
`manager+0x24c`, and optional `0x10`/`0x200` flags from `manager+0x230`.
`set_slic_ringfreq` derives a half-period count from a 500 Hz reference and
the requested ring frequency; `set_slic_ring_state` updates a per-SLIC ring
bitmask and state.

### 6.4 Line feed and reset

`isdn_fbox_fon5.ko` contains:

```text
InitAnalog          0x3b680
StartAnalog         0x3b860
ResetAnalog         0x3ba30
HandleAnalog        0x3ca80
Set_TimeslotAnalog  0x3dc20
GetSlicErrorAnalog  0x3dd58
slics_reset         0x40994
pots_reset          0x40cb0
Set_POTS_Line_FPGA  0x419c4
Get_POTS_LineState_FPGA 0x4179c
```

For the non-POTS path, `Set_POTS_Line_FPGA` writes virtual register `0x48`
with line-state values and calls `PCMRoute_SetTimeSlot`, `PCMRoute_RxOff`,
`PCMRoute_TxOff`, `PCMRoute_NoiseCanceller`, etc. `Get_POTS_LineState_FPGA`
reads registers `0x48`, `0x44` and `0x50` and interprets line-status bits.

`slics_reset` (0x40994) performs the SLIC bring-up sequence:

```text
pcmlink_ul_status(...)
write register 0x48 = 0x1100070 (mask 0x1100000)
write register 0x40 = 0x1107770 (mask 0x1100000)
slic_set_ring for up to three SLIC instances
msleep(200)
read hook state
write registers 0x40, 0x48, 0x4c, 0x50 with status bits
```

The exact register bit meanings are not fully decoded, but the order and
register numbers are proven by disassembly.

## 7. Audio plane

### 7.1 TDM/PCM hardware

`pcmlink`'s QCA backend is `ipq40xxtdm_*`:

```text
ipq40xxtdm_linkinit      0x9e40
ipq40xxtdm_linkactivate  0x9dd4
ipq40xxtdm_linkdeactivate 0xa37c
ipq40xxtdm_linkdeinit    0xa334
ipq40xxtdm_linkpoll      0xa1fc
```

`ipq40xxtdm_linkinit` calls:

```text
tdm_if_config_init(slot_size, tx_slots, rx_slots, config)
tdm_if_dma_init(handle, TxData, RxData, 1, 1, slot_size,
                slot_ratio, 16)
```

with:

```text
slot_size = 8 or 16, 16-bit slots only in practice
DMA descriptors = 16
```

The IPQ4019 TDM/PCM block is at `0x7709000` in the QCA IPQ4019 address map.
The 2016 QCA ASoC RFC names the compatible strings
`qca,ipq4019-pcm-tdm`, `qca,ipq4019-tdm` and `qca,ipq4019-audio-adss`.

### 7.2 PCM slot model

`pcmlink` exposes four slot-data operations used by the FON stack:

```text
pcmlink_ul_rxget_slotdata_pcmrouter   0x1a50
pcmlink_ul_txput_slotdata_pcmrouter   0x1b3c
pcmlink_ul_txalloc_slotdata_pcmrouter 0x2338
pcmlink_ul_rxfree_slotdata_pcmrouter  0x2290
```

Each slot entry is `0x14` bytes in the DSP descriptor table at `+0x24`:

```text
+0x00  slot/selector (observed <= 0x1f)
+0x04  length
+0x08  offset into the TX (+0x38) or RX (+0x3c) buffer
```

`pcmlink_ul_handler` (`0x2e78`) copies received data from descriptor `+0x28`
using the length at descriptor `+0x2c`. `pcmlink_ul_txput` uses descriptor
`+0x60` as a TX slot bitmask; `pcmlink_ul_rxfree` uses `+0x64`.

### 7.3 Routing to the FXS line

`Set_TimeslotAnalog` (`0x3dc20`) calls the controller function pointer at
`+0x2f4` (the non-POTS path is `Set_POTS_Timeslot_FPGA`, currently a
`bx lr` stub at `0x41710`) and updates a per-slot bit at `controller+0x3ec`
bit 3. The real routing is done by `PCMRoute_SetTimeSlot` and the
`pcmlink_ul_*slotdata*` API.

`PCMRoute_SetTimeSlot` is `pcmlink 0x151a4`; it takes a codec slot and TDM
timeslot and updates the `gPcmroute` slot table.

### 7.4 What audio format is expected

- 16-bit TDM slots.
- 8 kHz narrowband is the normal FXS path.
- `pcmlink` contains G.722 and other codec helpers, but the stock log shows
  `DSP-EC: 0`; basic PCM does not require the DSP echo-canceller.
- The FON stack can route a codec slot to a TDM timeslot without CAPI, DECT or
  RTP.

## 8. Hardware resources

| Resource | Evidence | Status |
|---|---|---|
| TDM FSC/FSC_2 | `gpio_avm_pcmlink_fsc`, `..._fsc_2` | names known, numbers from `hw_config` |
| TDM DCL/DCL_2 | `gpio_avm_pcmlink_dcl`, `..._dcl_2` | names known, numbers from `hw_config` |
| TDM DI/DO | `gpio_avm_pcmlink_di`, `..._do` | names known, numbers from `hw_config` |
| TDM/PCM register block | QCA IPQ4019 `0x7709000` | documented in QCA material |
| TDM DMA | `tdm_if_dma_init`, 16 descriptors | vendor API missing |
| TDM IRQ | `tdm_if_dma_irqcnt`, `ipq40xxtdm_linkpoll` | vendor API missing |
| Audio clocks | ADCC `audio_tx_bclk/mclk`, `audio_rx_bclk/mclk` | QCA ADCC, no mainline TDM user |
| SLIC reset | no direct GPIO in `isdn_fbox_fon5`; `slics_reset` via virtual regs | exact pin unknown |
| SLIC IRQ | no direct IRQ; hook status polled/read via register `0x44` | no dedicated IRQ proven |
| SLIC regulator | not visible in available artifacts | unknown |
| DECT reset/UART | GPIO 18/16 and `msm_dectuart_*` | DECT only, out of scope |

The six TDM GPIO numbers are **not constants** in `pcmlink`; the module reads
them from the AVM `hw_config` table by logical name. The real 7530 values must
be read from the device tree/board data or from the running stock system.

## 9. Linux 6.12 support matrix

| Component | Linux 6.12 mainline | OpenWrt 6.12 target | Consequence |
|---|---|---|---|
| IPQ4019 pinctrl/GPIO | yes (`pinctrl-ipq4019`) | yes | usable for TDM pins |
| IPQ4019 clocks/reset | partial QCOM clock drivers | target-specific | TDM audio clocks need board data |
| IPQ4019 TDM/PCM + ADSS | no mainline driver | not present | must port/reimplement |
| QCA TDM DMA (`tdm_if_*`) | no | no | main blocker |
| I2S/SPDIF | separate QCA blocks | not the FON wiring | not a drop-in replacement |
| ALSA SoC core | yes | yes | usable once a DAI/DMA exists |
| DAHDI | out-of-tree | not installed | does not remove the TDM/DMA blocker |
| SLIC driver | none for this AVM virtual register interface | none | must implement or reuse recovered sequence |

The 2016 QCA IPQ4019 ASoC driver series (`ipq4019-adss.c`,
`ipq4019-pcm-tdm.c`, `ipq4019-cpu-dai.c`, `ipq4019-mbox.c`) was an RFC and did
not become a mainline driver. It is the closest known starting point for a
clean TDM/DMA backend.

## 10. Confirmed vs unconfirmed

### Confirmed

- The 7530 has exactly one SLIC channel (`abmode=1`; boot log `Slics=1`).
- There is no separate Linux SPI/I2C/GPIO SLIC driver in the AVM stack.
- SLIC control is a virtual register bank `0x40/0x44/0x48/0x4c/0x50`.
- Hook is register `0x44` bit 7 for SLIC0.
- Ring is register `0x48` bits 5/6 for SLIC0.
- PCM is 16-bit TDM with 16 DMA descriptors and six codec slots.
- The QCA TDM/PCM block is at `0x7709000`.
- The vendor `tdm_if_*` API is not in Linux 6.12.

### Unconfirmed / unknown

- Exact SLIC part number and datasheet.
- Exact SLIC reset GPIO/regulator/clock wiring.
- Complete virtual-register bit meanings.
- Whether the QCA TDM/ADSS driver can be ported cleanly to 6.12.
- Real 7530 TDM GPIO numbers.
- Whether any closed DSP firmware is needed for basic 8 kHz PCM (the stock log
  suggests no DSP echo canceller; basic PCM may be firmware-free).

## 11. Sources

```text
reference/init.d/E41-capi
reports/pcmlink.modinfo.txt
reports/isdn_fbox_fon5.modinfo.txt
reports/imports/pcmlink.txt
reports/imports/isdn_fbox_fon5.txt
reports/functions/isdn_fbox_fon5.txt
notes/pcmlink.md
notes/avm_dect.md
notes/pcmlink-sharedmem.md
OpenWrt FRITZ!Box 7530 device page (stock dmesg line)
QCA IPQ4019 product brief (TDM/PCM/I2S/SPDIF)
linux-arm-kernel 2016-07 IPQ4019 ASoC RFC (qca,ipq4019-pcm-tdm)
```
