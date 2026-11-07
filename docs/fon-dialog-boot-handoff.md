# SC14448 boot hand-off

Status: **offline reconstruction.**  **Answer: PARTIALLY KNOWN.**

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
branch into loaded code         UNKNOWN (Q51) 0x1017C, 0x10284, 0x10298
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
| hand-off branch (`0x10284`) | `disps25` decodes to **`0x000008`**; `0x8` branches to `0x15AA` (normal) / `0x1026` (p2test) | **L3, decoded chain** |
| second-level start-up block | `0x15AA` (normal) / `0x102C` (p2test); sets USP, ISP, CFG, INTBASE | L2/L3 |
| first-level *load* address | `0x10080`, L1 (the Intel HEX record) | L1 |
| first-level *execution* entry | **UNKNOWN** — no ROM image and no decoded branch enters it | — |
| that block has no caller in the image | searched every direct branch and call | L2 |
| `0x1602` is on the start-up path | `0x15FA`–`0x1602` write PSR then `bal 0x39F8` | L3 |

## 3. The `0x7C` question

Earlier iterations suggested the hand-off goes to `0x7C`.  With the correct
reading of the loader this is **not supported**:

* the loader starts at `0x10080` and contains no code at `0x7C`;
* the `0x18` branch form at `0x1017C` computes `0x010101` under the binutils
  rule, not `0x7C` (see `fon-dialog-boot-branch-decoding.md`).

**Correction.**  Earlier text claimed that "no second-level block covers
`0x7C`".  That was wrong: block 1 is `0x0`–`0xD4` in both images, so `0x7C`
**is** inside loaded data.  It holds `68 46 01 00`, one of the two
non-repeating entries of the table at `0x24`.  Whether the CPU executes it
is a separate, unproven question.

## 4. How the second-level reaches its start-up block

Two possibilities, neither proven:

| Possibility | What would make it true |
|---|---|
| the loader jumps directly to `0x15AA`-equivalents | the hand-off branch target would be `0x15AA`; not established |
| the loader jumps to a fixed entry (e.g. `0x0`) and the image's first instructions jump on | bytes at `0x0` decode as `loadm $1,r0` then `illegal` — not a plausible entry sequence |

Neither explanation is supported by the bytes.  The hand-off is **PARTIALLY
KNOWN**: the destination *data* is known, the *control transfer* is not.

## 5. The `0x28D56` copy

| Question | Answer | Evidence |
|---|---|---|
| direction | writes through the destination pair `(r3,r2)` | `0x28D90 storb r0,0x0:s(r8,r7)` after `0x28D58 movd (r3,r2),(r8,r7)` |
| unit | **count of 8-byte `{u32be addr,u32be len}` entries**, not bytes | `0x28D6A addd $8,(r8,r7)` |
| destination | `(r3,r2) = 0x1C` loaded at `0x15EA` — this is the **record start**, not the copy address | L2 |
| source | `(r5,r4) = 0x24` loaded at `0x15F0` | L2 |
| what is actually written | **`0x8F2` zero bytes at `0x936C`** — one record `{count=0x8F2, dest=0x936C}` at `0x1C` | L2, `fon-dialog-copy-helper-28d56.md` |
| does it change `0x24` | **no** — the single record at `0x1C` names `0x936C` as the destination; nothing is written at `0x24` |

The call is `fn_28d56(0x1C, 0x24)`: cursor `0x1C`, end `0x24`, i.e. exactly
one 8-byte record, which asks for `0x8F2` zero bytes at `0x936C`.  It is a
buffer clear, not a copy and not a vector-table installation.
