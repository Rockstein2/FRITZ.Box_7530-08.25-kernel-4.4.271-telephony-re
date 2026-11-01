# `pcmlink` shared-memory layout — reconstructed map

Static analysis of `modules/ubik2/pcmlink.ko` (ARM EABI5, FRITZ!OS 08.25,
kernel 4.4.271, not stripped). No module was loaded and nothing was written to
the router.

This note replaces the top-level-only description in `notes/pcmlink.md` §7.
The machine-readable offsets are in `include/pcmlink_sharedmem.h`; raw evidence
is in `reports/pcmlink-sharedmem.txt`.

## 1. Two different shared-memory objects

The names are easy to confuse:

```text
gPcmroute             .bss+0xd780, size 0xf8e8
                      host-side PCMRoute router state.
                      Returned by pcmroute_getsharedmem().

gPcmrouteKernel       .bss+0x280c0, size 0x8f4
                      upper-layer pcmlink manager.
                      Holds the link handle and the DSP mapping.

DSP/link descriptor   returned by pcmlink_ll_sharedmemory()
                      stored at gPcmrouteKernel+0x234.
                      Not gPcmroute and not the same object.
```

`pcmroute_getsharedmem()` is exactly:

```text
0xc300: ldr r0, [pc]      ; -> .bss+0xd780
0xc304: bx  lr
```

`pcmlink_ll_sharedmemory()` is a vtable call:

```text
0xe60: check ll_handle magic 0x01012014
0xe78: r3 = [ll_handle+8]       ; link operations table
0xe7c: r3 = [r3+0x40]           ; shared-memory callback
0xe88: bx  r3
```

`pcmlink_ll_dsp_to_host_addr(ll, addr, len)` uses the next vtable slot:

```text
0xe28: r1 = [ll_handle+8]
0xe2c: lr = [r1+0x44]           ; DSP->host translation callback
0xe48: bx  lr
```

So the host router state and the DSP descriptor are deliberately separate.

## 2. `gPcmroute` region map

Offsets are relative to `gPcmroute` (`.bss+0xd780`).

| Offset | Size | Meaning | Evidence |
|---:|---:|---|---|
| `0x0000` | 4 | magic `0xC0AFD54C` | `pcmroute_memshared_routerinit` |
| `0x0004` | 4 | derived value `0xEAAC4704` | same function |
| `0x0008` | 2 | command-ring head | `l_pcmroutereadqueue` |
| `0x000A` | 2 | command-ring tail | same |
| `0x000C` | `0x104*0x28` | command ring entries | `pcmroute_enqueue_torouter`, `l_pcmroutereadqueue` |
| `0x2000` | — | control block base | `lpcmroute_sinkprocess` |
| `0x28D0` | 4 | control/status word | `lpcmroute_sinkprocess` |
| `0x28E0` | 1 | minimum active channel | same |
| `0x28E1` | 1 | maximum active channel | same |
| `0x28AC` | `4*0x40` | connection-struct pool | `pcmroute_alloc_cstruct` |
| `0x29AC` | `0x18` | slot-table descriptor | `pcmroute_slotconnectionlist_init` |
| `0x29B0` | 2 | slot count | `pcmroute_enqueue_torouter`, `pcmroute_hwchanviolation` |
| `0x29B4` | 4 | pointer to slot table | same |
| `0x29B8` | 2 | connection limit, `0x8C` (140) | descriptor init |
| `0x29BC` | 4 | connection storage pointer | descriptor init |
| `0x29C0` | 4 | descriptor flags | descriptor init |
| `0x29C4` | `140*0x10` | connection-entry array | `pcmroute_settimeslot` |
| `0x3284` | `0x198*count` | slot table | `PCMRoute_Init`, `lpcmroute_sinkprocess` |
| `0xDD98` | `5*0x94` | echo-canceller states | `pcmroute_ecinit`, `pcmroute_ecalloc` |
| `0xE76C` | `3*0x24` | codec callback table | `PCMRoute_RegisterCODEC` |
| `0xE828` | `0x44*N` | per-slot EC/channel state | `lpcmroute_sinkprocess` |
| `0xEAA8` | 2 | PCMRoute context word | `PCMRoute_SetContext` |
| `0xEAAC` | — | end of the zeroed area | `pcmroute_memshared_routerinit` |
| `0xEBAC` | `0x18*N` | channel state array | `lpcmroute_sinkprocess` |
| `0xF000` | `0x8E8` | status block | `l_pcmroutereadqueue` |
| `0xF8E8` | — | end of `gPcmroute` | ELF symbol size |

The first `0xEAAC` bytes are zeroed by `pcmroute_memshared_routerinit`; the
tail from `0xEAAC` to `0xF8E8` is not zeroed by that function.

## 3. Command ring

`pcmroute_enqueue_torouter` (`0x17a50`) proves the ring:

```text
count = 0x104
entry = 0x28 bytes
head  = u16 [gPcmroute+0x08]
tail  = u16 [gPcmroute+0x0a]
next  = (tail + 1) & 0xffff
if next == 0x104: next = 0
reject if next == head
entry[tail].fn      = r2          // callback/context
entry[tail].slot    = r6 & 0xff   // slot/channel
entry[tail].payload = memcpy(..., r3, len)
tail = next
```

`l_pcmroutereadqueue` (`0xb4bc`) consumes the same ring, copying `0x28` bytes
per entry and dispatching on the first word.

The ring occupies `0x000C..0x288B`; it does not overlap the control block at
`0x2000` only because the ring ends before `0x288C` and the control fields used
by the audio path start at `0x28D0`.

## 4. Slot table and connection list

`PCMRoute_Init` (`0x15058`) initializes two slot-table descriptors:

```text
gPcmrouteKernel+0x8d4   descriptor for one direction
gPcmroute+0x29ac        descriptor for the other direction
```

`pcmroute_slotconnectionlist_init` (`0xc500`) stores:

```text
+0x00  state / connection-list head (0 when empty)
+0x04  slot count
+0x08  slot table pointer
+0x0c  connection limit (0x8c = 140)
+0x10  connection storage pointer
+0x14  flags
```

For the `gPcmroute+0x29ac` descriptor the normal values are:

```text
slot table        = gPcmroute+0x3284
connection limit  = 0x8c (140)
connection store  = gPcmroute+0x29c4
connection entry  = 0x10 bytes
slot entry size   = 0x198
```

The gap between the connection store and the slot table is exactly
`0x3284 - 0x29c4 = 0x8c0`, i.e. 140 entries of `0x10`. This is the connection
array; it fits exactly before the fixed slot table. `PCMRoute_Init` accepts a
slot count up to `0x46`, but the connection array is still 140 entries.

The slot table entry fields observed in `lpcmroute_sinkprocess` are:

```text
+0x004  u32 flags              bit 0x80, bit 0x400, low 3 bits
+0x008  u32
+0x00c  u32
+0x010  u32                     checked non-zero before callback
+0x014  u32 callback
+0x018  u32 callback
+0x026  u8
+0x028  u8                      EC channel index
+0x029  u8                      1-based EC state index
+0x02d  u8                      connection/user-set busy flag
+0x02e  u8                      second busy flag
+0x02f  u8                      adds flag 0x20; clears +0x30 block
+0x030  u8[0x8c]                substructure cleared when +0x02f was set
+0x11c  u32                     G.722 state pointer
+0x18c  u32                     codec state pointer
+0x190  u8[8]                   DTMF state; +0x190 is the active byte
+0x198  end of entry
```

`pcmroute_userset` (`0xc914`) rejects a connection when `+0x2d`, `+0x2e`,
`+0x190` or `+0x18c` is set on either endpoint. `l_adddremove_entry`
(`0xcb94`) clears eight bytes at `+0x190` when the first byte is set.

`pcmroute_hwchanviolation` (`0xc464`) independently confirms the count at
`0x29B0` and the table pointer at `0x29B4`, with `0x198` bytes per entry.

A connection entry in the array at `0x29C4` is 0x10 bytes:

```text
+0x00  u8 endpoint 0 (source)
+0x01  u8 endpoint 1 (source)
+0x02  u8 sink key
+0x03  u8 multi-source alternate endpoint
+0x04  u8 endpoint checked by findslot_as_source
+0x05  u8[3] reserved
+0x08  u32 next connection (0 terminates the list)
+0x0c  u8 used flag
+0x0d  u8[3] reserved
```

`pcmroute_findslot_by_sink` (`0xc538`) walks the list through `+0x08` and
compares `+0x02`; `pcmroute_is_slot_activ` (`0xc590`) checks the sink at
`+0x02` and source endpoints at `+0x00/+0x03`;
`pcmroute_get_realsource_idx` (`0xc75c`) uses `+0x00/+0x01` and falls back to
`+0x03` for a multi-source slot; `pcmroute_numconnectedwithsrc` (`0xd110`)
counts a selected source byte. `pcmroute_settimeslot` (`0xce44`)
initialises a free entry with `-1` endpoints, the requested sink in `+0x02`,
and `1` in `+0x0c`.

The exact endpoint naming is not proven; only the sink at `+0x02` and the
list link at `+0x08` are unambiguous.

## 5. Connection-struct pool

`pcmroute_alloc_cstruct` (`0x17814`) scans four `0x40`-byte entries:

```text
entry[i]     = gPcmroute + 0x28ac + i*0x40
entry[i].used= byte at entry+0x3f (also gPcmroute+0x28eb+i*0x40)
```

`pcmroute_free_cstruct` (`0x17890`) only clears `entry+0x3f`. The copied
payload length is caller-provided and is at most `0x3f` bytes.

## 6. Echo-canceller states

`pcmroute_ecinit` (`0x17fa4`) clears five `0x94`-byte entries:

```text
base = gPcmroute + 0xdd98
for i in 0..4:
    memset(base + i*0x94, 0, 0x94)
    byte[+1] = 0xff
    dword[+4] = 0xff
```

`pcmroute_ecalloc` (`0x1801c`) and `pcmroute_get_ecbkanal_from_slot` (`0x1814c`)
confirm the same 5x0x94 array. `pcmroute_hwchanviolation` computes:

```text
gPcmroute + 0xdd98 + 0x94*(ec_index)
```

and calls `pcmroute_ecviolation`, which reads byte `+2` (EC channel).

## 7. Codec table

`PCMRoute_RegisterCODEC` (`0x13438`) accepts codec ids 1..3 and writes a
`0x24`-byte entry at:

```text
gPcmroute + 0xe76c + 0x24*codec_id
```

Entry layout:

```text
+0x00  codec id
+0x04  callback[0]
+0x08  callback[1]
+0x0c  callback[2]
+0x10  callback[3]
+0x14  callback[4]   // PCMRoute_InternalCODEC uses this slot
+0x18  callback[5]
+0x1c  callback[6]
+0x20  callback[7]
```

The table is separate from the per-slot codec state at slot+0x18c.

## 8. Channel and status blocks

The channel array at `0xEBAC` has `0x18`-byte entries:

```text
+0x00 u32
+0x04 u32
+0x08 u32
+0x0c u16
+0x10 u32
+0x14 u8
```

`lpcmroute_sinkprocess` indexes it with `0x18 * channel`.

The status block at `0xF000` has `0x8E8` bytes. Fields observed by
`l_pcmroutereadqueue` and `lpcmroute_sinkprocess`:

```text
gPcmroute+0xF8CC  u32
gPcmroute+0xF8D0  u32   // feature bits 0x20, 0x40
gPcmroute+0xF8D8  u32
gPcmroute+0xF8DC  u32
gPcmroute+0xF8E0  u8    // minimum channel
gPcmroute+0xF8E1  u8    // maximum channel
```

## 9. `gPcmrouteKernel` manager and DSP descriptor

`pcmlink_ul_register_pcmrouter` (`0x23f0`) clears the first `0x300` bytes of
the manager and fills:

```text
+0x000  u32 magic 0x53428431
+0x004  u32 ll_handle
+0x008  u32 regnoemif handle
+0x20C  u32 0
+0x210  u32 3
+0x218  wait_queue_head_t
+0x224  host address of descriptor+0x24
+0x228  host address of descriptor+0x38 (or 0)
+0x22C  host address of descriptor+0x3C (or 0)
+0x230  host address of descriptor+0x28
+0x234  descriptor pointer from pcmlink_ll_sharedmemory()
+0x238  pcmrouter callback argument
+0x2B4  AVM debug handle
+0x2B8  power-management handle
```

The descriptor fields used by the mapping and by the slot API are:

```text
+0x24  table of 0x14-byte slot entries -> manager+0x224
+0x28  control/receive buffer base     -> manager+0x230
+0x2C  current received length
+0x30  link state (3 = active, 0 = idle; 1/5 transitions)
+0x34  status/command word (observed 0, 2, 4, 6)
+0x38  buffer base A                   -> manager+0x228 (TX allocation)
+0x3C  buffer base B                   -> manager+0x22C (RX retrieval)
+0x44  observed bitmask
+0x48  observed bitmask
+0x4C  observed value
+0x50  observed value
+0x58  observed bitmask
+0x60  TX slot bitmask
+0x64  RX release/status
+0x68  regnoemif descriptor
```

The `+0x24` table entry is 0x14 bytes:

```text
+0x00  u32 slot/selector, observed <= 0x1f
+0x04  length (used as u16; doubled in one mode)
+0x08  offset into the +0x38 or +0x3C buffer
+0x0C  unknown
+0x10  unknown
```

`pcmlink_ul_rxget_slotdata_pcmrouter` (`0x1a50`) reads
`manager+0x224 + 0x14*slot`, uses `entry+0x08` as an offset into
`manager+0x22C`, and returns the length from `entry+0x04`.
`pcmlink_ul_txalloc_slotdata_pcmrouter` (`0x2338`) uses the same entry but
adds `entry+0x08` to `manager+0x228`.
`pcmlink_ul_handler` (`0x2e78`) copies a received block from
`manager+0x230` using the length at descriptor+0x2C.

For `0x38`/`0x3C`, the code maps both ends and stores the difference as the
third argument to `pcmlink_ll_dsp_to_host_addr`; this is a range translation,
not an independent buffer.

The link/DSP descriptor object is `SharedMemory`:

```text
.bss+0xcb0c, size 0x2dc   // VOIPOnlyLink_SharedMemory returns this
.bss+0xcde8, size 0x2dc   // FPGALink_SharedMemory returns this
```

The QCA backend returns its own descriptor through the same vtable slot. The
manager stores whichever pointer the selected backend returns at `+0x234`.

## 10. Lifetime and ownership

```text
pcmlink_init
  -> pcmlink_hrtimer_init
  -> pcmlink_ul_decttransp_init
  -> PCMRoute_Init(0,0,0,0)
       -> zero gPcmrouteKernel[0x8f4]
       -> gPcmrouteKernel+0x0c = gPcmroute
       -> pcmroute_memshared_routerinit()
            -> zero gPcmroute[0xeaac]
            -> gPcmroute[0x00] = magic
            -> gPcmroute[0x04] = derived
            -> pcmroute_dtmfscan_init()
            -> pcmroute_ecinit(gPcmroute+0xdd98)

pcmlink_ul_register_pcmrouter(callback)
  -> zero gPcmrouteKernel[0x300]
  -> pcmlink_ll_init(manager, link_ops)   // allocates ll_handle
  -> pcmlink_ll_sharedmemory()            // link/DSP descriptor
  -> map descriptor +0x24/+0x28/+0x38/+0x3C
  -> pcmlink_ul_regnoemif_init(descriptor+0x68)
  -> pcmlink_ll_activate()
  -> descriptor+0x30 = 3

PCMRoute_Init(ctx, slot_count, ...) with nonzero ctx
  -> initialize slot-table descriptors/tables

PCMRoute_Exit
  -> pcmroute_slotconnectionlist_exit(gPcmroute+0x29ac)
  -> pcmroute_memshared_routerexit()
       -> pcmroute_ecexit(gPcmroute+0xdd98)
       -> g722_freeallinst()
       -> equalize_freeall()

pcmlink_ul_release_pcmrouter
  -> pcmlink_ul_regnoemif_exit
  -> pcmlink_ll_exit
  -> clear manager+0x238, debug, power-management
```

`gPcmroute` is static module `.bss`; it is not allocated per open. Its lifetime
is the module lifetime. The command ring and slot tables are fixed-size and
reused. The DSP descriptor is owned by the selected link backend; the manager
only stores a borrowed pointer and translated host addresses.

## 11. Porting implications

To replace this on Linux 6.12, a clean implementation needs:

```text
host router state           kmalloc/kvzalloc or static per-device state
command ring                kfifo or explicit SPSC ring with barriers
slot table                  fixed array + mutex/spinlock, not FIQ masking
EC/codec state              normal kernel allocations with refcounts
DSP descriptor              DT reserved-memory or DMA-coherent region
DSP->host translation       dma_addr_t / gen_pool / regmap, not vtable magic
manager+0x224..0x234        typed struct with explicit dma_addr_t fields
```

The original uses FIQ masking and raw shared addresses. A clean port should
replace those with DMA API mappings and normal locking. The exact DSP data
format beyond the fields above still needs runtime tracing.

## 12. Unresolved

1. The full semantics of the command-ring entry first word and payload.
2. The exact semantics of the descriptor `+0x24` table fields `+0x0C/+0x10`
   and the `+0x44..+0x64` bitmask/status words; the buffer roles of
   `+0x28/+0x38/+0x3C` are now inferred from their consumers.
3. The size/count of the `0xE828` per-slot array and `0xEBAC` channel array.
4. The `0x198` slot entry beyond the fields listed above; the `0x10`
   connection entry is mapped, but its endpoint naming is partially inferred.
5. The tail region `0xEAAC..0xEFFF`.
6. The QCA backend's concrete shared-memory descriptor versus the
   `SharedMemory`/FPGA objects.
7. Runtime ownership rules for the DSP range translations.

## 13. Confidence

| Conclusion | Confidence | Basis |
|---|---|---|
| `pcmroute_getsharedmem()` returns `&gPcmroute` | high | `0xc300` |
| `gPcmroute` size/magic/zero size | high | ELF symbol + `0x178a0` |
| command ring at `+0x0c`, 0x104 x 0x28 | high | `0x17a50`, `0xb4bc` |
| slot descriptor at `+0x29ac`, table at `+0x3284` | high | `0x15058`, `0xaa70` |
| slot entry size `0x198`, count at `+0x29b0` | high | `0xc464`, `0xaa70` |
| EC array 5 x 0x94 at `+0xdd98` | high | `0x17fa4`, `0x1801c` |
| codec table 3 x 0x24 at `+0xe76c` | high | `0x13438` |
| manager `+0x224..+0x234` mapping | high | `0x23f0` |
| descriptor `+0x24` table and `+0x38`/`+0x3C` buffer roles | high | `0x1a50`, `0x2338`, `0x2e78` |
| descriptor `+0x44..+0x64` bitmask semantics | medium | call-site inference |
| connection array: 140 × 0x10 at `+0x29c4` | high | `0xce44`, `0xc538`, `0x15058` |
| full slot/connection entry layout | medium | partial field use |
| tail region and runtime ownership | low-medium | no runtime trace |

## Evidence files

```text
reports/pcmlink-sharedmem.txt
reports/pcmlink.disasm.txt
reports/pcmlink.annotated.txt
reports/pcmlink-callgraph.txt
include/pcmlink_sharedmem.h
```
