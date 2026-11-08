# FON-E1 — TX DMA `EOR #2` byte-order model

> **Status: offline ARM/Linux + QCA-source analysis.**  No hardware.

This is the separate Q74 task: explain the mismatch between the logical frame
order and the raw halfword stores in `TxDMA`.

---

## 1. ARM address arithmetic

For a 4-byte-aligned frame base `B`, `strh rX,[r3]` with `r3 = (B + off) ^ 2`
stores at the adjacent halfword address:

```text
(B + 0) ^ 2 = B + 2
(B + 2) ^ 2 = B + 0
(B + 4) ^ 2 = B + 6
(B + 6) ^ 2 = B + 4
(B + 8) ^ 2 = B + a
(B + a) ^ 2 = B + 8
```

So the transformation is **not a byte swap inside a 16-bit word**.  It swaps
two adjacent 16-bit slots inside each 32-bit DMA word.

## 2. Raw memory after TxDMA

For the logical frame:

```text
L = [0x0000, 0xfefe, 0xfefe, 0xfefe, 0x5555, control, audio6, audio7]
```

the stores produce:

```text
raw[0] = L[1] = 0xfefe
raw[1] = L[0] = 0x0000
raw[2] = L[3] = 0xfefe
raw[3] = L[2] = 0xfefe
raw[4] = L[5] = control
raw[5] = L[4] = 0x5555
raw[6] = L[7] = audio7
raw[7] = L[6] = audio6
```

The logical slot-5 control is at raw 16-bit index 4, i.e. byte offset `0x08`.
`PutRxDMA` reads status through the same `EOR #2` path, so its raw read is
also index 4.  This resolves why the raw store/read addresses looked like
`0x08` while the existing logical map calls the word slot 5.

## 3. QCA ADSS/MBOX policy

The AVM GPL source has:

```c
#define MBOX_DMA_POLICY_RXD_16BIT_SWAP BIT(10)
#define MBOX_DMA_POLICY_RXD_END_SWAP    BIT(8)
```

but the observed `mbox_dma_policy_reset()` leaves the swap bits unset and
contains the comment:

```c
/*--- val |= MBOX_DMA_POLICY_RXD_16BIT_SWAP | MBOX_DMA_POLICY_RXD_END_SWAP; ??? ---*/
```

No TX-side 16-bit-swap definition was found in that source.  Therefore:

- the **raw Linux memory order** is proven by the ARM instruction arithmetic;
- the **logical slot order** is coherent with the pair swap;
- the **DMA presentation/physical wire order** is not proven by the GPL
  source alone.

The AVM policy comment is evidence of uncertainty in the vendor source, not
proof that the swap is disabled at runtime.

## 4. Library support

`tools/fon-slot5-protocol/` now provides, separately from the logical encoder:

```c
fon_slot5_frame_to_raw(logical, raw);
fon_slot5_raw_to_frame(raw, logical);
```

The golden test covers all eight words, round-trip, and the raw order above.
The logical encoder is not changed to emit a guessed physical order.

## 5. Q74 status

**Partial:** logical header/control values and the raw pair-swap model are
proven; physical wire order remains **UNKNOWN**.  A future hardware trace is
required for the last step.
