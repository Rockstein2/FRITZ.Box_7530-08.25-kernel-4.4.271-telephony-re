# `0x28D56`: instruction-level semantics

> **Status: historical analysis.**
> This document records the reasoning and evidence as of the date it was
> written.  Some of its `UNKNOWN` / `UNVERIFIED` markers have since been
> answered.
> - Current confirmed facts: `../fon-known-facts.md`
> - Current open questions: `../fon-open-questions.md`
> - This file is kept for the reasoning trail, not as a status report.

Status: **offline analysis.**  L1 bytes, L2 decode, L4 semantics under the
stated assumptions.  The previous BOOT-1 text called this function "a
`{u32be addr, u32be len}` list walker"; that description is **withdrawn**.
This document re-derives the semantics from the instructions and shows what
is proven and what is not.

---

## 0. Conventions proven before the function is read

### Register-pair half order

`(rH,rL)` names a 32-bit pair where **`rH` is the high half and `rL` the low
half**.  Proof from the firmware itself, not from a manual:

```text
0x25BC  movd $0x937c:l,(r1,r0)
0x25C2  loadw 0x0:s(r1,r0),r3      ; a 32-bit address, displacement 0
```

`movd $imm:l` loads the whole 32-bit value into the pair and the following
`loadw` uses it as an address.  If `r0` held the high half, the address
would be `0x7C930000`; the code uses `0x0000937C`.  So `r1 = high`,
`r0 = low`, i.e. the pair is **big-endian**.

`movd $0x12345678:l,(r6,r5)` therefore sets `r6 = 0x1234`, `r5 = 0x5678`.

### Width of `loadd`

`loadd 0x0:s(r8,r7),(r6,r5)` loads 32 bits with the same half order: the
word at `(r8,r7)` becomes the pair value, `r6` high, `r5` low.

## 1. The function, instruction by instruction

| # | Address | Bytes | Instruction | Effect | Evidence |
|---|---|---|---|---|---|
| 1 | `0x28D56` | `b7 01` | `push $4,r7,RA` | save `r7`, RA, sp−4 | L1 |
| 2 | `0x28D58` | `27 55` | `movd (r3,r2),(r8,r7)` | `(r8,r7) = (r3,r2)` | L1 |
| 3 | `0x28D5A` | `49 55` | `movd (r5,r4),(r10,r9)` | `(r10,r9) = (r5,r4)` | L1 |
| 4 | `0x28D5C` | `97 57` | `cmpd (r10,r9),(r8,r7)` | loop while `(r8,r7) != (r10,r9)` | L1 |
| 5 | `0x28D5E` | `08 10` | `beq +0x28D6E` | exit loop | L1/L3 |
| 6 | `0x28D60` | `57 A0` | `loadd 0x0:s(r8,r7),(r6,r5)` | `hi = mem32[(r8,r7)+0]` | L1 |
| 7 | `0x28D62` | `04 5A` | `movw $0,r4` | **`r4` is forced to 0** | L1 |
| 8 | `0x28D64` | `27 A2` | `loadd 0x4:s(r8,r7),(r3,r2)` | `lo = mem32[(r8,r7)+4]` | L1 |
| 9 | `0x28D66` | `00 C0 22 00` | `bal 0x28D88` | call the fill helper | L1/L3 |
| 10 | `0x28D6A` | `87 60` | `addd $8,(r8,r7)` | next 8-byte record | L1 |
| 11 | `0x28D6C` | `E8 1F` | `br -0x28D5C` | loop | L1/L3 |
| 12 | `0x28D6E` | `B7 03` | `popret $4,r7,RA` | return | L1 |

### The fill helper `0x28D88`

| # | Address | Bytes | Instruction | Effect |
|---|---|---|---|---|
| 1 | `0x28D88` | `17 01` | `push $2,r7` | |
| 2 | `0x28D8A` | `27 55` | `movd (r3,r2),(r8,r7)` | `(r8,r7) = (r3,r2)` |
| 3 | `0x28D8C` | `05 56` | `cmpd $0,(r6,r5)` | loop while `(r6,r5) != 0` |
| 4 | `0x28D8E` | `06 10` | `beq +0x28D9A` | |
| 5 | `0x28D90` | `40 59` | `movb r4,r0` | **`r0 = r4` (always 0, see step 7 above)** |
| 6 | `0x28D92` | `07 F0` | `storb r0,0x0:s(r8,r7)` | **store a zero byte** |
| 7 | `0x28D94` | `17 60` | `addd $1,(r8,r7)` | advance |
| 8 | `0x28D96` | `95 60` | `addd $-1,(r6,r5)` | count down |
| 9 | `0x28D98` | `EA 1F` | `br -0x28D8C` | |
| 10 | `0x28D9A` | `20 55` | `movd (r3,r2),(r1,r0)` | return value = destination |
| 11 | `0x28D9C` | `17 03` | `popret $2,r7` | |

**The helper writes zeros.**  `r4` is set to `0` at `0x28D62`, `.` and
nothing between that and `0x28D90` can change it: the only instructions are
`loadd` into `(r3,r2)` (which overwrites `r3` and `r2`) and the call
itself.  So `movb r4,r0` always produces `0`.

## 2. Pseudocode (types explicit)

```c
/* all values are 32-bit, byte-addressed, big-endian pairs */
void fn_28d56(uint32 dst /* (r3,r2) */, uint32 src /* (r5,r4) */)
{
    uint32 rec = dst;             /* (r8,r7) */
    uint32 end = src;             /* (r10,r9) */
    while (rec != end) {          /* 0x28d5c */
        uint32 count = read32(rec + 0);   /* (r6,r5) */
        uint32 base  = read32(rec + 4);   /* (r3,r2) */
        fill_zeros(count, base);          /* 0x28d88 */
        rec += 8;                         /* 0x28d6a */
    }
}

void fill_zeros(uint32 count, uint8 *dst)
{
    while (count != 0) {          /* 0x28d8c */
        *dst++ = 0;               /* 0x28d90: r0 = r4 = 0 */
        count--;
    }
}
```

## 3. What the arguments mean

| Register | Meaning | Proof |
|---|---|---|
| `(r3,r2)` at entry | **first record address** (loop cursor start) | `0x28D58 movd (r3,r2),(r8,r7)` |
| `(r5,r4)` at entry | **loop end address** | `0x28D5A movd (r5,r4),(r10,r9)` and `0x28D5C cmpd` |
| `(r8,r7)` | record cursor | `0x28D6A addd $8` |
| `(r6,r5)` inside the loop | **byte count** for this record | `0x28D8C cmpd $0,(r6,r5)`, `0x28D96 addd $-1` |
| `(r3,r2)` inside the loop | **destination pointer** for this record | `0x28D8A movd (r3,r2),(r8,r7)` → `storb` through it |

**Both `(r3,r2)` roles are different.**  At entry it is the record start; at
`0x28D64` it is overwritten with the record's second field, which becomes the
fill destination.  That dual use is why the earlier "list walker" reading
went wrong.

## 4. The call at `0x15EA`

```text
0x15E0  movd $0x24:l,(r2,r1)     ; r2 high, r1 low -> (r2,r1) = 0x24
0x15EA  movd $0x1c:l,(r3,r2)     ; (r3,r2) = 0x1c
0x15F0  movd $0x24:l,(r5,r4)     ; (r5,r4) = 0x24
0x15F6  bal  0x28d56
```

So the call is `fn_28d56(0x1C, 0x24)`: the record cursor starts at `0x1C`,
the end is `0x24`.  **That is exactly one 8-byte record**, at `0x1C`:

```text
0x1C: f2 08 00 00   -> little-endian 0x000008F2   (count)
0x20: 6c 93 00 00   -> little-endian 0x0000936C   (destination)
```

**The record fields are little-endian**, because the value `0x000008F2`
read that way is an instruction boundary in the image
(`0x8F2 movd $0x10ccc:l,(r12)`) while the big-endian reading
`0xF2080000` is not.  This is the one endianness fact the code supports; it
does **not** follow from the register-pair order.

So the effect of the whole sequence is:

> **clear `0x8F2` bytes at `0x936C`**

and nothing else.  It is a `.bss`/buffer clear, not a vector-table
installation.

### Is `0x936C` inside the image?

No.  The block at `0x9000` has length `0x36B` and therefore ends at
`0x936A`; `0x936C` is the first byte **past the end of that block**, and no
other block covers it.  The
cleared region is outside the uploaded bytes.

### What the cleared region is: `.bss` (STRONG_INFERENCE)

`count = 0x8F2 = 2290` bytes starting at `0x936C`, so the cleared range is

```text
[0x936C, 0x936C + 0x8F2) = [0x936C, 0x9C5E)
```

and `0x9C5E` is **exactly** the start of the next uploaded block
(`0x9C5E`, length `0x3A2`).  In `p2test` the boundary misses by one byte:

| Image | record | range | next block |
|---|---|---|---|
| normal | `{0x8F2, 0x936C}` | `[0x936C, 0x9C5E)` | `0x9C5E` ✔ |
| p2test | `{0x69F, 0x94A4}` | `[0x94A4, 0x9B43)` | `0x9B44` (one byte gap) |

Every block in both images starts at an **even** address, so the one-byte
difference in `p2test` is consistent with clearing up to an aligned end
(`0x9B43` is odd, `0x9B44` is the next even boundary) rather than with an
exact match.  The normal image happens to land on an even address already.

This is the classic start-up `.bss` clear.  The reference project does the
same thing in `device/startup.c` (`for (dest = &_bss; dest < &_ebss;
dest++) *dest = 0;`), and its linker script places `.bss (NOLOAD)` after
`.data`.

**Status: STRONG_INFERENCE.**  In `normal` the cleared end equals the next
block start exactly; in `p2test` it stops one byte short, at the last even
boundary before it.  Both are consistent with a `.bss` clear, the second
with alignment, but the wording "exact match in both images" is **withdrawn**.
No SC14448 document says the region is RAM named `.bss`.

Note also what this rules out: the cleared region is **not** the region at
`0x1C`–`0xD4`, so the function does not modify the dispatch table.

## 5. Corrections to the BOOT-1 claims

| BOOT-1 said | Correct |
|---|---|
| "walks a list of `{u32be addr, u32be len}`" | the cursor is `(r3,r2)` and the end is `(r5,r4)`; the loop compares equal pointers and stops, so a *single* call with `(0x1C, 0x24)` processes **one** record |
| "writes the pointed-to data" | it writes **zeros**; the record's first field is a **count**, not a length of data to copy |
| "vector table installation" | not supported by any instruction |
| "record fields are big-endian" | they are **little-endian** (`0x8F2` is code, `0xF2080000` is not) |

## 6. Remaining unknowns

| Question | Status |
|---|---|
| why only one record is cleared | the caller sets end = start + 8; larger tables would need `(r5,r4) > 0x24` |
| what the region at `0x936C` is | UNKNOWN |
| whether `0x28D56` is called elsewhere | one caller only (`0x15F6`) |
| the meaning of the table at `0x24` | UNKNOWN — see `fon-dialog-low-memory-analysis.md` |
