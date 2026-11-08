# FON-E0 — TX slot-5 control reconstruction

> **Status: offline static analysis.**
> Source: `pcmlink.ko` SHA256
> `6620510bc1d4b0f4d670e1e93d3f308dc3002785d3129521156eb5e1bc4a363b`.
> No router, MMIO, DMA, GPIO, clock, reset or firmware was accessed.

This document refines the Linux-side TX path.  It does **not** establish the
SC14448 meaning of any bit.

---

## 1. Exact functions

| Function | Address | Role |
|---|---:|---|
| `build_slic_ctrl` | `0x8f68` | normal/special 16-bit control word |
| `_buildslic_ctrl_ring` | `0x8fb0` | ring phase toggles on an existing word |
| `set_slic_ringfreq` | `0x9084` | half-period counter |
| `TxDMA` | `0x9710` | consume command ring, build frame |
| `fpgadata_init` | `0x93d8` | zero shared window / link state |

## 2. Normal control word

`build_slic_ctrl(r0=value table, r1=special_field)`:

```text
if (special_field != 0)
    return special_field | 0x8000;

v48 = *(u32 *)(r0 + 0x24c);  /* value table entry for 0x48 */
v2c = *(u32 *)(r0 + 0x230);  /* value table entry for 0x2c */

ctrl = ((v48 >> 3) & 0x1e0)
     | ((v48 >> 4) & 0x00f);

if (v2c & BIT(17)) ctrl |= 0x010;
if (v2c & BIT(18)) ctrl |= 0x200;

return ctrl | 0x4000;
```

The instruction sequence at `0x8f78..0x8fac` matches this exactly:
`ldr`/`ubfx`/`lsr`/`and`/`orr`/`tst`/`orrne`.

### 2.1 TX bit table

| TX bit | Source | Linux-side proof | SC14448 semantics |
|---:|---|---|---|
| 0 | reg 0x48 bit 4 | `v48 >> 4 & 0xf` | **UNKNOWN** |
| 1 | reg 0x48 bit 5 | same; also ring toggle path | **UNKNOWN** |
| 2 | reg 0x48 bit 6 | same; also ring toggle path | **UNKNOWN** |
| 3 | reg 0x48 bit 7 | same | **UNKNOWN** |
| 4 | reg 0x2c bit 17 | `tst #0x20000; orrne #0x10` | **UNKNOWN** |
| 5 | reg 0x48 bit 8 | `v48 >> 3 & 0x1e0` | **UNKNOWN** |
| 6 | reg 0x48 bit 9 | same | **UNKNOWN** |
| 7 | reg 0x48 bit 10 | same | **UNKNOWN** |
| 8 | reg 0x48 bit 11 | same | **UNKNOWN** |
| 9 | reg 0x2c bit 18 | `tst #0x40000; orrne #0x200` | **UNKNOWN** |
| 10-13 | not set in normal path | normal path clears | special path may carry them |
| 14 | constant `0x4000` | `orr #0x4000` | **UNKNOWN marker** |
| 15 | `0x8000` special path | `orr #0x8000` on special | **UNKNOWN marker** |

Do not name bits `RING_ENABLE`, `BATTERY_ON`, `LINE_FEED`, etc.  The names are
not proven.

`0x4000` is **not** proven to be a safe idle command.  It is only the normal
control marker generated after a non-special path.

## 3. Special path

`TxDMA` handles the register-word switch at `0x9928..0x9954`:

| reg_word | Register | Action |
|---:|---:|---|
| `0x0b` | `0x2c` | normal `build_slic_ctrl` |
| `0x0c` | `0x30` | writes value table, sets `TDMPriv+0x7f4=value`, `+0x7f6=5` |
| `0x10` | `0x40` | normal `build_slic_ctrl` |
| `0x11` | `0x44` | value table only |
| `0x12` | `0x48` | normal `build_slic_ctrl` |

The special field at `TDMPriv+0x7f4` is therefore fed by the command for
register `0x30`, not by a generic "ring enable" register.  When non-zero,
`build_slic_ctrl` returns `special_field | 0x8000`.

The ring builder `_buildslic_ctrl_ring` is separate: it clears/sets bits 1/2
for SLIC0 and 6/7 for SLIC1 on an existing word, using a half-period counter.

## 4. Command ring and timing

`lpcmlink_ul_writeregister` (`0x34b8`) enqueues an 8-byte entry:

```c
struct pcmlink_ul_cmd {
        uint32_t value;      /* +0x00 */
        uint16_t reg_word;   /* +0x04, register >> 2 */
        uint16_t flags;      /* +0x06 */
};
```

`TxDMA` uses `flags` as a delay gate:

```text
frame_counter = [TDMPriv + 0x7f8]
if (frame_counter < (flags << 3))
        skip this command
```

The exact upper bound on commands consumed per DMA callback is **not**
proven.  The code advances the consumer by one entry in the command block and
can re-enter that block inside the frame loop; the workspace therefore must
not state "exactly one command per frame" without a trace.  The per-write ACK
is absent; the retry handler compares shadow/current values later.

`TDMPriv+0x7fc` is the current control word.  It is updated only from the
normal `0x2c`/`0x40`/`0x48` path or the special `0x30` path; `0x44` only
updates the value table entry.

## 5. Frame bytes and the EOR #2 caveat

`TxDMA` builds the fixed header and control slot with `strh` stores whose
address is XORed by 2.  For a 4-byte-aligned frame base `B`, the raw stores are:

```text
B+0x02 <- 0x0000
B+0x00 <- 0xfefe
B+0x06 <- 0xfefe
B+0x04 <- 0xfefe
B+0x0a <- 0x5555 (or 0)
B+0x08 <- control
```

The existing `fon-tdm-hardware.md` describes the logical order as
`[0]=0, [1..3]=0xfefe, [4]=0x5555, [5]=control` at byte offsets
`0x00..0x0a`.  The two descriptions differ because of the `EOR #2`
byte/halfword representation.

**E1 resolution:** `EOR #2` swaps adjacent 16-bit slots inside each 32-bit
DMA word.  The raw memory order is now proven; the logical slot-5 mapping is
coherent with it.  The remaining unknown is the DMA presentation/physical
wire order, not the ARM address arithmetic.  See
`fon-e1-dma-byte-order.md`.

Slots 6/7 are audio; `TxDMA` does not write them directly.  They are filled
by `generic_slotinterleave`/the audio path; their exact content is outside
this control-word reconstruction.

## 6. Ring cadence

`set_slic_ringfreq` computes:

```text
half_period = (500 / ring_frequency) << 3
```

with default 25 Hz.  `_buildslic_ctrl_ring` increments per-SLIC counters and
toggles SLIC0 bits 1/2 or SLIC1 bits 6/7 when the counter reaches the
half-period.  This is a software cadence; it is not a proven electrical ring
waveform.

## 7. What remains unknown

- SC14448 meaning of every bit and marker;
- whether `0x4000`/`0x8000` are mode markers, strobes or data qualifiers;
- physical slot/byte-order resolution of the `EOR #2` path;
- firmware-side consumer of slot 5;
- high-voltage ring/line-feed generation.
