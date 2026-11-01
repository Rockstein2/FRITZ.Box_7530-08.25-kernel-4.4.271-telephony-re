# `pcmlink.ko` — PCM/TDM hardware boundary

Static analysis of `modules/ubik2/pcmlink.ko` (ARM EABI5, FRITZ.OS 08.25,
kernel 4.4.271, not stripped). No module was loaded and nothing was written to
the router.

## 1. Role of the module

`pcmlink.ko` is the AVM PCM/TDM audio router. It is much more than a GPIO
adapter: it contains the QCA TDM backend, PCM slot routing, G.722 and other
codecs, echo cancellation, DTMF, FFT helpers, a debug socket, and the
`PCMRoute_*` API used by the ISDN/CAPI side.

Source paths embedded in the module:

```text
pcmlink_ll.c
pcmlink_ul.c
pcmlink_uldectctrl.c
pcmlink_socket.c
```

The module has no module dependency (`depends=` is empty), but the FRITZ load
order starts `pcmlink` before `dect_io`/`avm_dect` and before the ISDN/CAPI
driver.

Important exported groups:

```text
pcmlink_ll_*       low-level link, shared memory, trigger, PCM bus status
pcmlink_ul_*       upper-layer PCM router, slot allocation, DECT control
PCMRoute_*         routing/CAPI interface
codec_dsp_*        codec-DSP hooks
```

The actual 7530 backend is selected at runtime as `QCA-ADSS` /
`ipq40xxtdm_*`.

## 2. Initialization and activation

`pcmlink_init` / `init_module` (`.init.text 0x000`, size 452):

```text
clear pcmlink state
check kernel args: noslic / voiponly / nocapi / ignore_nocapi
pcmlink_hrtimer_init()
select link backend / platform
pcmlink_ul_decttransp_init()
PCMRoute_Init(0, 0, 0, 0)
register_reboot_notifier()
```

Hardware setup is lazy. `pcmlink_ul_register_pcmrouter` (`0x23f0`) does:

```text
zero the 0x300-byte pcmlink_ul_manager
initialize wait_for_deactivate
pcmlink_getlinktype()
pcmlink_ll_init(manager, linktype)
pcmlink_ll_sharedmemory()
map DSP shared-memory addresses
pcmlink_ul_regnoemif_init()
PowerManagmentActivatePowerMode("telefon_profile_4ms")
pcmlink_ll_activate()
pcmlink_ll_trigger_control()
avm_DebugCallRegister("pcmlink")
PowerManagmentRegister("pcmlink")
```

The low-level object is `pcmlink_ll_init` (`0xb20`). It:

- checks the handle magic `0x01012014`;
- allocates an `ll_handle` from the kmalloc cache;
- stores the callback table;
- computes timing from `ipq40xx_get_cyclefreq()` and `ipq40xx_get_cycles()`;
- registers the AVM event sink `piglet_ready_sink`;
- starts the `pcmlink_ctrl/%u` kernel thread;
- waits for the link initialization flag.

`pcmlink_ll_activate` (`0xe98`) sets the active state, triggers control, and
waits up to `0x1388` jiffies for activation. `pcmlink_ll_exit` stops the
kthread and releases the AVM event sink.

## 3. QCA/IPQ4019 TDM backend

The relevant local functions are:

```text
ipq40xxtdm_linkinit     0x9e40
ipq40xxtdm_linkactivate 0x9dd4
ipq40xxtdm_linkdeinit   0xa334
ipq40xxtdm_linkdeactivate 0xa37c
ipq40xxtdm_linkpoll     0xa1fc
ipq40xxtdm_checkhw      0xa3b4
ltdm_release_gpioresource 0x9d94
ipq40xxtdm_TxData       0x9c38
ipq40xxtdm_RxData       0x9bf4
```

### 3.1 TDM GPIOs

`ipq40xxtdm_linkinit` walks six entries in `pcmlinktdm_gpioconfig`
(`.data+0xd4`, six records of 0x2c bytes):

| index | logical hw-config name |
|---:|---|
| 0 | `gpio_avm_pcmlink_fsc` |
| 1 | `gpio_avm_pcmlink_fsc_2` |
| 2 | `gpio_avm_pcmlink_dcl` |
| 3 | `gpio_avm_pcmlink_dcl_2` |
| 4 | `gpio_avm_pcmlink_di` |
| 5 | `gpio_avm_pcmlink_do` |

Each table entry has this observed layout:

```text
+0x00  resource start
+0x04  resource end
+0x08  name pointer
+0x0c  flags (0x100)
+0x10  reserved
+0x14  reserved
+0x18  reserved
+0x1c  pinconfig A
+0x20  pinconfig B
+0x24  pinconfig from hw_config
+0x28  flags28 (1 on primary FSC/DCL entries)
```

For every entry the code:

1. looks up the logical name in `avm_get_hw_config_table()`;
2. reads the GPIO number from the table entry value;
3. requests the GPIO resource with `request_resource(&gpio_resource, ...)`;
4. programs the pin with `dakota_gpio_ctrl()` and
   `dakota_gpio_pinconfig()`;
5. marks the entry `-1` and fails if the resource is unavailable.

`ltdm_release_gpioresource` releases all six resources and restores `-1`.

The default `.data` table starts with `0xffffffff`, so the real GPIO numbers
come from the AVM `hw_config` table, not from constants in the code.

### 3.2 Frequency/clock check

`ipq40xxtdm_checkhw` (`0xa3b4`) reads `gpio_avm_pcmlink_fsc` and
`gpio_avm_pcmlink_dcl`, obtains their register bases, masks FIQ, samples the
GPIO bit over an `ipq40xx_get_cycles()` interval, and prints:

```text
[pcmlink]TDM: FS: %u Hz CLK: %u Hz
```

It returns failure bits if FSC/DCL are missing or the measured clock is below
the threshold. This is the same kind of hardware check that
`Piglet_noemif.ko` performs; `pcmlink` owns the actual TDM/audio path.

### 3.3 Vendor TDM/DMA API

`ipq40xxtdm_linkinit` configures only 16-bit slots and calls:

```text
tdm_if_config_init(slot_size, tx_slots, rx_slots, config)
tdm_if_dma_init(dma_handle, ipq40xxtdm_TxData, ipq40xxtdm_RxData,
                1, 1, slot_size, slot_ratio, 16)
```

The exact register/stack assignment is recovered from `0x9ff8..0xa04c`:

```text
r0 = [r4+0x24]  slot size (8 or 16)
r1 = [r4+0x34]  tx slot count/flag
r2 = [r4+0x30]  rx slot count/flag
r3 = [r4+0x38]  config value

tdm_if_dma_init:
  r0 = .bss+0xd6a4 (DMA handle/context)
  r1 = ipq40xxtdm_TxData
  r2 = ipq40xxtdm_RxData
  r3 = 1
  stack[0] = 1
  stack[1] = slot size
  stack[2] = slot_ratio = uidiv([r5+0], [r5+8])
  stack[3] = 0x10 (16 descriptors)
```

So the earlier “descriptor_count before slot_size” ordering was wrong; the
fifth argument is a second `1`, and the descriptor count is the eighth
argument.

`ipq40xxtdm_linkactivate` then calls:

```text
tdm_if_config_init(...)
tdm_if_dma_start(dma_handle)
```

The observed descriptor count is `0x10` (16). `linkdeactivate` calls
`tdm_if_dma_stop`; `deinit` calls `tdm_if_dma_exit` and
`tdm_if_config_exit`; debug uses `tdm_if_print_status`.

`ipq40xxtdm_linkpoll` checks `tdm_if_dma_irqcnt()`; if RX/TX IRQ counters stop
advancing for more than `0x7d` jiffies it logs a discontinued IRQ count and
forces a DMA reinitialization. `tdm_if_dma_irqcnt_reset()` resets the counters.

`ipq40xxtdm_TxData` and `ipq40xxtdm_RxData` call function pointers stored in
the TDM handle (DMA callbacks) and notify an optional timing hook after each
transfer.

The vendor symbols are the main blocker:

```text
tdm_if_config_init
tdm_if_config_exit
tdm_if_dma_init
tdm_if_dma_exit
tdm_if_dma_start
tdm_if_dma_stop
tdm_if_dma_irqcnt
tdm_if_dma_irqcnt_reset
tdm_if_print_status
```

They are not present in the OpenWrt 6.12 kernel. Replacing `vermagic` is not
enough; the QCA TDM/DMA driver or a clean ALSA/DAI + DMA implementation is
required.

### 3.4 Recovered host/router shared-memory layout

`pcmlink` has two distinct state objects:

```text
gPcmroute         .bss+0xd780, 0xf8e8  host-side PCMRoute state
gPcmrouteKernel   .bss+0x280c0, 0x8f4  upper-layer manager
```

`pcmroute_getsharedmem()` returns `&gPcmroute`. The DSP/link descriptor is a
different object returned by `pcmlink_ll_sharedmemory()` and stored at
`gPcmrouteKernel+0x234`.

Recovered `gPcmroute` regions:

```text
0x0000  magic 0xc0afd54c
0x0004  derived value 0xeaac4704
0x0008  u16 command-ring head
0x000a  u16 command-ring tail
0x000c  0x104 * 0x28 command-ring entries
0x28ac  4 * 0x40 connection-struct pool
0x29ac  0x18-byte slot-table descriptor
0x29b0  u16 slot count
0x29b4  pointer to slot table at 0x3284
0x29c4  140 * 0x10 connection entries
0x3284  0x198-byte slot entries
0xdd98  5 * 0x94 echo-canceller states
0xe76c  3 * 0x24 codec callbacks
0xe828  0x44-byte per-slot EC/channel state
0xeaa8  u16 PCMRoute context
0xebac  0x18-byte channel state array
0xf000  0x8e8-byte status block
```

The manager stores the DSP mappings at `+0x224..+0x234`:

```text
+0x224  host address of descriptor+0x24
+0x228  host address of descriptor+0x38 (or 0)
+0x22c  host address of descriptor+0x3c (or 0)
+0x230  host address of descriptor+0x28
+0x234  descriptor pointer from pcmlink_ll_sharedmemory()
+0x238  pcmrouter callback argument
```

The descriptor's `+0x24` table has 0x14-byte entries (`slot`, `length`,
`offset`); `+0x38` is the TX allocation buffer base, `+0x3c` the RX retrieval
buffer base, `+0x28` the control/receive buffer, `+0x2c` its current length,
`+0x30` the link state and `+0x34` a status/command word.

See `notes/pcmlink-sharedmem.md` and `include/pcmlink_sharedmem.h` for the
complete table, structs and evidence.

## 4. PCM slot and DECT audio API

`pcmlink_ul_register_pcmrouter` clears the first 0x300 bytes of the 0x8f4-byte
upper manager and maps the DSP shared-memory slot tables. The slot path is:

```text
pcmlink_ul_openslots
  validate linkmask (max 7 audio channels, control slot excluded)
  allocate simplemempool for slot FIFOs
  allocate/init G.722 codec state
  build per-slot descriptors and list entries

pcmlink_ul_rxget_slotdata_pcmrouter
pcmlink_ul_txput_slotdata_pcmrouter
pcmlink_ul_txalloc_slotdata_pcmrouter
pcmlink_ul_rxfree_slotdata_pcmrouter
pcmlink_ul_setslotparam_pcmrouter
pcmlink_ul_closeslots
```

Observed constraints:

- only 16-bit slots are accepted (`slot_size=16`);
- at most seven audio channels per link;
- control linkmask `bit 0` is rejected for audio;
- slots are allocated only after the ISDN driver start (`pcmlink_ul_manager`
  must exist);
- G.722 is the transparent audio codec; the codec state is allocated per open
  slot group;
- slot memory uses AVM `simplemempool_alloc`, not kmalloc directly;
- FIQ masking is used around slot/timing updates.

DECT control has a separate interface:

```text
pcmlink_ul_register_dectcontrol
pcmlink_ul_register_dectcontrolnotification
pcmlink_ul_config_dectcontrol
pcmlink_ul_release_dectcontrol
pcmlink_ul_dectctrl_handler
```

`pcmlink_ul_decttransp_handler` handles DECT transparent G.722/data channels,
and the DECT slot sync helpers are in `dectsync_*` (`dectsync_init`,
`dectsync_checksyncmode`, `dectsync_preparesyncmode`).

The `PCMRoute_*` exports are the higher-level CAPI/analog routing layer:
`PCMRoute_Init`, `PCMRoute_SetTimeSlot`, `PCMRoute_GetTimeSlot`,
`PCMRoute_DisconnectDuplexTimeSlot`, `PCMRoute_RestoreDuplexTimeSlot`,
`PCMRoute_RegisterCODEC`, `PCMRoute_SetCODEC`, `PCMRoute_TxOff/RxOff`,
`PCMRoute_DTMFGen`, `PCMRoute_EC`, and related functions.

## 5. Threading/timing model

- `pcmlink_ll_init` creates a `pcmlink_ctrl/%u` kthread.
- `pcmlink_hrtimer_init` creates the AVM high-resolution trigger.
- `pcmlink_tasklet_control` and `pcmlink_ll_rxtxtrigger` process TDM
  TX/RX trigger events.
- `ipq40xxtdm_linkpoll` runs on a timer and detects stalled DMA IRQ counters.
- The code masks/unmasks all FIQs through AVM-specific APIs
  (`avm_mask_all_fiqs_down` / `avm_unmask_all_fiqs_up`) and uses
  `firq_trigger_linux_ipi`; these are not standard Linux APIs.
- `pcmlink_ul_openslots` disables FIQ around slot-table updates.

This timing path is why a plain userspace implementation cannot reproduce
the original audio behavior; the TDM frame interrupt and PCM slot delivery
must be handled by a kernel audio driver.

## 6. What can be reused vs replaced

Reusable as documentation/algorithm:

```text
PCM slot allocation model
G.722/codec helpers (portable C code)
PCMRoute routing logic
DECT control state machine
debug socket protocol
```

Must be replaced for OpenWrt 6.12:

| Original | Replacement |
|---|---|
| `tdm_if_config_init/dma_*` | QCA TDM driver or ALSA SoC DAI + DMA engine |
| `dakota_gpio_ctrl/pinconfig` | `gpiod_*`, pinctrl, regmap |
| AVM `gpio_resource` | GPIO/pinctrl resource reservation in DT |
| `avm_current_hw_config` | device tree / `nvmem` / board data |
| `PowerManagment*` | runtime PM, clocks, regulators |
| `simplemempool_*` | `kmalloc`/`kfifo`/DMA-coherent allocator |
| FIQ trigger/mask APIs | threaded IRQ, hrtimer, tasklet, DMA callback |
| `avm_event_*` | notifier/uevent |
| `ipq40xx_get_cycles/cyclefreq` | clock framework / arch timer |
| `pcmroute` DSP shared memory | DT reserved-memory region or ALSA shared buffer |

`PCMRoute_*`/codec code is portable in principle, but it assumes 16-bit TDM
slots, AVM shared-memory addresses, and the AVM trigger timing.

## 7. Unresolved questions

1. Exact DT binding/GPIO numbers for the six QCA TDM pins on the 7530.
2. The vendor `tdm_if_*` implementation is still missing; the call-site
   prototypes and argument order are now recovered, but the DMA descriptor
   format is known only from the QCA call site.
3. Whether the 7530 uses the vendor QCA TDM driver with FIQ, or a different
   backend in production.
4. Complete `PCMRoute_*`/`pcmlink_ul_*` ABI details; the host-side
   `gPcmroute` region map is in `notes/pcmlink-sharedmem.md`, but the DSP
   descriptor semantics and some slot/connection fields remain unresolved.
5. Which codec/DSP firmware (if any) the 7530 actually requires; the module
   contains many codec/FFT/EC routines, but not all are used by DECT.
6. Exact behavior of `pcmlink_ll_trigger_control` and hrtimer timing under
   OpenWrt.

## 8. Confidence

| Conclusion | Confidence | Basis |
|---|---|---|
| six TDM GPIO names/table | high | `.data+0xd4`, `ipq40xxtdm_linkinit` |
| 16-bit-only slots, max 7 audio channels | high | `ipq40xxtdm_linkinit`, `pcmlink_ul_openslots` |
| `tdm_if_*` call order and DMA stall poll | high | `ipq40xxtdm_*` disassembly |
| QCA backend/`QCA-ADSS` identity | high | strings + symbols |
| `tdm_if_*` call-site prototypes/argument order | high | register/stack assignment |
| vendor `tdm_if_*` implementation/DMA descriptor | medium | call-site inference only |
| `gPcmroute` region map and command ring | high | `0x15058`, `0x17a50`, `0xb4bc` |
| DSP descriptor `+0x24/+0x28/+0x38/+0x3c` semantics | medium | `0x23f0` mapping only |
| physical GPIO numbers | medium | values come from hw_config |
| full shared-memory/timing semantics | low-medium | requires runtime tracing |
| codec/DSP usage on 7530 | medium | module contents vs stock profile |

## Evidence files

```text
reports/pcmlink.annotated.txt
reports/pcmlink.init-exit.disasm.txt
reports/pcmlink.disasm.txt
reports/pcmlink-callgraph.txt
reports/pcmlink-tdm-gpio.txt
reports/pcmlink-api.txt
reports/pcmlink-sharedmem.txt
notes/pcmlink-sharedmem.md
include/pcmlink_sharedmem.h
```
