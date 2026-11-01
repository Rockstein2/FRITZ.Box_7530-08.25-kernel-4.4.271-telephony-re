# FON PCMLINK register path — recovered

Status: stage 5 static analysis. No router was accessed, no AVM module was
loaded, and no hardware test was performed. Addresses are module-relative ELF
offsets unless stated otherwise.

## 0. Bottom line

The FON control path is no longer a software-only virtual register bank. The
complete Linux-side chain is:

```text
slic_set_ring() / Set_POTS_Line_FPGA()
        |
        v
pcmlink_ul_writeregister(reg, value, mask)      0x3b60
        |
        v
lpcmlink_ul_writeregister()                      0x34b8
        |
        |  8-byte command entry in a 64-entry ring
        v
TDMPriv+0x4a0+0x68 ring  (FPGALink shared-memory window)
        |
        |  consumed by the TX DMA callback
        v
TxDMA()                                          0x9710
        |
        |  build_slic_ctrl() / _buildslic_ctrl_ring()
        v
16-bit control word at byte offset 0x0a of the TX TDM/MBOX frame
        |
        v
ipq40xxtdm_TxData() -> tdm_if_dma_init() callback
        |
        v
QCA ADSS MBOX/TDM DMA (MBOX0 TX for the enabled tdm node)
        |
        v
physical PCM/TDM/MBOX bus
        |
        v
SC14448 (most likely; see §8) -> discrete LM324/BCP53-16 line interface
```

The reverse hook path is:

```text
SC14448 / line interface
        |
        v
RX TDM/MBOX frame, byte offset 0x0a, 16-bit status word
        |
        v
PutRxDMA()                                       0x9a60
        |
        |  decodes status into virtual register 0x44
        v
TDMPriv+0x4a0+0x26c+0x44 value table
        |
        v
lpcmlink_ul_readregister() / pcmlink_ul_readregister()
        |
        v
slic_get_hook_state() -> bit 7 of register 0x44
```

There is **no FON UART message**, **no SPI/I2C SLIC bus**, and **no QCA GPIO
for SLIC reset/ring/hook** in this path. The control plane is carried inside
the PCM/TDM/MBOX frame.

The exact boundary of knowledge is:

- **CONFIRMED**: Linux API to the byte offset 0x0a of the ADSS TX/RX DMA frame.
- **CONFIRMED**: the QCA ADSS TDM/MBOX DMA transport and board DTS wiring.
- **INFERRED (high confidence)**: the SC14448 receives the control word and
  drives the discrete FON line interface.
- **UNKNOWN**: the exact SC14448 interpretation of every control/status bit,
  and the discrete high-voltage/ring topology.

## 1. Artifacts and method

Analyzed module:

```text
modules/ubik2/pcmlink.ko
sha256 6620510bc1d4b0f4d670e1e93d3f308dc3002785d3129521156eb5e1bc4a363b
ARM EABI5, Linux 4.4.271, not stripped
```

The module contains AVM build paths:

```text
/GU/FON_KMODS_cortexa9_build/src/main/../ubik2/pcmlink_ll.c
/GU/FON_KMODS_cortexa9_build/src/main/../ubik2/pcmlink_ul.c
/GU/FON_KMODS_cortexa9_build/src/main/../ubik2/pcmlink_socket.c
```

The source files themselves are **not present** in the published 08.25 GPL
tarball; `pcmlink` is proprietary. The tarball does contain the QCA ADSS/TDM
implementation and the 7530 device tree:

```text
https://osp.avm.de/fritzbox/fritzbox-7530/source-files-FRITZ.Box_7530-cortexa9-08.25.tar.gz
sha256 8fe167fe849108d0f4fa99ee8c78c34bb8893993780387fe500c3e68fa66bcf0
size   626994064

sources/kernel/linux/sound/soc/qcom/ipq/ipq-adss-avm.c
sources/kernel/linux/sound/soc/qcom/ipq/ipq-avm.c
sources/kernel/linux/sound/soc/qcom/ipq/ipq-adss.h
sources/kernel/linux/arch/arm/boot/dts/Fritz_Box_HW236.dtsi
sources/kernel/linux/arch/arm/boot/dts/qcom-ipq4019-audio.dtsi
```

The binary was disassembled with the reproducible helper
`tools/pcmlink_regs.py` (see §11). No AVM `.ko` or firmware is added to the
repository.

## 2. Actual link-table correction

An earlier hypothesis looked at `ipq40xxtdm_hw` (`.rodata+0x17ac`, 14
pointers) and concluded that the QCA backend had no `set_status` callback. That
was the wrong table. The **selected link table is `FPGALink` at
`.rodata+0xa8`**, whose platform string is `QCA-ADSS`:

```text
.rodata+0xa8  FPGALink table (relocations)
  +0x00 FPGALink_PreInit           0x84b8
  +0x04 FPGALink_Init              0x84dc
  +0x08 FPGALink_Activate          0x8510
  +0x0c FPGALink_Poll              0x85b4
  +0x10 pcmlink_ul_handler         0x2e78
  +0x14 pcmlink_ul_control         0x2c78
  +0x20 FPGALink_Deactivate        0x8530
  +0x24 FPGALink_Exit              0x854c
  +0x28 FPGALink_PostExit          0x8568
  +0x2c FPGALink_SuspendResume     0x8598
  +0x30 FPGALink_ReinitPCMBus      0x857c
  +0x34 FPGALink_ClkChange         0x8908
  +0x38 FPGALink_StatusPCMBus      0x85a0
  +0x3c FPGALink_Set_Status        0x891c
  +0x40 FPGALink_SharedMemory      0x8930
  +0x50 -> .rodata.str1.1+0x10a = "QCA-ADSS"
```

`pcmlink_getplatform()` (`0x8c`) returns `[link_table+0x50]`; for this table
that is the `QCA-ADSS` string. `pcmlink_ll_sharedmemory()` calls vtable
`+0x40` and therefore gets `FPGALink_SharedMemory`, not a missing callback.
`pcmlink_ll_set_status()` calls vtable `+0x3c` and gets
`FPGALink_Set_Status`; it exists. However, **the FON register path does not go
through `Set_Status`**; it uses the TX/RX DMA frames described below.

`ipq40xxtdm_hw` is a hardware/backend table used by the TDM layer, not the
top-level link table.

## 3. Function-by-function call graph

### 3.1 API entry

`isdn_fbox_fon5.ko` calls exported `pcmlink_ul_*` functions:

| Function | Address | Arguments | Role |
|---|---:|---|---|
| `slic_set_ring` | `0x408d0` | `(slic, ring_on, ring_state)` | prepares register `0x48`, mask `0x60` |
| `slic_get_hook_state` | `0x4093c` | `(slic)` | reads register `0x44`, bit 7 for SLIC0 |
| `slics_reset` | `0x40994` | SLIC index/status | writes `0x40/0x48/0x4c/0x50` bring-up |
| `Get_POTS_LineState_FPGA` | `0x4179c` | line index | reads `0x48/0x44/0x50` |
| `Set_POTS_Line_FPGA` | `0x419c4` | line index/state | writes `0x48` and routes PCM |
| `Handle_Ints_FPGA` | `0x41058` | line index | toggles `0x48` bits 5/6, polls hook |

`pcmlink_ul_writeregister` (`0x3b60`) is a thin wrapper:

```text
r0 = reg, r1 = value, r2 = mask
r5 = reg
manager = pcmlink_ul_manager (.bss+0x438)
if manager+4 == 0: log "not registered", return
r0 = manager+8              ; pcmlink_ulreg object
r1 = reg
r2 = value
r3 = mask
stack[0] = -1               ; timeout/valid argument
tail call lpcmlink_ul_writeregister
```

`pcmlink_ul_readregister` (`0x3444`) is the matching wrapper:

```text
r0 = reg
manager = pcmlink_ul_manager
if manager+4 == 0: log "not registered", return 0
r1 = reg
r0 = manager+8              ; pcmlink_ulreg object
tail call lpcmlink_ul_readregister
```

### 3.2 Register object

`pcmlink_ulreg` is a static object at `.bss+0x740`, size `0x368`. Confirmed
fields from `pcmlink_ul_regnoemif_init` (`0x3aa0`) and the read/write paths:

| Offset | Size | Meaning | Evidence |
|---:|---:|---|---|
| `0x008` | 4 | read-mask-valid word, copied from shared window `+0x2d4` by handler | `0x3e5c` |
| `0x00c` | 4 | dirty/valid bitmask, one bit per 32-bit register word | `0x382c` |
| `0x010` | `4*26` | shadow values for register words 0..25 | `0x32d8`, `0x3828` |
| `0x078` | `8*26` | timestamp/validity pairs, initialized by `pcmlink_ll_mseccounter` | `0x3afc..0x3b0c`, `0x377c` |
| `0x150` | 4 | retry/state counter; initialized to `0x10152009`, set to `0x28` on timeout | `0x3af8`, `0x3e00` |
| `0x154` | 4 | link handle (`ll_handle`) | `0x3af0` |
| `0x158` | 4 | shared register window pointer (`descriptor+0x68`) | `0x3ae8` |
| `0x15c` | `0x208` | 26 metadata records, `0x14` bytes each, copied from `.rodata+0x58c` | `0x3ac8..0x3ad4` |
| `0x364` | 4 | spinlock/counter word used by read/write critical section | `0x3248`, `0x35b0` |

`pcmlink_ul_register_pcmrouter` (`0x23f0`) gets the shared window from
`pcmlink_ll_sharedmemory()`, then calls:

```text
pcmlink_ul_regnoemif_init(link_handle,
                          shared_window + 0x68,
                          host_addr_of_shared_window+0x24)
```

The return value (`&pcmlink_ulreg`) is stored in `pcmlink_ul_manager+8`.

### 3.3 Shared register window

`FPGALink_SharedMemory` (`0x8930`) returns `[FPGA_Ctrl+0x18]`. `FPGA_Ctrl` is
at `.bss+0xcde8`; `fpgadata_init` (`0x93d8`) receives `FPGA_Ctrl+0x18` as its
first argument, zeroes `0x2dc` bytes at `TDMPriv+0x4a0`, and stores that
pointer. Therefore the shared window is:

```text
TDMPriv + 0x4a0, size 0x2dc
```

Its layout, all evidence from `0x9768/0x9848/0x98e8/0x3aa0/0x3e5c`:

| Offset (shared window) | Size | Meaning | Confidence |
|---:|---:|---|---|
| `0x068..0x267` | `64*8` | command ring, 8 bytes per entry | confirmed |
| `0x268` | 2 | consumer index, modulo 64 | confirmed |
| `0x26a` | 2 | producer index, modulo 64 | confirmed |
| `0x26c..0x2d3` | `26*4` | current values for register words 0..25 | confirmed |
| `0x2d4` | 4 | read-mask-valid word | confirmed via `0x3e5c` |
| `0x2d8` | 4 | event/retry flag | confirmed via `0x3e64..0x3e78` |

`pcmlink_ul_regnoemif_init` sets the consumer index to the current producer
index, copies the metadata table, initializes timestamps, and optionally queues
register `0x20` with two descriptor fields. It does not zero the ring entries
or values itself; `fpgadata_init` zeroed the whole window.

### 3.4 Command ring entry

`lpcmlink_ul_writeregister` stores an entry at:

```text
ring_base + (producer & 0x3f) * 8
```

Confirmed fields from `0x3840..0x3868`:

```c
struct pcmlink_ul_cmd {      /* 8 bytes, CONFIRMED layout */
        uint32_t value;      /* +0x00 final masked value */
        uint16_t reg_word;   /* +0x04 register number / 4 */
        uint16_t flags;      /* +0x06 observed 1 for normal writes; exact meaning unknown */
};
```

The producer is incremented modulo 64. A full ring logs the module's
`registerqueueoverflow` message. `TxDMA` consumes entries and increments the
consumer index; it only uses `value` and `reg_word`, not `flags`.

### 3.5 Read path

`lpcmlink_ul_readregister` (`0x3174`) does **not** enqueue a read request and
does not sleep. It obtains:

```text
base       = ((pcmlink_ulreg*)handle)->+0x158 = shared_window + 0x68
idx        = reg >> 2
shadow     = *(u32 *)(handle + 0x10 + 4*idx)
real       = *(u32 *)(base + 0x204 + 4*idx)
metadata   = handle + 0x15c + 0x14*idx
value      = ((real ^ shadow) & metadata[0]) ^ shadow
```

`metadata[0]` is the **read mask**. The values for the FON registers are:

```text
reg 0x40: 0xfeeff000
reg 0x44: 0x01100fff
reg 0x48: 0xfeeff000
reg 0x4c: 0x00001111
reg 0x50: 0x00001111
```

Therefore `0x44` bit 7 is taken from the real/current value, while `0x48`
bits 5/6 are **not** present in the read mask; a read of `0x48` returns those
bits from the shadow, not from the current value. This is consistent with
bits 5/6 being write-side ring/line controls.

The function may log the module's `readregister` diagnostic with
`real`/`shadow` values, but it has no hardware read transaction.

### 3.6 Write path

`lpcmlink_ul_writeregister` (`0x34b8`) takes:

```text
r0 = pcmlink_ulreg handle
r1 = register number (0..0x64)
r2 = value
r3 = caller mask
stack[0] = timeout/valid argument (wrapper passes -1)
```

It locks `handle+0x364`, reads the shadow and metadata, merges the new value
with the caller mask, updates the shadow, sets the dirty bit, records a
timestamp, and enqueues the command. It does **not** touch MMIO and does not
call `pcmlink_ll_trigger_control`. The TX DMA callback consumes the ring on the
next frame.

The metadata table has more fields than the read mask. Observed uses:

- `metadata[0]` — read mask (read path).
- `metadata[1]` — used to clear bits from the shadow after a write; all zero
  for the FON entries, exact semantic name unknown.
- `metadata[2]` — used to merge the real/current value on the first write
  path; `0x44` = `0x01100fff`, `0x48`/`0x40` = 0.
- `metadata[3]` / `[4]` — mostly zero; used in diagnostic/validity checks,
  exact semantics unknown.

### 3.7 Retry / timeout path

`pcmlink_ul_regnoemif_handler` (`0x3e20`) is not the ring consumer. It:

```text
handle = pcmlink_ulreg
base   = handle+0x158
handle+8 = *(u32 *)(base + 0x26c)     ; read-mask-valid word
if (*(u32 *)(base + 0x270) != 0) {    ; event flag
        *(u32 *)(base + 0x270) = 0;
        handle+0x150 = 0x28;
}
if (handle+0x150 == 1) {
        for each dirty register word:
                if current != shadow:
                        log mismatch;
                        lpcmlink_ul_writeregister(handle, reg, shadow, -1, -1);
        handle+0x150--;
}
```

`pcmlink_ul_regnoemif_timeout` (`0x3dd0`) sets `handle+0x150 = 0x28` and
`handle+4 = 0`. This is an AVM retry/repair mechanism, not the transport.

### 3.8 Synchronization, acknowledgement and errors

| Question | Answer | Evidence |
|---|---|---|
| Is a write synchronous? | **No.** The API enqueues a ring entry and returns; `TxDMA` consumes it on a later DMA callback. | `0x3840..0x38d8`; no waitqueue/trigger in the function |
| Is there an explicit ACK? | **No per-write ACK.** The consumer index advances; the shadow/current values are compared later. | `0x3840..0x3868`, `0x3e20` |
| Is a read synchronous? | **No.** It returns the latest value-table entry and shadow, not a fresh hardware read. | `0x32d0..0x32ec` |
| Timeouts? | `pcmlink_ul_regnoemif_timeout` sets a retry state; `pcmlink_ul_regnoemif_handler` retries dirty registers whose current value differs from the shadow. | `0x3dd0`, `0x3e20` |
| Ring overflow? | The write path logs `registerqueueoverflow` and does not enqueue a new entry. | module strings at `0x231df`; producer logic |
| Callbacks | `tdm_if_dma_init` installs `TxData`/`RxData`; `TxDMA`/`PutRxDMA` are the callbacks that move frames. `pcmlink_ul_handler` handles link events; `FPGALink_Poll` handles link state. | `0x9c38`, `0x9bf4`, `0x2e78`, `0x85b4` |
| Wait queues | `pcmlink_ll_init` creates a waitqueue and control kthread; those are link activation/control, not per-register ACK. | `0xb20..0xe08` |

## 4. TX path: ring to TDM/MBOX frame

`TxDMA` (`0x9710`) is the TX callback installed by `tdm_if_dma_init`. It is
invoked through `ipq40xxtdm_TxData` (`0x9c38`):

```text
ipq40xxtdm_TxData(refhandle, buf)
  r3 = [refhandle+4]       ; TxDMA
  r0 = [refhandle+0xc]     ; TDMPriv
  blx r3
```

`TxDMA` confirms the ring and the control word:

```text
r4 = TDMPriv
r6 = TDMPriv + 0x508       ; ring base = shared_window + 0x68
producer = u16 [r6+0x202]
consumer = u16 [r6+0x200]
if producer != consumer:
    idx = consumer
    entry = r6 + idx*8
    reg_word = u16 [entry+4]
    value    = u32 [entry+0]
    consumer = (idx+1) & 0x3f
    store consumer at [r6+0x200]
    switch (reg_word - 0xb) {
      case 0x2c, 0x40, 0x48:
          values[reg_word] = value;       ; at shared_window+0x26c+4*reg_word
          ctrl = build_slic_ctrl(r8, ring_half_period);
          *(u16 *)(TDMPriv+0x7fc) = ctrl;
      case 0x30, 0x44:
          TDMPriv+0x7f4 = value;
          TDMPriv+0x7f6 = 5;
          ctrl = build_slic_ctrl(r8, value);
          *(u16 *)(TDMPriv+0x7fc) = ctrl;
      default:
          values[reg_word] = value;
    }
```

The exact TX buffer construction at `0x9874..0x98e0` is:

```text
tx[0x00] = 0x0000
tx[0x02] = 0xfefe
tx[0x04] = 0xfefe
tx[0x06] = 0xfefe
tx[0x08] = 0x5555          ; or 0 depending on TDMPriv+0x808
tx[0x0a] = control_word
tx[0x0c..] = audio slots
```

The control word is therefore **TDM slot 5** in a 16-bit-slot frame. The
`0xfefe`/`0x5555` words are AVM/DECT synchronization header values, not FON
register payloads.

When the `slic_ring` global is nonzero (ring active), `TxDMA` calls
`_buildslic_ctrl_ring` (`0x8fb0`) to produce the periodic ring control word
from `slic_ring`, `ring_half_period_count`, and per-SLIC state counters. When
a register write updates `0x48`/`0x2c`, `build_slic_ctrl` produces the line
control word. Both are written to `TDMPriv+0x7fc`, then copied to `tx+0x0a`.

### 4.1 `build_slic_ctrl` exact bit mapping

`build_slic_ctrl` (`0x8f68`) is called as:

```text
build_slic_ctrl(r0 = ring_base, r1 = ring/control field)
```

- If `r1 != 0`: return `r1 | 0x8000`.
- Else:
  - `v48 = *(u32 *)(r0+0x24c)` — this is the value-table entry for register
    `0x48` (value table starts at `r0+0x204`; `0x204+0x48 = 0x24c`).
  - `v2c = *(u32 *)(r0+0x230)` — value-table entry for register `0x2c`.
  - `ctrl = ((v48 >> 3) & 0x1e0) | ((v48 >> 4) & 0xf)`.
  - if `v2c & (1<<17)`: `ctrl |= 0x10`.
  - if `v2c & (1<<18)`: `ctrl |= 0x200`.
  - return `ctrl | 0x4000`.

Consequences for register `0x48`:

```text
0x48 bit 5 -> control bit 1
0x48 bit 6 -> control bit 2
0x48 bits 4..7 -> control bits 0..3
0x48 bits 8..11 -> control bits 5..8
0x2c bit 17 -> control bit 4
0x2c bit 18 -> control bit 9
control bit 14 = 0x4000 marker
```

The control word does **not** contain the complete 32-bit register value.
Only the selected line/ring bits are serialized.

### 4.2 Ring control path

`_buildslic_ctrl_ring` (`0x8fb0`) uses the `slic_ring` global at
`.bss+0xce48`, `ring_half_period_count` at `.bss+0xac`, and per-SLIC counters.
It sets/clears control bits 1/2 and 6/7 depending on the SLIC ring state, and
uses the half-period counter to alternate the ring phase. `set_slic_ringfreq`
(`0x9084`) computes:

```text
half_period = (500 / ring_frequency) << 3
```

with a default of 25 Hz when the requested frequency is zero. The exact
electrical meaning of the resulting 16-bit word is still inferred; the
software cadence is confirmed.

## 5. RX path: TDM/MBOX frame to hook register

`PutRxDMA` (`0x9a60`) is the RX callback installed by `tdm_if_dma_init` and
called through `ipq40xxtdm_RxData` (`0x9bf4`):

```text
ipq40xxtdm_RxData(refhandle, buf)
  r3 = [refhandle+0x10]   ; PutRxDMA
  r0 = [refhandle+0x18]   ; TDMPriv
  blx r3
```

The status word is read from the RX frame at **byte offset 0x0a** (TDM slot
5):

```text
status = u16 [rx + 0x0a]

if (status & 0x8000)
        marker = 0x1000;
        TDMPriv+0x73c = status;
else if ((status & 0xfffffc00) == 0x4000)
        TDMPriv+0x73c = status;
else
        TDMPriv+0x73c = status ? status : 0xbad00000;

reg44 = 0x00020008
        | ((status << 3) & 0x00000f00)
        | ((status << 4) & 0x000000ff);
TDMPriv+0x750 = reg44;      // value-table entry for register 0x44
```

`TDMPriv+0x750` is exactly:

```text
shared_window + 0x26c + 0x44
```

so `lpcmlink_ul_readregister(0x44)` reads this value. The hook extraction in
`slic_get_hook_state` is bit 7:

```text
hook = (reg44 >> 7) & 1
```

From the expression above:

```text
reg44 bit 7 = status bit 3
```

Thus the current code path gives:

```text
SC14448 RX status word bit 3 -> reg 0x44 bit 7 -> slic_get_hook_state()
```

This bit mapping is **confirmed by the instruction sequence**, but the
physical meaning of RX status bit 3 (hook switch, off-hook, or line current
threshold) is inferred from the name and caller, not from the SC14448
datasheet.

## 6. Register 0x44 analysis

### Confirmed

- `slic_get_hook_state` reads `pcmlink_ul_readregister(0x44)` and extracts
  bit 7 for SLIC0.
- `lpcmlink_ul_readregister` reads the current value table at
  `shared_window+0x26c+0x44`, not an MMIO register.
- `PutRxDMA` writes that table entry from the RX TDM/MBOX frame at offset
  `0x0a`.
- The read mask for `0x44` is `0x01100fff`, which includes bit 7.
- `Get_POTS_LineState_FPGA` also reads `0x44` (along with `0x48` and `0x50`)
  for line-state decoding.

### Inferred

- RX status bit 3 is the hook/loop-current state generated by the SC14448 or
  the discrete line interface.
- There is no hook IRQ in this path; `HandleAnalog`/`Handle_Ints_FPGA` poll
  the cached value on the analog timer.

### Unknown

- Exact SC14448 status bit assignment and threshold; only the Linux-side
  mapping to bit 7 is proven.

## 7. Register 0x48 analysis

### Confirmed

- `slic_set_ring` writes `0x48` with mask `0x60`; SLIC0 bits 5/6.
- `lpcmlink_ul_writeregister` turns that into an 8-byte ring command with
  `reg_word = 0x48/4 = 0x12`.
- `TxDMA` consumes the command, stores the final value in the value table,
  and calls `build_slic_ctrl`.
- `build_slic_ctrl` maps `0x48` bits 5/6 to control-word bits 1/2 and writes
  the 16-bit word to TX frame offset `0x0a` (slot 5).
- `Handle_Ints_FPGA` toggles `0x48` bits 5/6 while ringing; each toggle
  enqueues a new command consumed by the next TX DMA frame.
- `Set_POTS_Line_FPGA` also writes `0x48`; line/ring state and audio routing
  are coupled in the FON state machine.

### Inferred

- Control-word bits 1/2 are the logic-level ring/line drive bits presented to
  the SC14448/discrete line interface.
- The SC14448 or an external high-voltage stage converts these logic bits into
  the actual ring/line-feed waveform.

### Unknown

- Exact mapping of control-word bits to SC14448 pins/registers/F/R/RM/PD.
- High-voltage topology and safe ring voltage/cadence.
- Whether the SC14448 must run a specific firmware image for this slot.

## 8. Who receives the control word?

### A. Dialog SC14448 — INFERRED, high confidence

Supporting facts:

- Board DTS enables `qca-pcm-tdm@7709000`, `pcm@7704000`, `mbox0..4`,
  `stereo0..3`, and `tdm@0` (`Fritz_Box_HW236.dtsi:277..317`).
- The TDM node uses `MBOX0_TX`/`MBOX3_RX`; the PCM node uses
  `MBOX3_TX`/`MBOX0_RX` (`qcom-ipq4019-audio.dtsi:31..38,189..200`).
- The 7530 has one SC14448 with a 6-channel PCM+ interface. The six TDM
  codec slots match `Codecslots=6 Slics=1 DECT=4`: five audio channels plus
  one control slot.
- The FON PHY is discrete LM324 + BCP53-16; there is no separate SLIC IC and
  no QCA GPIO for SLIC control. The only digital device on the PCM/MBOX side
  that can drive the discrete line interface is the SC14448.
- `pcmlink`/`tdm_if` has no other FON control backend.

Contradicting/limiting facts:

- The SC14448 is not represented as a Linux device in the DTS; its firmware
  and register map are proprietary.
- No direct runtime trace of the SC14448 receiving slot 5 was captured.
- The exact SC14448 firmware path for slot 5 is not proven.

Verdict: **INFERRED, high confidence**, not `CONFIRMED`.

### B. Another hardware block — UNLIKELY

- `abmode=1` has no FPGA/FPGA2/PEF bit; `Pots=0`; the `FPGA*` names in
  `pcmlink` are legacy AVM names, not evidence of an FPGA on the 7530.
- Public board inventory lists no CPLD/FPGA or separate SLIC.
- The FON line interface is LM324/BCP53-16 discrete.

### C. Qualcomm subsystem — PARTIAL

- QCA ADSS is the **transport** (TDM/MBOX DMA), not the final FON controller.
- `ipq-adss-avm.c` has no FON GPIO, ADC, ring or hook logic.
- QCA only moves the 16-bit slot; it does not interpret the FON line state.

### D. Intermediate interface — CONFIRMED

- The intermediate is the QCA ADSS TDM/MBOX DMA frame, slot 5.
- It is not UART, not a shared-memory doorbell, not a Linux GPIO bit-bang.

## 9. TX/RX transport details (QCA ADSS)

Board DTS:

```text
tdm@0:  dma-tx-channel = MBOX0_TX_ID
        dma-rx-channel = MBOX3_RX_ID
        stereo-tx-port = STEREO0_ID
        stereo-rx-port = STEREO3_ID

pcm@7704000:
        dma-tx-channel = MBOX3_TX_ID
        dma-rx-channel = MBOX0_RX_ID
        stereo-tx-port = STEREO3_ID
        stereo-rx-port = STEREO0_ID
```

Both nodes are `status = "ok"` on the 7530. The TDM pin table in the same DTS
is:

```text
FSC   GPIO 22    FSC_2  GPIO 26
DCL   GPIO 21    DCL_2  GPIO 25
MCL   GPIO 20    MCL_2  GPIO 24
DI    GPIO 23    DO     GPIO 27
DECT reset GPIO 40, DECT ready GPIO 16
```

There is no SLIC reset/ring/hook GPIO in the board `avm_gpio` table.
`pcmlink`'s QCA path uses the `tdm_if_*` API; the source is available in the
GPL tarball:

```text
ipq-avm.c:30       tdm_if_config_init(slots, rxdelay, txdelay, master)
ipq-avm.c:72       tdm_if_dma_init(refhandle, TxData, RxData, cpu,
                                    only_rxirq, slots, fs_per_dma, desc_num)
ipq-adss-avm.c:2110 tdm_if_adss_config_init(...)
ipq-adss-avm.c:2188 tdm_if_adss_dma_init(...)
ipq-adss-avm.c:2234 tdm_if_adss_dma_start()
```

The ADSS implementation uses the **MBOX DMA** path, not a plain TDM FIFO:

```text
tdm_if_adss_dma_init()
  -> mbox_dma_init(PLAYBACK, ... MBOX tx ...)
  -> mbox_dma_init(CAPTURE, ... MBOX rx ...)
tdm_if_adss_dma_start()
  -> mbox_dma_prepare_desc()
  -> mbox_dma_prepare_reg()
  -> mbox_dma_start(PLAYBACK)
  -> wait for TX completion
  -> mbox_dma_start(CAPTURE)
```

Source constants:

```text
ipq-adss.h:33   ADSS_GLB_PCM_MBOX_CTRL_REG          0x0c
ipq-adss.h:112  ADSS_MBOXn_MBOX_DMA_POLICY_REG      0x10
ipq-adss.h:121  ADSS_MBOXn_DMA_RX_DESCRIPTOR_BASE   0x18
ipq-adss.h:128  ADSS_MBOXn_DMA_TX_DESCRIPTOR_BASE   0x20
```

The DMA descriptor is `struct _mbox_desc` (`ipq-adss-avm.c:128`), with
`BufPtr`, `NextPtr`, `size`, `length`, `OWN`, `EOM`, and related fields. The
descriptors and buffers are normal coherent DMA memory; the ADSS hardware
performs the transfer. `TxDMA`/`PutRxDMA` are the callbacks that fill/consume
the DMA buffers.

### Frame layout (confirmed from TxDMA/PutRxDMA)

For 16-bit slots, `TxDMA` writes a fixed header and the control word at byte
offset `0x0a`; `PutRxDMA` reads the status word at the same offset:

```text
byte offset  slot   TX value                 RX value
0x00         0      0x0000                   header/sync
0x02         1      0xfefe                   header/sync
0x04         2      0xfefe                   header/sync
0x06         3      0xfefe                   header/sync
0x08         4      0x5555 or 0             header/sync
0x0a         5      FON control word        FON status word
0x0c..               audio codec slots       audio codec slots
```

The exact meaning of the header words is AVM/DECT-specific; they are not FON
registers. What matters is that the FON control/status word is **slot 5** and
is carried in the same DMA frame as the audio.

### Wire-message format (confirmed size, limited semantics)

```c
/* Linux-side command ring entry: 8 bytes */
struct pcmlink_ul_cmd {
        uint32_t value;      /* +0x00: final masked value */
        uint16_t reg_word;   /* +0x04: virtual register / 4 */
        uint16_t flags;      /* +0x06: observed 1; exact meaning unknown */
};

/* On the TDM/MBOX wire: one 16-bit word in slot 5 */
u16 tx_slot5;   /* control */
u16 rx_slot5;   /* status */
```

There is **no opcode, explicit register address, mask, sequence number or
per-write ACK** in the wire word. The register address is implicit in slot 5;
the mask is applied in `lpcmlink_ul_writeregister` before the ring entry is
created. The control/status words are periodic per-frame values, not
transaction messages. The 8-byte ring is an internal Linux-to-TxDMA queue, not
the wire protocol.

## 10. Can a small independent driver replace PCMLINK?

### What is now known

- The FON control word is not a mysterious shared-memory protocol; it is a
  **16-bit word in TX TDM/MBOX slot 5**.
- The hook status is a **16-bit word in RX TDM/MBOX slot 5**, decoded into
  register `0x44` bit 7.
- Audio/control share the ADSS MBOX DMA frame; the QCA vendor source is
  available and shows how to initialize TDM, MBOX DMA, descriptors and
  interrupts.

### Minimum independent implementation

1. **QCA ADSS/TDM backend**: port the relevant `tdm_if_adss_*` and MBOX DMA
   code from the 4.4.271 GPL source to Linux 6.12, or write an equivalent
   DMA-engine/ALSA DAI driver. Use the board DTS channel mapping.
2. **DMA buffers/descriptors**: allocate coherent buffers, set
   `ADSS_MBOXn_DMA_TX/RX_DESCRIPTOR_BASE`, policy, interrupts, and start TX/RX.
3. **TX frame builder**: build slot 5 control words using the confirmed
   `build_slic_ctrl`/`_buildslic_ctrl_ring` mapping; preserve the AVM header
   words until their DECT-side meaning is proven.
4. **RX frame parser**: extract slot 5 status; map bit 3 to hook bit 7 (or
   first prove the SC14448 status assignment).
5. **Control API**: small character device/sysfs/ioctl for hook read, line
   state, ring cadence.
6. **ALSA PCM**: one 8 kHz, 16-bit PCM device over the audio slots; ALSA SoC
   is still preferable to DAHDI.

### Standard Linux 6.12 APIs

| Need | API | Status |
|---|---|---|
| TDM/MBOX pin mux | pinctrl/GPIO | available |
| clocks/resets | clk/reset frameworks | available |
| DMA buffers/descriptors | DMA engine or dma_alloc_coherent | available; ADSS programming missing |
| ALSA PCM | ASoC DAI/PCM | available |
| Hook/ring control | custom ioctl/sysfs | implement |
| ADSS register programming | vendor/GPL port | **main work item** |
| SC14448 control semantics | datasheet/firmware/trace | **unknown** |

DAHDI does not reduce the work; it still needs the same ADSS DMA backend.

### Verdict

**CONDITIONAL GO**, with a much better-defined boundary than before:

- The Linux-to-transport path is recovered.
- The remaining hard blockers are:
  1. porting the QCA ADSS/TDM/MBOX driver to 6.12;
  2. proving the SC14448 interpretation of control/status slot 5 and the
     high-voltage/ring circuit;
  3. validating safe ring/line-feed behavior on a bench.

If the SC14448 firmware is required and cannot be driven without the AVM
firmware/protocol, a standalone module is **NO-GO** unless the control slot is
fully reverse-engineered or the SC14448 is bypassed in hardware.

## 11. Reproducible commands and scripts

Install analysis dependencies:

```sh
python3 -m venv .venv-analysis
.venv-analysis/bin/pip install -r tools/requirements.txt
```

List symbols:

```sh
.venv-analysis/bin/python tools/pcmlink_regs.py \
  --module modules/ubik2/pcmlink.ko --list 'pcmlink_ul'
```

Disassemble a function with PC-literal/relocation annotations:

```sh
.venv-analysis/bin/python tools/pcmlink_regs.py \
  --module modules/ubik2/pcmlink.ko --disasm pcmlink_ul_writeregister

.venv-analysis/bin/python tools/pcmlink_regs.py \
  --module modules/ubik2/pcmlink.ko --disasm TxDMA --length 0x400

.venv-analysis/bin/python tools/pcmlink_regs.py \
  --module modules/ubik2/pcmlink.ko --disasm PutRxDMA --length 0x200
```

Dump the register metadata:

```sh
.venv-analysis/bin/python tools/pcmlink_regs.py \
  --module modules/ubik2/pcmlink.ko --metadata
```

Find relocation references:

```sh
.venv-analysis/bin/python tools/pcmlink_regs.py \
  --module modules/ubik2/pcmlink.ko --xrefs FPGALink_SharedMemory
```

The script only reads the ELF; it never loads/executes the module.

## 12. Remaining unknowns and next experiments

1. **SC14448 slot-5 protocol**: inspect the second-level firmware with a CR16C
   disassembler and the SC14448 peripheral map; locate the PCM/MBOX interrupt
   handler and the code that reads/writes slot 5.
2. **Exact control/status bit meanings**: use a read-only logic analyzer or
   PCM capture on a stock 7530 while toggling hook/ring; compare slot 5 with
   the virtual-register writes. This is the most direct confirmation.
3. **Which DTS path is active**: both `tdm@0` and `pcm@7704000` are enabled.
   Confirm whether `pcmlink` binds to `qca,ipq4019-tdm` (MBOX0 TX/MBOX3 RX) or
   `qca,ipq4019-pcm` (MBOX3 TX/MBOX0 RX) by runtime trace or module debug.
4. **High-voltage/ring topology**: trace LM324/BCP53-16, transformer and
   SC14448 GPIO/PWM/ADC connections; do not power the line for continuity
   checks.
5. **QCA ADSS 6.12 port**: start from `ipq-adss-avm.c`/`ipq-avm.c`, remove
   AVM FASTIRQ/RTE dependencies, and map to DMA engine/ALSA.
6. **SC14448 firmware dependency**: determine whether FON control survives a
   stock DECT firmware load only, or whether a FON-only firmware image is
   required. Do not assume the DECT firmware is optional.

## 13. Confidence summary

| Claim | Status | Evidence |
|---|---|---|
| `pcmlink_ul_writeregister` enqueues an 8-byte ring command | CONFIRMED | `0x3840..0x3868` |
| `pcmlink_ul_readregister` returns a cached/current table value | CONFIRMED | `0x32d0..0x32ec` |
| `TxDMA` consumes the ring | CONFIRMED | `0x9768..0x9984` |
| TX control word is at frame offset `0x0a` | CONFIRMED | `0x98cc..0x98e0` |
| RX status word is at frame offset `0x0a` | CONFIRMED | `0x9b38..0x9b90` |
| Hook bit 7 comes from RX status bit 3 | CONFIRMED (bit mapping) | `0x9b74..0x9b90` |
| Transport is QCA ADSS MBOX/TDM DMA | CONFIRMED | board DTS, `ipq-adss-avm.c` |
| Receiver is SC14448 | INFERRED, high | board inventory, 6-slot PCM, no other controller |
| Exact SC14448 bit semantics | UNKNOWN | no datasheet/firmware proof |
| FON UART protocol | DISPROVED | no UART imports/path |
| Separate SPI/I2C SLIC IC | DISPROVED | no chip/driver/GPIO; discrete LM324/BCP53 |
| `pcmlink_ll_set_status` is the FON register transport | DISPROVED | register path uses ring/TxDMA; Set_Status is separate |
