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
| hand-off branch | the `0x18` form at `0x1017C`/`0x10298` is not decoded | **UNKNOWN** |
| second-level start-up block | `0x15AA` (normal) / `0x102C` (p2test); sets USP, ISP, CFG, INTBASE | L2/L3 |
| that block has no caller in the image | searched every direct branch and call | L2 |
| `0x1602` is on the start-up path | `0x15FA`–`0x1602` write PSR then `bal 0x39F8` | L3 |

## 3. The `0x7C` question

Earlier iterations suggested the hand-off goes to `0x7C`.  With the correct
reading of the loader this is **not supported**:

* the loader starts at `0x10080` and contains no code at `0x7C`;
* no second-level block starts or covers `0x7C`;
* the `0x18` branch form at `0x1017C` does not decode to `0x7C` under any
  rule consistent with the three known-good second-level targets.

What *is* true about `0x7C`: it lies inside the second-level block that
starts at `0x0`, and it holds a pointer pattern (`0x000146E5`) that points
outside the image.  Whether the loader jumps there remains **UNKNOWN**.

## 4. How the second-level reaches its start-up block

Two possibilities, neither proven:

| Possibility | What would make it true |
|---|---|
| the loader jumps directly to `0x15AA`-equivalents | the hand-off branch target would be `0x15AA`; not established |
| the loader jumps to a fixed entry (e.g. `0x0`) and the image's first instructions jump on | bytes at `0x0` are `a0 00 00 00 35 00 00 00 …`, which decode as `loadm $1,r0` — not a plausible entry sequence |

Neither explanation is supported by the bytes.  The hand-off is **PARTIALLY
KNOWN**: the destination *data* is known, the *control transfer* is not.

## 5. The `0x28D56` copy

| Question | Answer | Evidence |
|---|---|---|
| direction | writes through the destination pair `(r3,r2)` | `0x28D90 storb r0,0x0:s(r8,r7)` after `0x28D58 movd (r3,r2),(r8,r7)` |
| unit | **count of 8-byte `{u32be addr,u32be len}` entries**, not bytes | `0x28D6A addd $8,(r8,r7)` |
| destination | `(r3,r2) = 0x1C` loaded at `0x15EA` | L2 |
| source | `(r5,r4) = 0x24` loaded at `0x15F0` | L2 |
| overlap of source and destination | **UNKNOWN** — `0x1C` and `0x24` are 8 bytes apart, so the list read and the bytes written overlap only if the destination bytes extend upward from `0x1C` into `0x24` | not resolved: the destination is a *pointer* to where the copy goes, not the copy address itself |
| does it change `0x24` | **UNKNOWN** | depends on the destination pointer, which is `(r3,r2) = 0x1C` — i.e. the copy writes at `0x1C` and above |

The function reads a **list** at `0x24` and writes the pointed-to data at
`0x1C`.  It is not a simple byte copy, and it is not a vector-table
installation: the list at `0x24` is walked as `{addr,len}` pairs.
