# fon-slot5-protocol

Offline reference encoder/decoder for the Linux-side `pcmlink` slot-5
control/status words.

> **Status: reconstruction of the Linux-side data transformation only.**
> No hardware, MMIO, DMA, GPIO, clock, reset or firmware is accessed.  The
> SC14448-side interpretation and the physical wire bit order remain
> **UNKNOWN**.

## 1. Control word

`build_slic_ctrl()` (`pcmlink.ko` `0x8f68`):

```text
if special_field != 0:
    return special_field | 0x8000

ctrl = ((reg48 >> 3) & 0x1e0)
     | ((reg48 >> 4) & 0x00f)

if reg2c & (1 << 17): ctrl |= 0x010
if reg2c & (1 << 18): ctrl |= 0x200

return ctrl | 0x4000
```

Bit sources:

| TX bit | Source | Linux-side status |
|---:|---|---|
| 0-3 | reg 0x48 bits 4-7 | **DISASM** |
| 4 | reg 0x2c bit 17 | **DISASM** |
| 5-8 | reg 0x48 bits 8-11 | **DISASM** |
| 9 | reg 0x2c bit 18 | **DISASM** |
| 10-13 | not set by the normal path | **DISASM** |
| 14 | constant `0x4000` | **DISASM** |
| 15 | not set by normal; set by special path | **DISASM** |

`0x4000` and `0x8000` are reported only as **markers**.  Their hardware
meaning is not established.

The special path is fed from `TDMPriv+0x7f4`, which is updated by the TX
command for register word `0x30`; it is not a generic ring-enable bit.

## 2. Status word

`PutRxDMA()` (`pcmlink.ko` `0x9a60`):

```text
if status & 0x8000:
    no register-0x44 update
else:
    reg44 = 0x00020008
          | ((status << 3) & 0x00000f00)
          | ((status << 4) & 0x000000ff)
```

| RX status bits | Register-0x44 bits |
|---|---|
| 0-3 | 4-7 |
| 5-8 | 8-11 |
| 4, 9-15 | not represented in reg44 |
| 15 | special: no reg44 update |

Hook for SLIC0 is `reg44` bit 7, therefore RX status bit 3.  The name
"hook" is inferred from the caller; it is not a datasheet claim.

## 3. Frame layout

The logical eight-word frame used by the existing reconstruction:

```text
slot 0: 0x0000
slot 1: 0xfefe
slot 2: 0xfefe
slot 3: 0xfefe
slot 4: 0x5555 (suppressed to 0 when TDMPriv+0x808 != 0)
slot 5: control word
slot 6: audio
slot 7: audio
```

The library leaves slots 6/7 zero for the caller's audio path.

`TxDMA` writes through an ARM `strh` address `EOR #2` transformation.  E1
resolved it as an adjacent-halfword swap inside each 32-bit DMA word.  The
logical encoder is kept separate from the raw-DMA helper:

```c
fon_slot5_frame_to_raw(logical, raw);
fon_slot5_raw_to_frame(raw, logical);
```

The raw model is proven; the physical TDM wire order remains **UNKNOWN**.
See `docs/history/fon-e1-dma-byte-order.md`.

## 4. Build and test

```sh
make
make test
```

`make test` runs golden vectors with literal expected values and a static
check that the library contains no hardware accessors.  It does not execute
firmware or touch a router.

## 5. Limits

- `FON_SLOT5_STATUS_NO_UPDATE` is the library's sentinel for RX status bit 15;
  `PutRxDMA` simply skips the reg44 store in that case.
- No claim is made that `0x4000`/`0x8000` mean idle/ring or any other
  hardware mode.
- No claim is made about the SC14448 firmware interpretation, PCM slot
  number, or physical bit order.
