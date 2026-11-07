# SC14448 boot memory map

Status: **offline reconstruction.**  L1 for every byte and block address,
L2 for the instructions that compute an address.  No hardware property is
assigned to any address number.

Report: `tools/reports/cr16-boot-memory-map.json` from
`tools/cr16_boot_memory_map.py`.

---

## 1. What each image declares

| Image | Blocks | Address range | Bytes |
|---|---|---|---|
| first-level `dectfw_firstlevel_441_slow.hex` | **1** | `0x10080`–`0x102E9` | 618 |
| second-level `dectfw_secondlevel_441.hex` | **9** | `0x0`–`0x28DCD` | 54 047 |
| second-level `dectfw_secondlevel_441p2test.hex` | **8** | `0x0`–`0x27D49` | 49 736 |

`normal` second-level blocks:

```text
0x00000000  0x0d5
0x000000d6  0x1dd
0x000002b4  0x17fa   <- the second-level start-up block is inside this one
0x000024f8  0x1806
0x00009000  0x36b
0x00009c5e  0x3a2
0x00017300  0xb7a
0x00017fe0  0x018
0x00020000  0x8dce
```

## 2. Where the bytes actually go

The loader writes each byte at the address in its block header
(`0x1022C`, see `fon-dialog-uart-boot-protocol.md`).  Therefore:

| Claim | Status |
|---|---|
| the second-level image is placed at the addresses its Intel HEX records declare | **proven at L2** (header-driven `storb`, `0x1019A`–`0x10234`) |
| the second-level image is relocated to another base by the loader | **no evidence**; the loader has no base adjustment |
| the second-level image is placed at `0x7C` | **not supported**: no block starts there |
| the loader and the loaded code coexist in memory | **hypothesis**: the loader occupies `0x10080`, which lies inside the second-level *envelope* `0x0`–`0x28DCD`, but no second-level block covers `0x10080`.  The block `0x20000` `0x8dce` ends at `0x28DCe`, above it, and `0x9c5e` `0x3a2` ends at `0xA000`, below it |

**The last row is the important one.**  Since no second-level block spans
`0x10080`, the loader's own code is not overwritten by the second-level
image.  That is consistent with the loader staying resident, which in turn
is consistent with the loader jumping into the loaded code at an address
the loader knows.

## 3. The region around `0x0`–`0x100`

The second-level image starts at `0x0` with a block of `0xD5` bytes.  At
`0x24` and around `0x7C` the same 4-byte pattern repeats:

```text
0x24: e5 46 01 00 e5 46 01 00 ...
0x70: e5 46 01 00 e5 46 01 00 cb 44 01 00 e5 46 01 00 68 46 01 00
```

read as little-endian 32-bit values that is `0x000146E5`, `0x000144CB`,
`0x00014668`.  **None of those addresses exists in the image**: the block
list has no entry covering `0x146E5`.  So this region is a table of
pointers into code that is *not* part of the uploaded image — it must come
from somewhere else (a further upload, or a different image).

The same table is what `INTBASE = 0x24` points at (see
`fon-dialog-cr16-system-registers.md`).

## 4. What the loader itself writes

The first-level image writes only these addresses:

| Address | Operation | Site |
|---|---|---|
| `0x000F4020` | `storb $0x30` | `0x1009C` |
| `0x000F400E` | RMW | `0x100A0`–`0x100AA` |
| `0x000F4000` | RMW, `sbitw $7` | `0x100AE`–`0x100C6`, `0x100FC` |
| `0x000F4838` | `sbitw`/`cbitw` | `0x100CA`, `0x10270` |
| `0x000F4836` | RMW | `0x100CE`–`0x100E2`, `0x10254`–`0x1026C` |
| `0x000F4900` | RMW, `sbitw` | `0x100E6`–`0x100F8`, `0x10274` |
| `0x000F4902` | `storw` (UART data) | `0x102CE` |
| `0x000F4904` | `storw $1` (TX strobe) | `0x102E4` |
| `0x000F4906` | `storw $1` (RX strobe) | `0x102BA` |
| `0x000F4C00` | `storw $0xFF` | `0x102A0`, `0x102CA` |
| *the received blocks* | `storb` at the header address | `0x1022C` |

No write below `0x10000` comes from a **static** address; the only writes
there are the header-driven transfers.

## 5. Region `0x01000000`

The area the `0x25F90` sequence fills (`0x01000002`–`0x010003FE`) appears in
**neither** the first-level image nor the second-level image.  It is
therefore runtime memory: nothing in the upload places bytes there.  Its
nature (RAM, FIFO, peripheral window) is **UNKNOWN**.

## 6. Overlaps

* no overlap *within* any single image;
* the first-level and second-level images share **no byte**;
* the first-level address `0x10080` falls inside the second-level
  *envelope* but inside none of its blocks.
