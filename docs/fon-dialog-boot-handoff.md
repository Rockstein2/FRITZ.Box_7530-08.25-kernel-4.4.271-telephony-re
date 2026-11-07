# SC14448 boot hand-off

Status: **offline reconstruction.**

**Answer: STATICALLY_RESOLVED / RUNTIME_UNVERIFIED.**  Every link of the
transfer is decoded from the image bytes.  Nothing here has been observed on
hardware.

---

## 1. The chain

```text
SC14448 reset / ROM            UNKNOWN (no ROM image, no reset vector found)
        |
        v
first-level 0x10080            PROVEN: one block, 618 bytes (L1)
        |
        v
CFG/PSR setup, I/O setup       PROVEN (L2), 0x10080-0x100FC
        |
        v
byte protocol (0x1029C/0x102C6) PROVEN as code (L2)
        |
        v
blocks written at header addr   PROVEN (L2) 0x1022C
        |
        v
0x10284  br 0x000008           DECODED (disps25, L2)
        |
        v
second-level 0x000008:
  normal  br 0x15AA            DECODED (disps25, L2)
  p2test  br 0x1026            DECODED (disps25, L2)
        |
        v
second-level start-up           PROVEN location: 0x15AA block, 0x15BC setup
        |
        v
0x1602 -> 0x39F8 -> ... 0x25F90 PROVEN by call chain (L3)
```

## 2. What is proven, link by link

| Link | Statement | Evidence |
|---|---|---|
| reset → first-level | no evidence in this repository | **UNKNOWN** |
| first-level image content | one block at `0x10080`, 618 bytes | L1 |
| loader writes the received blocks | `storb r2,0x0:s(r12)` at `0x1022C`, pointer in `(r12)` from a `u32be` header | L2 |
| second-level lands at its declared addresses | the header carries the address; no base adjustment exists in the loader | L2 |
| second-level does not overwrite the loader | no second-level block covers `0x10080` | L1 |
| the three `disps17` branches | decode to `0x010100`, the retry loop | L2 |
| hand-off branch (`0x10284`) | `disps25` decodes to **`0x000008`** | L2 |
| second-level at `0x8` | `disps25` to `0x15AA` (normal) / `0x1026` (p2test); both are instruction boundaries | L2 |
| whole transfer chain | every link decoded, no gaps | **L3 static** |
| second-level start-up block | `0x15AA` (normal) / `0x102C` (p2test); sets USP, ISP, CFG, INTBASE | L2/L3 |
| first-level *load* address | `0x10080`, L1 (the Intel HEX record) | L1 |
| first-level *execution* entry | **UNKNOWN** — no ROM image and no decoded branch enters it | — |
| that block has no caller in the image | searched every direct branch and call | L2 |
| `0x1602` is on the start-up path | `0x15FA`–`0x1602` write PSR then `bal 0x39F8` | L3 |

## 3. The `0x7C` question

`0x7C` lies inside block 1 (`0x0`–`0xD4`) in both images and holds
`e5 46 01 00`, i.e. the repeating stub value `0x000146E5` — vector 22 of the
dispatch table.  It is **not** the hand-off target: the loader's branch goes
to `0x8`.

An earlier iteration claimed that "no second-level block covers `0x7C`";
that was wrong and is recorded here only as history.

## 4. How the second-level reaches its start-up block

**Resolved.**  The loader's `disps25` branch at `0x10284` goes to `0x8`, and
`0x8` in both images is itself a `disps25` branch:

| Image | bytes at `0x8` | target | target is an instruction boundary |
|---|---|---|---|
| normal | `10 00 e0 00 a2 15` | **`0x15AA`** (the start-up block) | yes |
| p2test | `10 00 e0 00 1e 10` | **`0x1026`** (six bytes before `0x102C`) | yes |

Note that `0x8` is **not** an instruction boundary in the linear disassembly
of the second-level image: linear decoding starts at `0x0` and reads
`loadm $1,r0`, `illegal`, then a 6-byte `subd` that would span `0x4`–`0x9`.
The bytes at `0x8` are therefore decoded in isolation, and they are a valid
`disps25` branch.  This means the first ten bytes of the image are not code
reached by fall-through; they are the entry block the loader jumps into.

Runtime status: **UNVERIFIED**.  No capture or trace shows the board taking
this path.

## 5. The `0x28D56` copy

| Question | Answer | Evidence |
|---|---|---|
| direction | writes through the destination pair `(r3,r2)` | `0x28D90 storb r0,0x0:s(r8,r7)` after `0x28D58 movd (r3,r2),(r8,r7)` |
| unit | one 8-byte record `{u32le count, u32le destination}`; the loop advances by 8 | `0x28D6A addd $8,(r8,r7)` |
| destination | `(r3,r2) = 0x1C` loaded at `0x15EA` — this is the **record start**, not the copy address | L2 |
| source | `(r5,r4) = 0x24` loaded at `0x15F0` | L2 |
| what is actually written | **`0x8F2` zero bytes at `0x936C`** — one record `{count=0x8F2, dest=0x936C}` at `0x1C` | L2, `fon-dialog-copy-helper-28d56.md` |
| does it change `0x24` | **no** — the single record at `0x1C` names `0x936C` as the destination; nothing is written at `0x24` |

The call is `fn_28d56(0x1C, 0x24)`: cursor `0x1C`, end `0x24`, i.e. exactly
one 8-byte record, which asks for `0x8F2` zero bytes at `0x936C`.  It is a
buffer clear, not a copy and not a vector-table installation.
