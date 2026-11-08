# SC14448 <-> PCMLINK slot-5 protocol

> **Status: offline specification of the proven Linux-side protocol.**
> The SC14448 firmware interpretation and the physical electrical layer remain
> **UNKNOWN**.  This document does not authorize firmware upload, TDM/DMA,
> GPIO40 reset or line/ring.

Sources: `pcmlink.ko` `6620510b…a363b`, `isdn_fbox_fon5.ko`
`47e0e29b…dbd2c9`, the AVM GPL ADSS source, and the local CR16 reports.  No
AVM binary is committed.

---

## 1. Transport

```text
isdn_fbox_fon5
  -> pcmlink virtual registers
  -> 64-entry command ring
  -> TxDMA
  -> slot-5 control word
  -> QCA ADSS TDM/MBOX DMA
  -> 8 kHz, 8 x 16-bit PCM frame
  -> SC14448 PCM+ interface (consumer inferred)
  -> analog FON hardware (electrical topology unknown)

SC14448 -> RX slot-5 status
  -> PutRxDMA
  -> virtual register 0x44
  -> hook/state polling in isdn_fbox_fon5
```

## 2. Frame geometry

| Quantity | Value | Status |
|---|---|---|
| Frame rate | 8000 Hz | confirmed Linux/DTS |
| Physical slots | 8 | confirmed Linux |
| Slot width | 16 bit | confirmed Linux |
| Frame size | 16 bytes | confirmed Linux |
| BCLK nominal | 1.024 MHz | formula; external source not measured |
| TDM role | IPQ4019 ADSS slave; SC14448 supplies clocks | inferred high |
| Logical codec slots | `Codecslots=9` in OEM 08.25 runtime; `Codecslots=6` in older wiki build | both recorded; **not physical slot count** |

Nine logical codec slots do **not** mean nine physical 16-bit slots.  The
ADSS hardware channel is programmed for 8 physical slots; the logical codec
count is a separate AVM allocation.

## 3. TX logical frame

The Linux-side reconstruction uses this logical order:

| Slot | Value | Evidence |
|---:|---|---|
| 0 | `0x0000` | `TxDMA` fixed header |
| 1 | `0xfefe` | `TxDMA` fixed header |
| 2 | `0xfefe` | `TxDMA` fixed header |
| 3 | `0xfefe` | `TxDMA` fixed header |
| 4 | `0x5555`, or `0` when `TDMPriv+0x808 != 0` | `TxDMA` fixed header |
| 5 | FON control word | `TDMPriv+0x7fc` / `tx+0x0a` hypothesis |
| 6 | audio | filled by `generic_slotinterleave`/audio path |
| 7 | audio | filled by `generic_slotinterleave`/audio path |

**EOR #2 (resolved at the memory level):** `TxDMA`/`PutRxDMA` swap adjacent
16-bit slots inside each 32-bit DMA word.  The logical slot-5 word appears at
raw 16-bit index 4 / byte offset `0x08`; the logical map remains the order
above.  The raw memory model is proven by the ARM instructions and covered by
`history/fon-e1-dma-byte-order.md`.  E2 confirmed that
`generic_slotinterleave` also uses `EOR #2` for the audio stores; the
header/control raw order is proven, while audio sample order/endianness is
**MODEL / INFERRED**.  The final DMA presentation/physical wire order is still
**UNKNOWN** and is the remaining Q74 caveat.

`0xfefe` and `0x5555` are Linux-side frame constants.  They are **not**
claimed to be universal SC14448 sync words.

## 4. TX control word

`build_slic_ctrl()`:

```text
if special != 0: return special | 0x8000

ctrl = ((reg48 >> 3) & 0x1e0) | ((reg48 >> 4) & 0xf)
if reg2c & BIT(17): ctrl |= 0x010
if reg2c & BIT(18): ctrl |= 0x200
return ctrl | 0x4000
```

| Bit | Source | SC14448 meaning |
|---:|---|---|
| 0-3 | reg 0x48 bits 4-7 | UNKNOWN |
| 4 | reg 0x2c bit 17 | UNKNOWN |
| 5-8 | reg 0x48 bits 8-11 | UNKNOWN |
| 9 | reg 0x2c bit 18 | UNKNOWN |
| 10-13 | normal path zero; special can carry | UNKNOWN |
| 14 | `0x4000` normal marker | UNKNOWN |
| 15 | `0x8000` special marker | UNKNOWN |

The special path is fed by `TDMPriv+0x7f4`, written by the command for register
word `0x30`.  `0x4000` is not proven to mean idle; `0x8000` is not proven to
mean ring.

## 5. RX status word

`PutRxDMA()`:

```text
if status & 0x8000: no reg44 update
else:
    reg44 = 0x00020008
          | ((status << 3) & 0xf00)
          | ((status << 4) & 0xff)
```

| RX bit | reg 0x44 | Meaning |
|---:|---|---|
| 0-3 | bits 4-7 | UNKNOWN; bit 3 -> hook bit 7 |
| 4 | not mapped | UNKNOWN |
| 5-8 | bits 8-11 | UNKNOWN |
| 9-14 | not mapped | UNKNOWN |
| 15 | no reg44 update | UNKNOWN marker |

Raw status `0` is stored as `0xbad00000` in `TDMPriv+0x73c`; status `0x8000`
is stored raw and suppresses reg44; `0x4000` updates reg44.  Hook is
`(reg44 >> 7) & 1`, i.e. RX bit 3, **inferred** to be hook/line state.

## 6. Virtual registers

| Register | Use | Read mask | Notes |
|---:|---|---:|---|
| `0x2c` | control source bits 17/18 | FON metadata | also other line state |
| `0x30` | special field -> `TDMPriv+0x7f4` | — | TX special marker source |
| `0x40` | line/bring-up | `0xfeeff000` | bit effects unknown |
| `0x44` | RX status/hook | `0x01100fff` | bit 7 hook |
| `0x48` | line/ring control | `0xfeeff000` | bits 5/6 SLIC0 |
| `0x4c` | line/status | `0x00001111` | unknown |
| `0x50` | line/status | `0x00001111` | unknown |
| `0x64` | bring-up | — | value 0, mask 1 in reset path |

## 7. Command ring and update timing

- ring: 64 entries x 8 bytes at shared window `+0x68`;
- entry: `{u32 value, u16 reg_word, u16 flags}`;
- `flags` is used as a frame-delay gate: `frame_counter < flags << 3` skips;
- writes are asynchronous; no per-write ACK;
- retry compares shadow/current later; overflow logs and drops;
- `TDMPriv+0x7fc` holds the current control word;
- exact maximum commands per DMA callback is **not proven**;
- initial `TDMPriv+0x7fc` before the first command is **not established**.

## 8. Ring cadence

`slic_set_ring` writes reg 0x48 bits 5/6 for SLIC0.  The analog timer
`Handle_Ints_FPGA` toggles them; `set_slic_ringfreq` computes
`half_period = (500 / freq) << 3` frames, default 25 Hz.  This is software
cadence; it is not a proven high-voltage waveform.

## 9. Initialization / idle

The Linux-side `slics_reset` sequence is recovered in
`history/fon-e0-analog-state-machine.md`: reg 0x48/0x40 writes, a 200 ms
bring-up/ring pulse, hook polls and idle writes.  The numeric idle/ring
semantics remain unknown, and the SC14448 firmware path is unproven.

## 10. Firmware interpretation

No slot-5 handler was found in the resolved CR16 map.  The only resolved
PCM-adjacent accesses are the `0xF6002` poll, `0x00FF6006` pulse/clear,
`0xF6006` reads and interrupt-controller writes.  Indirect/cross-block code
remains the open possibility.  See
`history/fon-e0-sc14448-firmware-search.md`.

E2 expanded this to call continuations, direct-call summaries, table-consumer
candidates and all 31 IRQ vectors.  It still found no proven slot-5 consumer:
the closest IRQ path is `dip_int`, which reads `0xF6006` and writes
`0xF5402 = 0x400` in both images, but that is not a proven control-word
handler.  The `0x01000000 + 2*index` writer remains a loader/RAM-init
candidate with no resolved reader.  See `fon-e2-summary.md`.

## 11. Minimum standalone driver

A transport-only harness can be written from the Linux-side formulas.  A
functional FON driver additionally requires:

- proof of the SC14448 slot-5 consumer and bit semantics;
- the analog line/ring topology and safe test load;
- reset/firmware sequencing only after separate approval.

Until then, the minimum safe deliverable is an offline encoder/decoder plus a
read-only transport test plan.  It must not drive ringing or line feed.
