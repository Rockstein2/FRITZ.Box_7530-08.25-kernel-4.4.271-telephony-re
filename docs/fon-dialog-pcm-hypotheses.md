# SC14448: hypotheses about PCM/TDM, with evidence levels

Status: **offline analysis.**  Levels: L1 bytes, L2 decode, L3 CFG,
L4 semantics under stated ISA assumptions, **L5 requires hardware and is not
reached**.  Agreement between two software tools that share binutils is not
independent evidence.

The purpose of this document is to keep hypotheses about PCM/TDM separate
from confirmed facts.  Each row says what supports the hypothesis, what
contradicts it, and which observation would settle it.

**Address discipline.**  `0x000F6006` and `0x00FF6006` are different
addresses with different sets of writers.  No hypothesis below may treat them
as one register unless it says so explicitly and marks that step as unproven.

---

## 1. The known host-side frame (for reference only)

On the IPQ4019 side the TDM link is configured by AVM's audio driver in the
GPL source: 8 kHz frame rate, 8 slots, 16 bits per slot, and the slot-5
control word carries FON control.  This is host code, not SC14448 firmware,
and it says nothing about what the SC14448 expects.

## 2. Hypotheses

### H1 — `0x000F6002 == 1` means "the operation started in `0x2558` finished"

| | |
|---|---|
| Supporting | `0x25FAE`–`0x25FB4`: read, compare with 1, loop. It follows `0x2558`, which pulsed `0x0080` into `0x00FF6006` and edited `0x00FF5406`. `0x000F6002` has exactly one access in each image (a read). |
| Contradicting | no writer exists among the resolved forms; nothing shows what sets it; the poll is unbounded, so if it never becomes 1 the sequence never returns |
| Missing | an L5 observation: does the value change while the firmware runs this path |
| Confidence | **low-medium** |

### H2 — bit 7 of the `0x6006` register pair is a start/commit strobe

This hypothesis must be split: the two addresses have different evidence.

| | |
|---|---|
| Supporting (both) | `0x0080` is written and then cleared (`0x258C`→`0x25B4` for `0x00FF6006`); the `0x000F6006` writers `0x1348`/`0x145C` write the same value |
| Supporting (`0x00FF6006` only) | written at `0x258C`, read at `0x25AA`, cleared at `0x25B4`, all inside `0x2558`; the clear is immediately followed by the poll |
| Missing | whether the same value at two different addresses means the same hardware |
| Confidence | **medium** that `0x00FF6006` is pulsed inside `0x2558`, **none** for "PCM start", **none** for aliasing with `0x000F6006` |

Since PERIPH-2 the statement "three independent routines write `0x0080` to
`0x000F6006`" is withdrawn: only `0x1348` and `0x145C` write that address.

### H3 — `0x000F5402` selects a channel or a divider

| | |
|---|---|
| Supporting | written with four distinct values (`0x0400`, `0x2000`, `0x0100`, `0xFFFF`) from seven sites; `0x0400` follows every read of `0x000F6006` (`0x26034`, `0x28CE8`) and is written inside `0x2558` (`0x25B0`) |
| Contradicting | no read-back anywhere, so it could equally be a strobe with a payload |
| Missing | the effect of changing one of the four values while the chip runs |
| Confidence | **low** |

### H4 — `0x01000000` is a buffer the hardware reads, 511 words of `0x1001`

| | |
|---|---|
| Supporting | 511 sequential 16-bit writes; the base is not inside any loaded code run; other routines load the same base; the store address is `SYMBOLIC` (`0x01000000 + 2*r3`), consistent with an array |
| Contradicting | no numeric reader was found; `0x1001` appears nowhere else in either image |
| Missing | a reader: a routine that loads `0x01000000` and reads with an index, or a DMA descriptor pointing there |
| Confidence | **low** for "PCM buffer", **medium** that it is a data area written by the firmware |

### H5 — `0x1001` is a per-slot pattern, not a configuration word

| | |
|---|---|
| Supporting | the value is repeated 511 times, so per-element meaning is more likely than a one-off control word |
| Contradicting | `0x1001` is not reused anywhere; the constant `0x901` that appears in the image (`0x2E48`, `0x2EFA`, `0x2FEC`, `0x30BA`, `0x316E`) is loaded by different code, not by the fill helper |
| Missing | a second routine writing a different constant pattern into the same area, or a reader that interprets the field |
| Confidence | **low** |

### H6 — the sequence involves a PCM/TDM block at all

| | |
|---|---|
| Supporting | the sequence touches `0x000F6xxx`, `0x00FF6xxx` and `0x00FF54xx`, which sit in blocks adjacent to GPIO (`0xFF48xx`) and timers (`0xFF58xx`), so a separate `0x6000` block exists in both address spaces |
| Contradicting | no instruction in the sequence is conditioned on frame timing, no FIFO fill/drain loop, no 8 kHz or 8-slot constant, no interrupt entry |
| Missing | an L5 trace of which registers change once per frame |
| Confidence | **low** |

### H7 — there is no interrupt handler for this block in the firmware

| | |
|---|---|
| Supporting | the only entries to the sequence are the `bal` chain from `0x1602`; the poll loops are busy-waits; the sequence runs with interrupts disabled |
| Contradicting | the image is not fully classified; 11 230 instructions are not reached from `0x1602` and an indirect dispatch is not excluded |
| Missing | a full code/data classification and a check of the vector table that the CR16 uses for exceptions |
| Confidence | **low** |

### H8 — `0x00FF4C00` / `0x00FF5000` belong to the same block family as the other `0xFFxxxx` words

| | |
|---|---|
| Supporting | they are the only `abs24` accesses into the `0x00FFxxxx` space, both 8-bit constant stores located in one small block |
| Contradicting | 8-bit access width, while every neighbouring `0xFFxxxx` register is 16-bit; the block is not reached in mode A |
| Missing | any second access, or a hardware map |
| Confidence | **very low** |

## 3. What the firmware does *not* contain

Searched for, and not found, in either image:

* any 8 kHz / 8000 / 125 µs constant;
* a loop whose trip count is 8, 16 or 128 in a register-fill pattern;
* any numeric (resolved) read from `0x01000000`;
* any write to `0x000F6002`;
* a second writer of `0x000F6400`/`0x000F6402`;
* a write of any value other than `0x0080` to `0x000F6006`;
* any access at all to `0x00FF6400` or `0x00FF6402`.

This list is a statement about what the scanner can see (§1 of
`fon-dialog-peripheral-xrefs.md`), not a proof of absence.

## 4. Verdict

There is **no demonstrated link** between `0x25F90`, the registers it touches
and a PCM/TDM interface.  The strongest statement the evidence supports is:

> the firmware writes a constant pattern into an unidentified area at
> `0x01000000 + 2·index`, stores two constants (`0x0000`, `0x00F0`) into two
> `0x000F64xx` registers, writes `0x0080` into `0x00FF6006`, clears four bits
> of `0x00FF5406` under `di`, reads `0x00FF6006` back, writes `0x0400` to
> `0x000F5402`, clears `0x00FF6006` and then waits for `0x000F6002` to read 1.

The observation that would move this forward is described in
`fon-dialog-hw-test-plan.md`; it cannot by itself establish causation.
