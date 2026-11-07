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
| `0x7C` holds loaded bytes | **yes** — block 1 covers `0x0`–`0xD4` in both images, and `0x7C` lies inside it (the earlier "no block covers `0x7C`" was wrong) |
| the CPU executes `0x7C` | **UNKNOWN** — bytes present is not bytes executed |
| the loader and the loaded code coexist in memory | **hypothesis**: the loader occupies `0x10080`, which lies inside the second-level *envelope* `0x0`–`0x28DCD`, but no second-level block covers `0x10080`.  The block `0x20000` `0x8dce` ends at `0x28DCe`, above it, and `0x9c5e` `0x3a2` ends at `0xA000`, below it |

**The last row is the important one.**  Since no second-level block spans
`0x10080`, the loader's own code is not overwritten by the second-level
image.  That is consistent with the loader staying resident, which in turn
is consistent with the loader jumping into the loaded code at an address
the loader knows.

## 3. The region around `0x0`–`0x100`

The second-level image starts at `0x0` with a block of `0xD5` bytes, so
`0x7C` and `0x24` are both **loaded data**.  The table at `0x24` is analysed
in `fon-dialog-low-memory-analysis.md`: its entries double to
**instruction boundaries inside the image** (`0x28996`, `0x28A94`,
`0x28CD0`, `0x28DCA`), which makes them word-offset addresses, not pointers
to missing code.

Also in that block, at `0x1C`, is the single record that the start-up code
uses to clear a buffer (`{count=0x8F2, dest=0x936C}`).

## 3a. Load address versus execution entry

`0x10080` is the address of the first Intel HEX block of the first-level
image.  That is an **image placement** fact (L1).  It does **not** establish
that the CPU starts executing there: no ROM image and no decoded branch into
it exists in the material available.  Execution entry: **UNKNOWN**.

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

## 4a. The zero-filled gap and the `.bss` reading

Between the block at `0x9000` and the block at `0x9C5E` there is a gap that
the image does not carry.  The start-up record clear fills exactly that gap:

| Image | cleared range | next block |
|---|---|---|
| normal | `[0x936C, 0x9C5E)` | `0x9C5E` |
| p2test | `[0x94A4, 0x9B44)` | `0x9B44` |

The bytes at `0x936B` (one before the cleared range) are **not** in any
block, so the region `0x936B`–`0x9C5D` is image-absent memory that the code
zeroes at start-up.  Status: **STRONG_INFERENCE** for `.bss`, not proof.

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
