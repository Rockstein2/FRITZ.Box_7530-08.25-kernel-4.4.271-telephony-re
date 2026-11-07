# SC14448: hypotheses about PCM/TDM, with evidence levels

Status: **offline analysis.**  Levels: L1 bytes, L2 decode, L3 CFG,
L4 semantics under stated ISA assumptions, **L5 requires hardware and is not
reached**.  Agreement between two software tools that share binutils is not
independent evidence.

The purpose of this document is to keep hypotheses about PCM/TDM separate
from confirmed facts.  Each row says what supports the hypothesis, what
contradicts it, and which observation would settle it.

---

## 1. The known host-side frame (for reference only)

On the IPQ4019 side the TDM link is configured by AVM's audio driver in the
GPL source: 8 kHz frame rate, 8 slots, 16 bits per slot, and the slot-5
control word carries FON control.  This is host code, not SC14448 firmware,
and it says nothing about what the SC14448 expects.

## 2. Hypotheses

### H1 — `0x000F6002 == 1` means "the operation started at `0xFF6006` finished"

| | |
|---|---|
| Supporting | `0x25FAE`–`0x25FB4`: read, compare with 1, loop. It follows `0x2558`, which pulsed `0x80`. The register has exactly one access in each image (a read). |
| Contradicting | no writer exists in the firmware; nothing shows what sets it |
| Missing | an L5 observation: set the register to 1 from a debugger/host and see whether the loop exits, and whether `0x80` is needed first |
| Confidence | **low-medium** |

### H2 — `0x000F6006` bit 7 is a start/commit strobe for whatever `0x000F6002` reports

| | |
|---|---|
| Supporting | three independent routines write exactly `0x0080` (`0x1348`, `0x145C`, `0x258C`); `0x25B4` clears it again; the write at `0x25B0`–`0x25B4` is bracketed by the poll |
| Contradicting | `0x145C` writes `0x80` without a following poll in the same routine |
| Missing | what changes between the set and the clear: any other register, the poll value, or a pin |
| Confidence | **medium** for "strobe", **none** for "PCM start" |

### H3 — `0x000F5402` selects a channel or a divider

| | |
|---|---|
| Supporting | written with four distinct values (`0x0400`, `0x2000`, `0x0100`, `0xFFFF`) from seven sites; `0x0400` follows every read of `0x000F6006` |
| Contradicting | no read-back anywhere, so it could equally be a strobe with a payload |
| Missing | the effect of changing one of the four values while the chip runs |
| Confidence | **low** |

### H4 — `0x01000000` is a buffer the hardware reads, 511 words of `0x1001`

| | |
|---|---|
| Supporting | 511 sequential 16-bit writes; the base is not inside any loaded code run; five other routines load the same base; `0x25BA` is a generic "store and advance the counter" helper reused with other values (`0x901` at `0x26020`) |
| Contradicting | no reader of the area was found; `0x1001` appears nowhere else in either image |
| Missing | a reader: a routine that loads `0x01000000` and reads with an index, or a DMA descriptor pointing there |
| Confidence | **low** for "PCM buffer", **medium** that it is a data area written by the firmware |

### H5 — `0x1001` is a per-slot pattern, not a configuration word

| | |
|---|---|
| Supporting | the value is repeated 511 times, so per-element meaning is more likely than a one-off control word; the same helper writes `0x901` elsewhere |
| Contradicting | nothing |
| Missing | a second routine writing a different constant pattern into the same area, or a reader that interprets the field |
| Confidence | **low** |

### H6 — the sequence involves a PCM/TDM block at all

| | |
|---|---|
| Supporting | the register set it touches (`0x000F6xxx`) and the `0xFF6xxx` block are adjacent in address space to the blocks used for GPIO (`0xFF48xx`) and timers (`0xFF58xx`), so a separate `0x6000` block exists; `0xFF600E` is loaded at `0x1486` into `r12` (a single register, not a pair) |
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

## 3. What the firmware does *not* contain

Searched for, and not found, in either image:

* any 8 kHz / 8000 / 125 µs constant;
* a loop whose trip count is 8, 16 or 128 in a register-fill pattern;
* any read back from `0x01000000`;
* any write to `0x000F6002`;
* a second writer of `0x000F6400`/`0x000F6402`;
* a write of any value other than `0x0080` to `0x000F6006`.

This list is a statement about what the scanner can see (§1 of
`fon-dialog-peripheral-xrefs.md`), not a proof of absence.

## 4. Verdict

There is **no demonstrated link** between `0x25F90`, the registers it touches
and a PCM/TDM interface.  The strongest statement the evidence supports is:

> the firmware writes a constant pattern into an unidentified RAM area,
> stores two constants into an unidentified register pair, pulses one bit of
> `0x000F6006`, edits four bits of `0x00FF5406`, writes `0x0400` to
> `0x000F5402`, clears the pulse and then waits for `0x000F6002` to read 1.

The single observation that would establish or refute the link is in
`fon-dialog-hw-test-plan.md`.
