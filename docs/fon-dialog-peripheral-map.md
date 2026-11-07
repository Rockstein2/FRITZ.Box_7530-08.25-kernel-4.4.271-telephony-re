# SC14448 peripheral map (address evidence only)

Status: **offline static analysis, L1/L2 only.**  This file groups every
address the scanner resolved into the block it belongs to, and states what is
proven about it.  **No block is named after a function** (PCM, codec, DMA…)
because no hardware document confirms any name.

All sites are from `dectfw_secondlevel_441.hex` unless marked *p2*, and were
produced by `tools/cr16_peripheral_xrefs.py`
(`tools/reports/peripheral-xrefs.json`).

---

## 1. Blocks observed

| Block (address range, neutral name) | Access sizes | Sites (normal) | What is proven |
|---|---|---|---|
| `0x00FF40xx` | 16-bit via `movd` pairs | `0xFF4000`, `0xFF4004`, `0xFF400A`, `0xFF4010`, `0xFF401C`; plus the abs20 registers `0xF4002`, `0xF4004`, `0xF4006`, `0xF400C`, `0xF400E`, `0xF4012` in the `0x000F40xx` row | a register array; `0xFF400A` is edited by `0x24F8` |
| `0x00FF48xx` | 16-bit via `movd` pairs | `0xFF4808`, `0xFF4810`, `0xFF4812`, `0xFF481E`, `0xFF4836`, `0xFF4838`, `0xFF4856`, `0xFF4858`, `0xFF4860`, `0xFF4866`, `0xFF4868` | a register array written in blocks (`0x11D4`–`0x14D6`) |
| `0x00FF49xx` | 16-bit | `0xFF4960` | single load of a base |
| `0x00FF54xx` | 16-bit | `0xFF5404`, `0xFF5406` | `0xFF5406` read-modify-written once; `0xFF5402` is the *abs20* register `0xF5402` below (separate row) |
| `0x00FF58xx` | 16-bit | `0xFF5800`, `0xFF5802`, `0xFF5804`, `0xFF5806`, `0xFF5808`, `0xFF580A`, `0xFF580C` | a small register array |
| `0x00FF60xx` | 16-bit | `0xFF6006` (3 sites), `0xFF600E` (1 `movd` into `r12`) | pulsed register |
| `0x00FF70xx` | 16-bit | `0xFF7052`, `0xFF7056`, `0xFF7070`, `0xFF7072`, `0xFF7080` | a register array |
| `0x000F40xx` | 16-bit | `0xF4002`, `0xF4004`, `0xF4006`, `0xF400C`, `0xF400E`, `0xF4012` | plain abs20 registers |
| `0x000F50xx` | 16-bit | `0xF5000`, `0xF5402`–`0xF540A`, `0xF580A`, `0xF580E` | plain abs20 registers |
| `0x000F60xx` | 16-bit | `0xF6002`, `0xF6006`, `0xF6400`, `0xF6402` | the sequence under study |
| `0x000F70xx` | 16-bit | `0xF7052`, `0xF7056` | two registers |
| `0x01000000` | 16-bit writes only | 6 `movd` literals, no linked access | a data area |

Two families exist with overlapping low bits: `0x000Fxxxx` reached by
`abs20` operands and `0x00FFxxxx` reached through register pairs.  Nothing in
the code proves that e.g. `0x000F6400` and `0x00FF6400` are the same
hardware; therefore both are listed separately.

## 2. What each block is *not* proven to be

| Block | Common guess | Evidence for the guess | Evidence against |
|---|---|---|---|
| `0x00FF60xx` | PCM/DMA | adjacent to `0xFF54xx`, pulsed exactly once per sequence | no frame-timed access, no FIFO loop |
| `0x00FF54xx` | interrupt controller | written under `di` (`0x2592`–`0x25A6`) | no mask/ack pattern proven |
| `0x00FF48xx` | GPIO | 11 registers written in blocks, set/clear pairs | driven by the DECT part of the image, not by the FON path |
| `0x01000000` | PCM buffer / DMA descriptors | 511 sequential writes, outside any code run | no reader found |

## 3. Smallest confirmed facts worth carrying forward

1. `0x000F6006` has two writers in the image and both write `0x0080`; the
   third writer is the one in `0x25F90`.  There is no other value.
2. `0x000F6002` has one access in the whole image: a read at `0x25FAE`.
3. `0x000F6400` and `0x000F6402` have one writer each and no reader.
4. `0x000F5402` has seven writers and no reader.
5. `0x01000000` is written by a generic helper and never read through an
   address the scanner can resolve.
6. The whole sequence uses 16-bit accesses; only the addresses are 32-bit.
