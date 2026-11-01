# `avm_dect.ko` — DECT stack / pcmlink / `dect_io` boundary

Static analysis of `modules/avm_dect/avm_dect.ko` (ARM EABI5, FRITZ.OS 08.25,
kernel 4.4.271, not stripped). No module was loaded and nothing was written
to the router.

## 1. Layering

```text
dect_manager (userspace)
        |
        |  /dev/dect_io  (dect_io.ko, ABI in notes/dect_io.md)
        v
avm_dect.ko
        |
        |  pcmlink_ul_register_dectcontrol
        |  pcmlink_ul_config_dectcontrol
        |  RxTxCallback
        v
pcmlink.ko
        |
        |  QCA IPQ4019 TDM/DMA + PCM slots
        v
DECT stub / DECT chip
```

`avm_dect.ko` declares `depends=pcmlink`. The userspace `dect_manager` sees
only `/dev/dect_io`; `avm_dect` is the kernel-side DECT protocol/audio stack.

## 2. Init and cleanup

`avm_dect_init` / `init_module` (`.init.text 0x000`, 396 bytes):

```text
simplemempool_alloc_init(0x40000) -> gDectMemPool
avm_dect_debug_register()
avm_support_register()
initialize the DECT control object (0x48 bytes)
pcmlink_ul_register_dectcontrol(&ctl->handle, &ctl->slot_count,
                                RxTxCallback)
pcmlink_ul_config_dectcontrol(handle, 0x1000, 0x1000)
allocate 0x1000-byte control/RX buffer
init_waitqueue_head()
kthread_create_on_node(avm_dect_thread)
onu_init()
```

`avm_dect_cleanup` / `cleanup_module` reverses it:

```text
onu_exit()
kthread_stop()
PROTRACE_Deinit()
cdev_del / unregister_chrdev_region for the avm_dect debug device
pcmlink_ul_release_dectcontrol(handle)
avm_dect_debug_exit / avm_support_exit
simplemempool_free(0x1000 buffer)
simplemempool_alloc_exit(gDectMemPool)
```

`gDectMemPool` is a 0x40000-byte fixed pool used for DECT mail packets and
the control buffer. `avm_dect` has its own character device for monitor/debug;
it is separate from `/dev/dect_io`.

## 3. `avm_dect_if_*` — the userspace-facing hooks

Exported functions:

```text
avm_dect_if_init          0xad54
avm_dect_if_deinit        0xad68
avm_dect_if_audio_init    0xad7c
avm_dect_if_audio_deinit  0xad90
avm_dect_if_tx            0xada4
```

`avm_dect_if_init(handler)` stores the frame handler at `.bss+0xed4`;
`avm_dect_if_audio_init(handler)` stores the audio callback at `.bss+0xed8`.
The deinit functions clear those pointers.

`avm_dect_if_tx(ptr, len)` receives the bytes that `dect_io` forwards:

```text
ptr[0]      channel, observed 0x14
ptr[1..2]   AVM primitive, little-endian
ptr[3..]    payload
len         includes the channel byte
```

Behavior:

```text
if frame handler == NULL: return -EIO (-5)
channel = ptr[0]
primitive = le16(ptr[1..2])
length = len - 1
if primitive == 0x2fba:
    allocate a special upper-layer buffer from gDectMemPool
    copy the special payload
SendMailFromUpper(channel, length, ptr+1)
avm_dect_trigger_thread(1)
return 0
```

The `0x2fba` special path is confirmed at `0xadf0..0xae30`; it uses
`simplemempool_alloc(gDectMemPool, length)` and `memcpy`.

`UicpSendMailToHost(ptr, len)` is the reverse path:

```text
if .bss+0xed4 handler is set:
    handler(ptr, len)
simplemempool_free(gDectMemPool, ptr)
```

`UicpSendSyncPcmFramingCfmToAudioHost()` calls the handler at `.bss+0xed8`
with no additional framing.

## 4. pcmlink DECT-control boundary

`avm_dect_init` registers `RxTxCallback` with:

```text
pcmlink_ul_register_dectcontrol(&handle, &dect_slot_count, RxTxCallback)
pcmlink_ul_config_dectcontrol(handle, 0x1000, 0x1000)
```

`pcmlink_ul_register_dectcontrol` (`pcmlink 0x3fa8`):

- requires the ISDN driver to be started;
- calls the link backend to allocate DECT control slots;
- stores the callback in its own `.bss+0xaa8` DECT-control object;
- returns a handle and the number of DECT slots;
- calls `pcmlink_ul_status(5, 0xc..0xf, ...)` to query the control slots.

`pcmlink_ul_config_dectcontrol` (`pcmlink 0x4370`) stores the callback/context
and slot configuration in the handle. `pcmlink_ul_release_dectcontrol` releases
it.

`RxTxCallback` (`avm_dect 0x21b9c`) is the actual control-channel callback:

```text
callback(src_ptr, len_ptr):
    if g_avm_dect_status.control_active:
        memcpy(avm_dect control buffer, *src_ptr, *len_ptr)
        pcm_rx_tx_handler(control_object, buffer, *len_ptr)
        optional AVM notification
```

It copies the incoming control bytes into the 0x1000-byte buffer and passes
them to `pcm_rx_tx_handler`.

## 5. PCM mail path

There are two related queues:

```text
g_pcmdrv_tx_queue   .bss+0xc068  (12-byte queue object)
g_pcmdrv_rx_queue   .bss+0xc088
g_pcm_local_stat    .bss+0xc076
g_pcm_stub_status   .bss+0xc094
```

### `pcm_TaskInit`

Initializes both queues, resets the PCM control TX state, initializes the
control RX state, starts a 0x7918-jiffy timer, and clears the status buffers.

### `pcm_Task`

Parses an upper-layer mail. The observed header is at `mail-4`:

```text
mail-4  u16le length
mail-2  u8 task
mail-1  u8 primitive
mail+0  payload
```

The task length passed to `pcmdrv_enqueue_tx` is `length + 4`. For a mail that
represents PCM activity, `pcm_Task` calls:

```text
pcmlink_ul_activity(0, 0x100000, 1)
```

and then enqueues the frame with `pcmdrv_enqueue_tx`.

### `pcmdrv_enqueue_tx`

- rejects a frame longer than `0xfc`;
- recognizes primitive values `0xf626`, `0xfff1`, and `0x158`;
- byte-swaps several fields in the mail;
- masks FIQ with `avm_mask_all_fiqs_down`;
- enqueues into `g_pcmdrv_tx_queue` with `Queue_EnQueueIRQ`;
- updates queue statistics and increments the TX counter;
- unmask FIQs.

### `pcmdrv_check_rx_mails`

- dequeues from the RX queue;
- rejects a mail shorter than 8 bytes;
- handles primitive `0xf625` (status/indication), `0xfff1` (stub OS status),
  and `0x242`;
- byte-swaps fields of multi-field status messages;
- forwards remaining mails through `SendMailRaw`;
- updates RX statistics/errors.

### `pcmdrv_checksum_valid`

For a frame pointer `p`:

```text
length = le16(p[0])
checksum is checked over p[0 .. length+3]
received checksum is at p[length+4 .. length+5]
```

The parser is used by PCM code only after the mail length/header checks.

### `pcm_rx_tx_handler`

`pcm_rx_tx_handler` (`0x19614`) is the byte-stream parser for received PCM
control data. It recognizes `0xAA` as the start marker, parses task/primitive
and length, fills `g_mail_rx_buf`, and dispatches PCM status/commands. The
exact state variables are:

```text
pcm_local_stat  0x3958  parser state, counters, current length/pointer
g_mail_rx_buf   0xc108  receive buffer
```

The parser is why `RxTxCallback` copies the incoming bytes and passes a length
pointer rather than directly calling a PCM data routine.

## 6. Audio/UOTA slots

`FpUI` (DECT call control) opens a pcmlink audio slot for a handset:

```text
pcmlink_ul_openslots(1 << pcm_slot, &slot->handle,
                     ApiFpFastUotaRxTxCb, 1)
```

The returned handle is stored in the per-handset UOTA state. The state
allocation is `0x1450` bytes. On UOTA stop/exit:

```text
pcmlink_ul_closeslots(slot->handle)
```

`ApiFpFastUotaRxTxCb` (`0x2f5c`) is called by pcmlink with an audio buffer. It
copies data into the per-handset ring buffer at `state+0x430`, advances the
ring index, and wakes the DECT thread. The observed limits are:

```text
ring entries: 0x80 (128)
max copied per callback: 0x20 (32)
```

`pcmlink_ul_activity(0, 0x100000, 1)` is called from `pcm_Task` and `FpUI`
when PCM/DECT activity changes.

`ProtocolMapSetPcmSlot` (`0x1b360`) manages the DECT internal PCM slot table:

```text
table base .bss+0x3971
entry size 0x4f bytes
valid CCEI/CC slots 0..6
entry fields include slot, mode, codec/feature flags and mute state
```

It calls `ProtocolMapConnectAdpcm` / `ProtocolMapPcmSlotInd` when a slot is
added or changed. This table is separate from the pcmlink TDM slot table.

## 7. pcmlink shared-memory / router state

`pcmlink` has two distinct state areas:

```text
gPcmroute       .bss+0xd780, size 0xf8e8   (PCMRoute shared/router state)
SharedMemory    .bss+0xcb0c, size 0x2dc    (link/shared-memory object)
```

`pcmroute_getsharedmem()` returns `&gPcmroute`. `pcmroute_memshared_routerinit`
zeroes `0xeaac` bytes and writes:

```text
gPcmroute+0x000  0xc0afd54c  (magic)
gPcmroute+0x004  derived pointer/value
gPcmroute+0xdd98 EC state (passed to pcmroute_ecinit)
```

The exact field-by-field layout of `gPcmroute` is not fully recovered. The
high-level code uses it for PCMRoute routing, DTMF scan, echo cancellation,
G.722 state, equalizer state, and post-processing. The DSP shared-memory
mapping used by `pcmlink_ul_register_pcmrouter` is a separate mapping:

```text
pcmlink_ll_sharedmemory()
pcmlink_ll_dsp_to_host_addr()
```

The manager stores the mapped pointers at:

```text
pcmlink_ul_manager+0x224  DSP table base
pcmlink_ul_manager+0x228  host address for shared+0x24
pcmlink_ul_manager+0x22c  host address for shared+0x3c
pcmlink_ul_manager+0x230  host address for shared+0x28
pcmlink_ul_manager+0x234  shared-memory object
```

The layout of the DSP shared-memory table itself remains unresolved without
runtime tracing; the offsets above are what `pcmlink_ul_register_pcmrouter`
uses.

## 8. Porting impact

The userspace-facing `avm_dect_if_*` ABI is small and can be mocked. The hard
part is the kernel-side split:

- `dect_io` provides framed `/dev/dect_io`;
- `avm_dect` implements the DECT protocol, PCM mail transport and UOTA;
- `pcmlink` provides QCA TDM/DMA and slot routing;
- `pcmlink`'s `tdm_if_*`, `dakota_gpio_*`, FIQ, shared memory and timing have no
  OpenWrt 6.12 equivalent.

A clean implementation needs at least:

```text
clean /dev/dect_io shim
clean avm_dect DECT protocol/transport
pcmlink-compatible PCM/TDM driver (ALSA/DAI + DMA)
userspace dect_manager compatibility
```

It is not sufficient to copy `avm_dect.ko` and `pcmlink.ko`: both are kernel
4.4 proprietary modules with AVM-only imports.

## 9. Unresolved questions

1. Exact `gPcmroute` field layout and shared-memory descriptor layout.
2. Exact `tdm_if_config_init`/`tdm_if_dma_init` prototypes and DMA descriptor
   ring format.
3. Exact PCM mail task/primitive numbering beyond the observed `f625/f626`,
   `fff1`, `158`, `242`, and `2fba`.
4. Which portions of the codec/EC/G.722 code are used on 7530 DECT.
5. How `pcmlink_ul_activity` affects power/clock on the QCA backend.
6. The stock 7530 `hw_config` GPIO numbers for FSC/DCL/DI/DO.

## 10. Confidence

| Conclusion | Confidence | Basis |
|---|---|---|
| `avm_dect_if_*` pointer storage and TX contract | high | `avm_dect` disassembly |
| `pcmlink_ul_register/config/release_dectcontrol` calls | high | `avm_dect_init`, `pcmlink` |
| RxTxCallback copies into 0x1000 buffer | high | `0x21b9c` |
| PCM queue/length/checksum facts | medium-high | `pcmdrv.c`, `pcm.c` |
| FpUI UOTA slot open/close | high | `FpUI` call sites |
| `gPcmroute` size/magic/EC offset | medium | shared state initialization |
| full shared-memory layout | low-medium | needs runtime tracing |
| exact mail task/primitive ABI | medium | observed branches only |

## Evidence files

```text
reports/avm_dect.annotated.txt
reports/avm_dect.init-exit.disasm.txt
reports/avm_dect.disasm.txt
reports/avm_dect-pcmlink-xrefs.txt
reports/avm_dect-callgraph.txt
reports/avm_dect-pcm-frames.txt
reports/avm_dect-sharedmem.txt
```
