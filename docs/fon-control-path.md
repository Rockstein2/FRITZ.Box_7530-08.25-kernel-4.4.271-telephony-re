# FON control path and the Dialog SC14448 hypothesis

Status: stage 4 static/board-evidence analysis. No router was accessed, no
AVM module was loaded, and no driver code was written.

## 1. Hypothesis and verdict

The hypothesis under test was:

> The FON port is an LM324 analog path plus the built-in audio codec of the
> Dialog SC14448; it is not a separate SPI/I2C SLIC.

The result is **largely supported at board level, but the control/audio
transport is still unproven**.

Supported:

- The 7530 FON PHY is **discrete/analog**, not a standard Linux SPI/I2C/GPIO
  SLIC. Public board inventories list **LM324** and **BCP53-16** as the FON
  chips; the 14-pin device near the DECT antenna is the **LM324** quad op-amp.
  No separate SLIC IC is listed or identified. The "SLIC" in the AVM software
  is a logical channel built around this discrete line interface.
- The **SC14448** is the only intelligent telephony IC on the board with a
  dual audio codec, a 6-channel PCM+ interface, ADC/opamps for line sensing,
  and GPIO. It is a plausible codec/line controller for the analog port.
- FON control in the AVM kernel stack is **not** a UART protocol to the
  SC14448. It is the `pcmlink` virtual-register bank (0x40, 0x44, 0x48, 0x4c,
  0x50). `Piglet_noemif` and `avm_dect` contain no FON/SLIC API.

Not proven:

- The exact transport from the `pcmlink` virtual-register bank to the physical
  FON PHY.
- Whether the SC14448 firmware participates in FON line/ring control.
- The exact discrete LM324/BCP53 line-feed/ring topology and component values.
- Whether the SC14448 PCM+ interface carries FON audio, DECT audio only, or
  both.

Consequence for the project:

> A small independent Linux module is still **CONDITIONAL**, but the Dialog
> hypothesis adds a new hard condition: if FON control or audio depends on
> SC14448 firmware, the module must either implement the PCM+ mailbox protocol
> to that firmware or bypass the SC14448 in hardware. Neither is currently
> proven possible on the stock board.

## 2. Board-level evidence

Public board data, not a vendor schematic:

| Item | Evidence | Most likely role | Confidence |
|---|---|---|---|
| Dialog SC14448-B96R101QNC | BoxMatrix 7530 chip list; Renesas SC14448/SC14441 family datasheets | DECT baseband, dual codec, 6-channel PCM+, GPIO/ADC/opamps | high presence, medium FON role |
| LM324 (14-pin) | BoxMatrix 7530 FON chip list; board-owner inspection | quad op-amp: audio buffer, line sensing, line-driver/ring support | high presence, medium role |
| BCP53-16 | BoxMatrix 7530 FON chip list | 1.5 A PNP: line-feed/ring/power switch | high presence, low role |
| WE-40799-LF1 | BoxMatrix 7530 FON transformer list | common-mode choke / line filter | high |
| Separate SLIC IC | no such chip listed/identified in the board inventory; no such driver in the AVM stack | FON PHY is a discrete circuit, not an SPI/I2C SLIC | medium-high |
| Separate SPI/I2C SLIC driver | no such driver or import in the AVM stack | not the control architecture | high |

The community inventory is useful because it records what is physically on
the board, but it is not a substitute for a schematic. The 14-pin device
seen in the teardown is the LM324. The remaining board-level uncertainty
is the **discrete high-voltage/line-feed/ring topology**, not the identity of
a separate SLIC chip.

### 2.1 Why the SC14448 is plausible

The SC14448/SC14441 family provides:

- dual 8/16/32 kHz 16-bit audio codecs;
- a 6-channel PCM+ interface (I2S-compatible, master or slave);
- a 10-bit ADC for line interface, battery and temperature;
- opamps for caller-ID, ringing and parallel-set detection;
- GPIO, UART, SPI, I2C, ACCESS and PWM/timer blocks;
- no high-voltage FXS line driver.

The last point is important: the SC14448 cannot directly generate the battery
and ringing voltages of an FXS port. A discrete line-feed/ring network is
still required. The LM324 + BCP53-16 inventory is exactly such a discrete
network; the 14-pin device is the LM324, not a separate SLIC module. The
remaining question is how the discrete network is wired and which SC14448
GPIO/PWM/ADC pins (or which PCM+ mailbox commands) control it.

The SC14441 family also has a low-voltage PSTN/line interface (hook-switch
output, line-current/polarity ADCs, ringing input). That is primarily an FXO
feature set, not proof that the 7530's FXS port is handled by the same pins.
It does show that the family is intended to connect to analog line hardware.

### 2.2 The likely control chain after identifying the 14-pin device

With the 14-pin device identified as the LM324 and no separate SLIC/CPLD/FPGA
identified in the public inventory, there is no known standalone digital SLIC
controller on the FON side. `pcmlink` also has no QCA GPIO path for SLIC
reset/ring/hook. The only known plausible digital agent between the Linux host
and the discrete LM324/BCP53-16 line interface is therefore the **SC14448**.

The most likely architecture is:

```text
pcmlink virtual registers 0x40/0x44/0x48/0x4c/0x50
  -> QCA TDM/PCM+ frame or shared-memory mailbox
  -> SC14448 firmware
  -> SC14448 GPIO/PWM/ADC pins
  -> discrete LM324/BCP53-16 line/ring circuit
  -> TAE/RJ11
```

This is a strong inference from the board inventory and the absence of any
other digital controller, but it is **not yet proven**. The exact mailbox
protocol and pin mapping are still unknown.

## 3. Kernel call graph

### 3.1 `isdn_fbox_fon5.ko`

The analog state machine is in this module. The hardware-facing calls are all
`pcmlink_*`:

```text
Analog_Timer_Handler
  -> HandleAnalog                        0x3ca80
       -> [controller+0x2e0] = Handle_Ints_FPGA   0x41058
            -> slic_get_hook_state     0x4093c
                 -> pcmlink_ul_readregister(0x44)
                 -> bit 7 for SLIC0
            -> pcmlink_ul_readregister(0x48)
            -> toggle bits 5/6 of register 0x48
            -> pcmlink_ul_writeregister(0x48, value, 0x60)
       -> [controller+0x304] = SetStatusLED_FPGA
```

`Handle_Ints_FPGA` is legacy-named but is used by the non-FPGA path. It both
samples the hook state and toggles the ring bits. This is software-generated
ring cadence/phase, not a single "ring enable" register write.

Other relevant functions:

```text
slic_set_ring          0x408d0
  SLIC0: register 0x48, mask 0x0060, bit 5 = ring_on, bit 6 = ring_state
  SLIC1: register 0x48, mask 0x0600, bits 9/10
  SLIC2: register 0x48, mask 0x6000, bits 13/14

slic_get_hook_state    0x4093c
  register 0x44, SLIC0 bit 7, SLIC1 bit 11, SLIC2 bit 15

slics_reset            0x40994
  writes registers 0x40, 0x48, 0x4c and 0x50 during bring-up

Get_POTS_LineState_FPGA 0x4179c
  reads registers 0x48, 0x44 and 0x50 and decodes line state

Set_POTS_Line_FPGA     0x419c4
  writes register 0x48 for line state and calls PCMRoute_* for audio routing
```

The exact bit meanings beyond hook and the two ring bits are not fully
decoded. The important result is that `isdn_fbox_fon5` never touches a UART,
SPI, I2C or GPIO controller directly.

### 3.2 `pcmlink.ko`

`pcmlink` owns the virtual register bank and the TDM/PCM link. The QCA
backend is `ipq40xxtdm_*`:

```text
ipq40xxtdm_linkinit      0x9e40
ipq40xxtdm_linkactivate  0x9dd4
ipq40xxtdm_linkdeactivate 0xa37c
ipq40xxtdm_linkdeinit    0xa334
ipq40xxtdm_linkpoll      0xa1fc
```

`ipq40xxtdm_linkinit` calls the missing vendor API:

```text
tdm_if_config_init(...)
tdm_if_dma_init(..., TxData, RxData, ..., 16 descriptors)
```

The QCA operation table is in `.rodata` at offset `0x17ac` and has 14
pointers:

```text
preinit, init, activate, deactivate, deinit, postexit, poll,
suspendresume, checkhw, debug, clkchange, rxirqcount,
rxirqcountreset, dmadescriptorcount
```

`pcmlink_ll_set_status` calls vtable offset `+0x3c`, which is **outside** that
14-entry table. On the QCA backend the call therefore returns `-1`. This is an
important correction to the earlier assumption: the QCA FON control path is
**not** proven to be `pcmlink_ll_set_status`.

`pcmlink_ll_trigger_control` instead raises an IPI/wake-up through the link
handle, and the shared-memory descriptor carries TX/RX slot data and control
buffers. The missing piece is the implementation behind `tdm_if_*` and the
remote/shared-memory side. It may program a control slot for the SLIC, or it
may exchange a mailbox with the SC14448; the Linux-side module does not expose
which.

`ipq40xxtdm_checkhw` only looks up the six `gpio_avm_pcmlink_*` TDM pins and
uses `dakota_gpio_ctrl` on those pins. There is no QCA GPIO path for a SLIC
reset, ring or hook signal in `pcmlink`. This is consistent with SLIC control
being carried inside the TDM/PCM stream (or handled entirely on the SC14448
side), not with a QCA GPIO bit-bang.

## 4. UART and the Dialog firmware loader

### 4.1 What uses UART

Only `Piglet_noemif.ko` imports the Dialog UART:

```text
msm_dectuart_init
msm_dectuart_get_char
msm_dectuart_put_char
msm_dectuart_exit
```

`Piglet` exports only DECT/loader functions:

```text
dect_file_process
dect_requestinit
dect_requestrelease
piglet_requestinit
piglet_requestrelease
piglet_reset
dectuart_sniffer_*
dectuart_event_dim_led_status_*
```

It exports no generic UART send/receive API. `pcmlink`, `isdn_fbox_fon5` and
`avm_dect` import no UART symbols at all. `avm_dect` uses only the
`pcmlink_ul_*dectcontrol*` and PCM-slot APIs.

### 4.2 Are there separate FON messages over UART?

No such path exists in the available kernel modules:

- `isdn_fbox_fon5` calls `pcmlink_ul_readregister`/`writeregister`, not UART.
- `pcmlink` has no UART import and no FON UART code.
- `Piglet` owns the UART but exposes no FON control API.
- `avm_dect` owns the DECT stack but has no FON/SLIC imports or exports.

The UART is a **firmware-loading/debug path** for the SC14448, not a runtime
FON control bus. After `Piglet` has loaded the DECT firmware, no module sends
FON hook/ring/line commands over that UART.

`Piglet` also has optional `piglet_potsbitfile` and `te_pots_mode` parameters.
Those belong to the FPGA/POTS variants. The 7530 runs `abmode=1` (SLIC1, no
FPGA/POTS; boot log `Pots=0`), so they are not the 7530 FON path.

## 5. PCM: DECT only, or also FON?

The stock boot log is:

```text
PCMLINK: Codecslots=6 Slics=1 Pots=0 TE=0 NT=0 DECT=4 no HwCross DSP-EC: 0
```

The codec-channel tables in `pcmlink` separate DECT and SLIC channels:

```text
DECT codec channels: slots 0..3
SLIC/POTS channels:  slots 4/5 (SLIC_LPCM variant uses slot 5)
```

This is logical separation inside `pcmlink`: the FON path is the **SLIC**
codec channel, not one of the four DECT channels. It does not prove which
physical block or codec owns the FON channel.

The SC14448 PCM+ interface has six channels and is I2S-compatible. A
six-slot PCM bus can carry four DECT channels plus one FON/SLIC channel plus
one spare/control channel, which matches the boot log. Therefore the SC14448
PCM+ interface is **not necessarily DECT-only**. The likely possibilities are:

1. The SC14448's second audio codec is the FON codec; the same PCM+ bus carries
   DECT and FON channels. This is now the most likely option because there is
   no separate SLIC/codec IC in the board inventory.
2. A separate codec (not an SLIC) sits on the same PCM bus; the SC14448 is
   only the DECT participant.
3. The discrete LM324/BCP53 network performs only analog line/ring functions;
   the SC14448 or another codec digitizes the audio.

The available software does not distinguish these. There is no kernel path
that sends FON audio through `avm_dect` or the DECT firmware. If the SC14448
does carry FON audio, it is transparent PCM data, not a DECT control message.

## 6. Dialog firmware inspection

### 6.1 Method

The local firmware images were parsed as Intel HEX and disassembled as CR16C
with a locally built `cr16-elf` binutils 2.42. This is static inspection only;
no firmware was executed. The images are AVM's DECT firmware files, not a
SC14448 datasheet or SDK.

Firmware block layout (first/second-level images):

```text
first-level  0x010080  618 bytes   entropy 5.91
second-level 0x000000  213 bytes   header/tables
             0x0000d6  477 bytes
             0x0002b4  6138 bytes
             0x0024f8  6150 bytes
             0x009000  875 bytes
             0x009c5e  930 bytes
             0x017300  2938 bytes
             0x017fe0  24 bytes
             0x020000  36302 bytes
```

The images contain code/data, not encrypted blobs: entropy is about 6-6.8 in
the code blocks, and the disassembly is coherent CR16C. The firmware has no
ASCII symbol/string table, so names such as `SLIC`, `POTS` or `hook` cannot be
used as evidence either way.

### 6.2 What the disassembly shows

- The first-level image is a UART bootstrap. It initializes and polls
  `0xFF4900/02/04/06` (UART control/data/clear), configures GPIO direction at
  `0xFF4836`, and implements a byte/checksum upload loop. It contains no FON
  line/ring logic.
- The second-level image contains the DECT application. It accesses:
  - UART `0xFF4900..0xFF4906`;
  - GPIO ports `0xFF4830..0xFF4868`;
  - interrupt controller `0xFF5400..0xFF540A`;
  - PCM/DMA-related `0xFF6006/0xFF600E`;
  - radio/analog front-end `0xFF7052/0xFF7056`;
  - timer/clock and other DECT peripherals.
- The code has DECT slot/frame handling and PCM setup. No clearly isolated
  FXS hook/ring/line-feed routine was identified. The SC14448 register map is
  not public in the available short datasheet, so absence of a named routine
  is **not proof** that FXS code is absent.

### 6.3 What can be concluded

The firmware is loaded by the DECT loader and is used by the DECT stack. The
kernel call graph gives no path by which `isdn_fbox_fon5` sends FON control
messages to this firmware. The only plausible interaction is transparent PCM
(or an undocumented PCM+ mailbox). A separate FON UART protocol is not
supported by the modules.

The firmware could still implement FON line control if it receives commands
through a PCM+ control channel. That would be a **firmware-mediated FON
controller**, and it would be a hard dependency for an independent driver.
This remains unproven.

## 7. High-voltage line feed and ringing

The FON control registers are logic-level, not high-voltage analog outputs:

```text
0x44 bit 7   hook/status (SLIC0)
0x48 bits 5/6 ring/line control (SLIC0)
0x40/0x4c/0x50 other line/reset/status bits
```

`slic_set_ring` sets bits 5/6. `Handle_Ints_FPGA` toggles both bits while the
line is in the ringing state. This is consistent with a logic-controlled
discrete line interface (or a small H-bridge/ring-generator), not with a
register that directly sets a 48 V/90 V analog level.

The high-voltage generation must therefore be external:

- LM324 is a low-voltage quad op-amp. The 14-pin device near the DECT antenna
  is this LM324, so it is not a separate SLIC or ringing module.
- BCP53-16 is a 1.5 A PNP transistor, not a ringing generator by itself.
- The remaining possibilities are a discrete boost/ring converter using the
  PNP, op-amps, inductors/capacitors and the line transformer, or a separate
  high-voltage module that is not in the public chip inventory.
- The exact discrete topology is unresolved. No software-visible regulator,
  reset GPIO or ring-enable GPIO is present in `isdn_fbox_fon5`; the control
  must therefore come from the SC14448 side or the TDM/PCM control stream.

The 14-pin device is the LM324, so there is no separate 14-pin SLIC module.
The FON line interface is a discrete design.

## 8. What is proven, likely, and unknown

### Proven by static analysis / board inspection

- `isdn_fbox_fon5` controls FON through `pcmlink` virtual registers
  0x40/0x44/0x48/0x4c/0x50.
- Hook is register 0x44 bit 7 for SLIC0.
- Ring/line bits are register 0x48 bits 5/6 for SLIC0; the ring bits are
  toggled by `Handle_Ints_FPGA`.
- `pcmlink` uses the QCA `ipq40xxtdm_*` backend and the missing `tdm_if_*`
  API; the QCA operation table has no `set_status` slot at `+0x3c`.
- `Piglet`/`avm_dect` provide no FON/SLIC control API and do not import a
  generic UART transport.
- The first-level Dialog firmware is a UART bootstrap; the second-level image
  is DECT/PCM code, not a separately addressable FON driver.
- The 14-pin device near the DECT antenna is the LM324; there is no separate
  SLIC IC in the public board inventory.

### Likely

- The FON PHY is a discrete analog line interface built around LM324 and
  BCP53-16, not a standard SPI/I2C SLIC. The 14-pin device is the LM324, not
  an SLIC module.
- The SC14448 is involved in the FON audio path or line control, because it is
  the only telephony IC with a codec, ADC, GPIO and PCM+ interface. With no
  other identified digital controller, the likely chain is `pcmlink -> PCM+
  mailbox -> SC14448 firmware -> GPIO/PWM/ADC -> discrete line interface`.
- The six PCM+ channels carry four DECT channels and one FON/SLIC channel.

### Unknown

- Exact discrete LM324/BCP53 line/ring topology and component values.
- Which SC14448 GPIO/PWM/ADC pins control the discrete line interface.
- The exact role/protocol of the SC14448 firmware in FON GPIO/ring/line
  control (likely involved, not proven).
- The transport between QCA/`pcmlink` and the FON PHY (TDM control slot,
  shared-memory mailbox, PCM+ mailbox, or something else).
- Whether FON audio uses the SC14448 codec or another codec on the PCM bus.
- High-voltage battery/ring generation topology.
- Safe ring voltage/cadence limits and reset/regulator wiring.

## 9. Consequence for a standalone driver

A small independent module would need one of these architectures:

| Route | What is required | Verdict |
|---|---|---|
| Reimplement `pcmlink` + QCA TDM | QCA ADSS/TDM/DMA programming, `tdm_if_*` equivalent, FON control transport | hard, 3-6 months |
| Talk to SC14448 over PCM+ mailbox | PCM+ protocol, firmware command set, GPIO/audio mapping | most likely route; firmware protocol unknown |
| Bypass SC14448 | QCA GPIO/PCM directly to the discrete LM324/BCP53 line circuit | requires board rework/schematic; not stock |
| Keep AVM `pcmlink`/Dialog firmware | not independent; out of project scope | rejected |

ALSA SoC is still the preferred audio framework once a QCA TDM/DMA backend
exists. DAHDI would not remove the backend or firmware dependency.

The project therefore remains **CONDITIONAL GO**, but the Dialog hypothesis
makes the condition stricter:

1. Prove that FON control/audio can be driven without SC14448 firmware, **or**
   recover enough of the PCM+ mailbox protocol to drive the stock firmware.
2. Trace the discrete LM324/BCP53 line interface to the SC14448 GPIO/PWM/ADC
   pins (or to the QCA TDM control stream) and recover the high-voltage/ring
   topology.
3. Recover the QCA TDM/ADSS/DMA programming.
4. Validate hook/ring/line feed on a safe bench before connecting a telephone.

If item 1 or 2 cannot be satisfied, a small independent module is **NO-GO**.
With no separate SLIC IC identified, the SC14448 firmware dependency is now
the central risk: the Linux side may have no direct pin-level access to the
line interface.

## 10. Next evidence to collect

1. Board schematic or continuity check of the LM324, BCP53-16, the line
   transformer and the SC14448 GPIO/PWM/ADC pins; do not power the line for
   this.
2. AVM GPL source for FRITZ!OS 08.25: `pcmlink_ll.c`, `tdm_if_*`,
   `ipq40xxtdm_*`, `isdn_fon5` SLIC/FON code.
3. A read-only trace of `pcmlink_ul_writeregister(0x40/0x44/0x48/0x4c/0x50)`
   during hook/ring transitions on a stock box.
4. A read-only trace of the QCA TDM shared-memory descriptor and any PCM+
   control slots during the same transitions.
5. A CR16C/Ghidra analysis of the second-level firmware with the SC14448
   peripheral map, focused on the PCM+ interrupt handler and GPIO writes.
6. A safe dummy-load bench test of the discrete line/ring circuit before any
   telephone is connected.

## 11. Sources

```text
reference/init.d/E41-capi
reports/pcmlink.disasm.txt
reports/imports/pcmlink.txt
reports/imports/isdn_fbox_fon5.txt
reports/imports/avm_dect.txt
reports/imports/Piglet_noemif.txt
reports/exports/Piglet_noemif.txt
reports/functions/isdn_fbox_fon5.txt
firmware/dectfw_firstlevel_441_slow.hex
firmware/dectfw_secondlevel_441.hex
firmware/dectfw_secondlevel_441p2test.hex
docs/fon-hardware.md
docs/fon-avm-analysis.md
docs/fon-feasibility.md

BoxMatrix FRITZ!Box 7530 board inventory:
https://boxmatrix.info/wiki/FRITZ!Box_7530
BoxMatrix FON chip lists:
https://boxmatrix.info/wiki/Property:LM324
https://boxmatrix.info/wiki/Property:BCP53-16

IP-Phone-Forum 7530 teardown thread (photo/location of the 14-pin device):
https://www.ip-phone-forum.de/threads/sammelthema-zur-avm-fritz-box-7530-sowie-7520-und-7530-ax.299746/page-2
Board-owner inspection (2026-11-01): the 14-pin device is the LM324.

Renesas SC14448 / SC14441 family short datasheets:
https://www.renesas.com/en/products/sc14448
https://www.renesas.com/en/document/sds/sc14441abc-sc14442a-short-form-datasheet
RTX1040 SC14441 module specification (line-interface pin example):
https://www.mikrocontroller.net/attachment/205108/RTX1040ProductSpecification_v2.5.pdf
```
