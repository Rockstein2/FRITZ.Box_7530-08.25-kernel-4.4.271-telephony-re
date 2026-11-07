# Low memory `0x1C`–`0xD4`: what the bytes are and are not

Status: **offline analysis.**  L1 bytes, L2 decode.  Nothing here is a
claim about what the CPU executes.

---

## 1. The bytes

Block 1 of both second-level images covers `0x000000–0x0000D4`.  The region
this document is about, `0x1C`–`0xD4`, is inside it in **both** images.

```text
0x1C: f2 08 00 00  6c 93 00 00
0x24: e5 46 01 00  e5 46 01 00  e5 46 01 00  e5 46 01 00
0x34: e5 46 01 00  e5 46 01 00  e5 46 01 00  e5 46 01 00
...
```

## 2. What is proven

| Claim | Status | Basis |
|---|---|---|
| `0x1C` holds the pair `(0x000008F2, 0x0000936C)` read as little-endian `u32` | **L2** | `0x8F2` is an instruction boundary (`movd $0x10ccc:l,(r12)`); `0xF2080000` is not |
| the start-up code clears `0x8F2` bytes at `0x936C` | **L2** | see `fon-dialog-copy-helper-28d56.md` |
| `0x24` onwards is a table of repeating 4-byte values `0x000146E5` | **L1** | bytes |
| that table has a few different entries (`0x000144CB`, `0x00014668`) | **L1** | bytes at `0x74`, `0x7C` |
| the values are **odd** | **L1** | `0x146E5 & 1 = 1`, `0x144CB & 1 = 1`; `0x14668` is even |
| no byte of the image covers `0x146E5`, `0x144CB` or `0x14668` | **L1** | block list ends at `0x28DCD` but has gaps; none covers those addresses |

## 3. What is **not** proven, and why

| Claim that was made in BOOT-1 | Why it does not stand |
|---|---|
| "the table holds pointers to code that must be loaded later" | **wrong**: under the ×2 encoding the entries point inside the image (see §4) |
| "the table is a vector table" | nothing in the image writes or reads it as a table of entry points; `INTBASE = 0x24` says where the core *looks*, not that the bytes there are valid vectors for this image |
| "the copy at `0x15F6` installs the table" | it clears a buffer at `0x936C`; it does not move anything into `0x24` |

**Status of `0x24` onward: a table of 32-bit values of unknown purpose.**

## 4. The encoding of the table entries: **×2 (word offsets)**

The unique 32-bit little-endian values in `0x24`–`0xD4` are:

```text
0x000144CB  0x0001454A  0x00014668  0x000146E5     (the four address-like ones)
0x00000000  0x00000001  0x01042A01  0x02FFFFFF  0x03030B02
0x0A000107  0x50010608  0x7F800000  0xFFFF0501     (nine others, not address-like)
```

Doubling each of the four address-like values:

| Value | ×2 | Instruction at ×2 | Kind |
|---|---|---|---|
| `0x000144CB` | `0x028996` | `push $0x3,r0` | **function prologue** |
| `0x0001454A` | `0x028A94` | `push $0x8,r0,RA` | **function prologue** |
| `0x00014668` | `0x028CD0` | `push $0x7,r0,RA` | **function prologue** |
| `0x000146E5` | `0x028DCA` | `nop` | stub (the `0x28DCC retx` handler) |

**Probability check.**  In the block `0x20000`–`0x28DCD` only 87 of 13 528
instruction boundaries (0.6 %) are `push …,RA` prologues, and 161 of 19 570
(0.8 %) image-wide.  Four independent values all landing on a prologue has a
probability of about 3 × 10⁻⁹ if the mapping were arbitrary.

**Conclusion (L2, strong):** the table entries are **byte addresses divided
by two**, i.e. they encode a 24-bit address in a 23-bit field with the low
bit implicit.  This is also why three of the four are odd: the odd low bit is
the lost bit-0 of the address, not a tag.

The nine non-address-like values in the same region are a different thing;
they are not covered by this encoding and remain **UNKNOWN** (possibly a
different table interleaved, or data).

### What the entries point at

`0x28996`, `0x28A94`, `0x28CD0`, `0x28DCA` are all in the last part of the
image, next to the routines that touch `0x000F5402` and end in `retx`
(`0x289AE`, `0x28B0A`, `0x28CF2`, `0x28DCC`).  So the table does reference
exception-handler-like code **inside the uploaded image** — contrary to the
BOOT-1 statement that it must point outside.

## 5. Relationship to `INTBASE = 0x24`

`INTBASE` names `0x24`.  The core reads the dispatch table there.  Because:

* the entries decode (×2) to prologues and one `retx` stub inside the
  image, which is exactly what a dispatch table should contain,
* the start-up runs `di` before setting `INTBASE` (`0x15D0`, `0x15DE`),

the table is consistent with an exception dispatch table for this image.
Whether the core uses it in this build is **UNKNOWN**, and the ×2 encoding
is not documented in any offline source — it is established from the
firmware, not from a manual.

## 6. Could the region change before it is used?

| Candidate | Evidence |
|---|---|
| the loader writes it | the loader writes only at addresses carried in block headers; it could write anywhere in principle, but no captured transfer shows it |
| the start-up code writes it | no store to `0x1C`–`0xD4` exists in either image (scanned with `cr16_peripheral_xrefs.py`) |
| it is already correct in the file | consistent with the bytes being data |

No write to this region was found in either image, so **the bytes in the file
are what the code would see**, unless something outside the image (the
loader, a ROM stage, or the hardware) changes memory first.

## 6a. The `.bss` link

The record at `0x1C` clears `[0x936C, 0x9C5E)`, and `0x9C5E` is exactly the
start of the next uploaded block.  In `p2test` the record `{0x69F, 0x94A4}`
clears `[0x94A4, 0x9B44)`, again landing on the next block start.  See
`fon-dialog-copy-helper-28d56.md`; status **STRONG_INFERENCE**.

## 7. `0x7C`

`0x7C` lies inside block 1 (`0x0`–`0xD4`) and holds
`68 46 01 00` — a **different** 32-bit value from the repeating
`0x000146E5`, i.e. one of the two exceptions in the table.

The earlier statement that "no second-level block covers `0x7C`" was
**wrong** and is corrected.  `0x7C` is loaded data.  Whether the CPU
executes it is a separate, unproven question.
