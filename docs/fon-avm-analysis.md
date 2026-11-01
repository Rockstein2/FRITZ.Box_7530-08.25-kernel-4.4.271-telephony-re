# AVM FON kernel-module analysis

Status: stage 2 static analysis. No router was accessed, no module was loaded.
Addresses are module-relative ELF offsets.

## 1. Modules in scope

```text
isdn_fbox_fon5.ko   CAPI/analog-FON control, SLIC line/ring/hook logic
pcmlink.ko          TDM/PCM link, slot router, SLIC virtual registers, DMA
capi_codec.ko       CAPI codec/DSP layer (not required for basic PCM)
dect_io.ko          DECT-only; out of scope
avm_dect.ko         DECT stack; out of scope
nlaudio.ko          optional audio netlink; out of scope
krtp.ko             RTP acceleration; out of scope
ulpcmlink.ko        remote PCM transport; out of scope
```

`isdn_fbox_fon5` declares `depends=pcmlink`. `capi_codec` is loaded after
`isdn_fbox_fon5` in `E41-capi`, but the analog line can be brought up without
CAPI or codec DSP for basic 8 kHz PCM.

## 2. Dependency and data-flow graph

```text
userspace (telefon / voipd / CAPI)
        |
        | CAPI / /dev/dect_io (not required for a standalone FON driver)
        v
isdn_fbox_fon5.ko
  |        |            |
  |        |            +--> PCMRoute_* / pcmlink slot API
  |        |
  |        +--> pcmlink_ul_readregister / writeregister (SLIC control)
  |
  +--> pcmlink_ul_register_pcmrouter / rxget / txput / txalloc / rxfree
        |
        v
pcmlink.ko
  |        |             |
  |        |             +--> pcmroute_* / gPcmroute
  |        |
  |        +--> pcmlink_ll_* (link backend)
  |
  +--> tdm_if_config_init / tdm_if_dma_init / tdm_if_dma_start
        |
        v
QCA IPQ4019 TDM/PCM + DMA + ADCC
        |
        v
single SLIC (part unknown) + DECT codec slots
```

## 3. Hardware-significant functions

### 3.1 `isdn_fbox_fon5.ko`

| Address | Function | Role | Needed for FON? |
|---:|---|---|---|
| `0x3b680` | `InitAnalog` | init analog controller, FPGA/POTS function table, V23 | yes, partially |
| `0x3b850` | `HookStateAnalog` | return cached hook byte `+0x308` | yes |
| `0x3b860` | `StartAnalog` | start analog timers and 4-channel state | yes |
| `0x3ba30` | `ResetAnalog` | reset analog controller, V23Deinit | yes |
| `0x3ca80` | `HandleAnalog` | main analog state machine/timer handler | yes |
| `0x3dc20` | `Set_TimeslotAnalog` | bind codec slot to TDM timeslot | yes |
| `0x3dd58` | `GetSlicErrorAnalog` | read SLIC error via controller callback | yes |
| `0x3e26c` | `AnalogCodecReq` | CAPI codec request (0x8100..) | no for basic PCM |
| `0x3e694` | `AnalogCodecInd` | CAPI codec indication (0x8100..) | no for basic PCM |
| `0x408d0` | `slic_set_ring` | ring bits in virtual register 0x48 | yes |
| `0x4093c` | `slic_get_hook_state` | hook bit in virtual register 0x44 | yes |
| `0x40994` | `slics_reset` | SLIC reset/bring-up sequence | yes |
| `0x40cb0` | `pots_reset` | POTS/FPGA variant reset | no on 7530 |
| `0x40e60` | `Init_FPGA` | detect/support FPGA/POTS, call `slics_reset` | partly yes |
| `0x412e8` | `Init_POTS_FPGA` | POTS/FPGA variant init | no on 7530 |
| `0x4179c` | `Get_POTS_LineState_FPGA` | read line state from regs 0x44/0x48/0x50 | yes |
| `0x419c4` | `Set_POTS_Line_FPGA` | line feed/ring/audio routing state machine | yes |
| `0x3a25c` | `Analog_CPU_Init` | analog timer init | yes |
| `0x3a284` | `Analog_CPU_Activate` | start analog timer | yes |
| `0x3a200` | `Analog_Timer_Handler` | periodic analog poll | yes |

### 3.2 `pcmlink.ko`

| Address | Function | Role | Needed for FON? |
|---:|---|---|---|
| `0x3444` | `pcmlink_ul_readregister` | read virtual SLIC/control register | yes |
| `0x3b60` | `pcmlink_ul_writeregister` | write virtual SLIC/control register | yes |
| `0x30e0` | `pcmlink_ul_status` | query link status | yes |
| `0x23f0` | `pcmlink_ul_register_pcmrouter` | init manager, map DSP shared memory | yes |
| `0x1a50` | `pcmlink_ul_rxget_slotdata_pcmrouter` | get RX PCM slot buffer | yes |
| `0x1b3c` | `pcmlink_ul_txput_slotdata_pcmrouter` | put TX PCM slot buffer | yes |
| `0x2338` | `pcmlink_ul_txalloc_slotdata_pcmrouter` | allocate TX slot buffer | yes |
| `0x2290` | `pcmlink_ul_rxfree_slotdata_pcmrouter` | free RX slot buffer | yes |
| `0x1c00` | `pcmlink_ul_setslotparam_pcmrouter` | configure slot params | yes |
| `0x2114` | `pcmlink_ul_release_pcmrouter` | release manager | yes |
| `0x9e40` | `ipq40xxtdm_linkinit` | QCA TDM init, GPIO, `tdm_if_config_init`/`dma_init` | yes |
| `0x9dd4` | `ipq40xxtdm_linkactivate` | `tdm_if_config_init` + DMA start | yes |
| `0xa334` | `ipq40xxtdm_linkdeinit` | DMA/config exit | yes |
| `0xa37c` | `ipq40xxtdm_linkdeactivate` | DMA stop | yes |
| `0xa1fc` | `ipq40xxtdm_linkpoll` | DMA IRQ stall detection | yes |
| `0x8f68` | `build_slic_ctrl` | build 16-bit FPGA/SLIC control word | partly |
| `0x90b0` | `set_slic_ring_state` | per-SLIC ring state | yes |
| `0x9084` | `set_slic_ringfreq` | ring half-period | yes |
| `0x151a4` | `PCMRoute_SetTimeSlot` | route codec slot to TDM timeslot | yes |
| `0x15058` | `PCMRoute_Init` | init host router state | yes |
| `0x1340c` | `PCMRoute_Exit` | exit router/slot lists | yes |

### 3.3 `capi_codec.ko`

`capi_codec` provides CAPI codec/DSP helpers (`BLK_*`, `capi_codec_*`,
`Codec_*`). It is **not required** for a minimal 8 kHz PCM path unless a
specific compression format is required. The stock log shows `DSP-EC: 0`, so
no hardware echo canceller is active.

## 4. Control-plane chain

### 4.1 Hook

```text
HandleAnalog / Get_POTS_LineState_FPGA
  -> pcmlink_ul_readregister(0x44)
       -> lpcmlink_ul_readregister
            -> pcmlink_ul_manager register bank
  -> bit 7 for SLIC0
  -> HookStateAnalog cached byte +0x308
```

Evidence: `slic_get_hook_state` at `0x4093c`; `Get_POTS_LineState_FPGA` at
`0x4179c` reads `0x48`, `0x44`, `0x50`.

### 4.2 Ring

```text
FON state machine
  -> slic_set_ring(slic, ring_on, ring_state)
       -> pcmlink_ul_writeregister(0x48, value, mask)
            -> register bank
  -> pcmlink set_slic_ring_state / set_slic_ringfreq
       -> ring bitmask / half-period count
  -> link backend status/control stream
```

For SLIC0: bits 5/6 of register `0x48`. For SLIC1: bits 9/10. For SLIC2:
bits 13/14.

### 4.3 Line feed / on-hook / off-hook

`Set_POTS_Line_FPGA` handles line states. For the non-POTS path it writes
register `0x48` with line-state values and calls:

```text
PCMRoute_SetTimeSlot
PCMRoute_RxOff / TxOff
PCMRoute_NoiseCanceller
PCMRoute_SetSlotFeatureParam
PCMRoute_RestoreRxTimeSlot
```

The exact state values are encoded in the line-state jump table at
`0x41b10`. The important fact is that **line feed and audio routing are
coupled** through `PCMRoute_*`.

## 5. Audio-plane chain

```text
isdn_fbox_fon5
  -> Set_TimeslotAnalog (controller+0x2f4 = Set_POTS_Timeslot_FPGA)
  -> PCMRoute_SetTimeSlot(codec_slot, tdm_slot, ...)
  -> pcmlink_ul_txalloc/rxget/txput/rxfree
       -> descriptor+0x24 table entry (0x14 bytes)
       -> descriptor+0x38 TX buffer or +0x3c RX buffer
  -> pcmlink_ul_handler
       -> descriptor+0x28 control buffer, descriptor+0x2c length
  -> pcmlink_ll_* trigger/status
  -> tdm_if_config_init / tdm_if_dma_init / tdm_if_dma_start
  -> QCA TDM/PCM + DMA
```

`pcmlink_ul_register_pcmrouter` (`0x23f0`) maps the descriptor:

```text
manager+0x224 = host address of descriptor+0x24
manager+0x228 = host address of descriptor+0x38
manager+0x22c = host address of descriptor+0x3c
manager+0x230 = host address of descriptor+0x28
manager+0x234 = descriptor pointer
manager+0x238 = pcmrouter callback argument
```

`pcmlink_ul_txalloc` returns `manager+0x228 + entry+0x08`;
`pcmlink_ul_rxget` returns `manager+0x22c + entry+0x08`.

## 6. Required hardware resources

| Resource | Where used | Notes |
|---|---|---|
| TDM FSC/FSC_2 | `ipq40xxtdm_linkinit` | six-pin table, GPIO numbers from `hw_config` |
| TDM DCL/DCL_2 | same | bit clock |
| TDM DI/DO | same | data in/out |
| TDM/PCM register block | `tdm_if_*` | IPQ4019 `0x7709000` |
| TDM DMA | `tdm_if_dma_init` | 16 descriptors |
| TDM IRQ / poll | `tdm_if_dma_irqcnt`, `ipq40xxtdm_linkpoll` | 0x7d-jiffy stall check |
| Audio clocks | ADCC | `audio_tx_bclk/mclk`, `audio_rx_bclk/mclk` |
| SLIC control | virtual regs 0x40/0x44/0x48/0x4c/0x50 | transport inside `tdm_if_*`/backend |
| SLIC reset | `slics_reset` | exact GPIO/regulator unknown |
| Hook | reg 0x44 bit 7 | polled via analog timer/state machine |
| Ring | reg 0x48 bits 5/6 | `set_slic_ring_state/freq` |

## 7. What can be excluded for a single FON port

```text
DECT stack and DECT firmware
ISDN TE/NT2
POTS/FPGA/PEF variants
CAPI application layer
telefon / voipd / call routing
RTP acceleration (krtp)
remote PCM (ulpcmlink)
netlink audio (nlaudio)
full PCMRoute codec/EC/DTMF/FFT code
```

The minimal set is:

```text
SLIC line/ring/hook control
one codec slot mapped to one TDM timeslot
16-bit TDM RX/TX with 16 DMA descriptors
```

## 8. Functions that must be reimplemented

```text
SLIC virtual-register transport (currently inside pcmlink/tdm_if_*)
SLIC reset/bring-up sequence
hook/line-state polling
ring cadence/frequency control
codec-slot to TDM-timeslot routing
QCA TDM/DMA backend (tdm_if_* equivalent)
ALSA SoC DAI/PCM or a small character-device PCM interface
```

## 9. Reuse candidates

Reusable as documentation/algorithm, not as loadable code:

```text
virtual register numbers and bit positions
line-state and ring state machine
PCM slot model (0x14-byte descriptor)
G.722/other codec helpers if needed
PCMRoute routing logic
```

## 10. Open questions

1. Exact SLIC part and datasheet.
2. Exact SLIC reset GPIO/regulator/clock wiring.
3. Complete virtual-register bit map beyond hook/ring.
4. Exact `tdm_if_*` implementation and QCA ADSS register programming.
5. Real 7530 TDM GPIO numbers.
6. Whether basic 8 kHz PCM needs any closed DSP firmware.

## 11. Sources

```text
reports/functions/isdn_fbox_fon5.txt
reports/imports/isdn_fbox_fon5.txt
reports/imports/pcmlink.txt
reports/symbols/isdn_fbox_fon5.txt
reports/symbols/pcmlink.txt
notes/pcmlink.md
notes/pcmlink-sharedmem.md
notes/avm_dect.md
docs/fon-hardware.md
```
