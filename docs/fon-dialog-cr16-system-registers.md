# CR16 system registers and vectors in the SC14448 firmware

Status: **offline analysis.**  L1 bytes, L2 decode, L3 control flow,
L4 semantics under the stated ISA assumptions.  **No L5 hardware evidence.**

Two images are analysed separately; every row states which one it comes
from.

---

## 1. Processor-register accesses actually present

All accesses to `lpr`/`lprd`/`spr`/`sprd` in both images, grouped:

| Image | Form | Sites | Reachable from `0x1602` |
|---|---|---|---|
| normal | `lprd (sp),usp` | `0x15C2` | **no** |
| normal | `lprd (r1,r0),isp` | `0x15CC` | **no** |
| normal | `spr cfg,r0` | `0x15D2` | **no** |
| normal | `lpr r0,cfg` | `0x15DA` | **no** |
| normal | `lprd (r2,r1),intbase` | `0x15E6` | **no** |
| normal | `lpr r1,psr` | `0x15FE` | **yes** |
| normal | `lpr/lprd …psr` | `0x19EC`, `0x1A2E`, `0x39FC`, `0x258E`, `0x25A6`, `0x286…` | mixed |
| normal | `sprd psr,(r1,r0)` | 6 sites | mixed |
| normal | `lpr r9,dbs` (6), `lpr r4,dbs`, `lpr r5,intbasel` | `0x90DC`–`0x9284` | **no — data block** |
| p2test | `lprd (sp),usp` | `0x1044` | **no** |
| p2test | `lprd (r1,r0),isp` | `0x104E` | **no** |
| p2test | `spr cfg,r0` | `0x1054` | **no** |
| p2test | `lpr r0,cfg` | `0x105C` | **no** |
| p2test | `lprd (r2,r1),intbase` | `0x1068` | **no** |

The `dbs` and `intbasel` accesses in the `0x90xx` block (`normal`) sit in a
region whose surrounding instructions do not decode as code (`lshb $-5`,
`loadm $0x5,(r1,r0)`, `illegal`).  They are **data misread as code** and
must not be treated as system-register uses.

## 2. The start-up sequence

Both images contain the same block, at different addresses:

| Operation | normal | p2test | Value |
|---|---|---|---|
| `movd $0x3f00:l,(sp)` | `0x15BC` | `0x103A` | stack |
| `lprd (sp),usp` | `0x15C2` | `0x1044` | `USP = 0x3F00` |
| `movd $0x3ff0:l,(r1,r0)` | `0x15C6` | `0x1048` | |
| `lprd (r1,r0),isp` | `0x15CC` | `0x104E` | `ISP = 0x3FF0` |
| `di` | `0x15D0` | `0x1052` | interrupts off |
| `spr cfg,r0` | `0x15D2` | `0x1054` | read `CFG` into `r0` |
| `orw $0x100:m,r0` | `0x15D6` | `0x1058` | set **bit 8** |
| `lpr r0,cfg` | `0x15DA` | `0x105C` | write `CFG` back |
| `di` | `0x15DE` | `0x1060` | |
| `movd $0x24:l,(r2,r1)` | `0x15E0` | `0x1062` | |
| `lprd (r2,r1),intbase` | `0x15E6` | `0x1068` | **`INTBASE = 0x24`** |
| `movd $0x1c:l,(r3,r2)` | `0x15EA` | `0x106C` | |
| `movd $0x24:l,(r5,r4)` | `0x15F0` | `0x1072` | |
| `bal 0x28D56` | `0x15F6` | `0x1078` | **clear `0x8F2` bytes at `0x936C`** (one record at `0x1C`) |
| `movw $0x800:m,r1` / `lpr r1,psr` | `0x15FA`/`0x15FE` | `0x107C`/`0x1080` | PSR |
| `bal 0x39F8` | `0x1602` | `0x1084` | main path |

`0x28D56` is **not** a byte copy and **not** a vector-table install: it
walks 8-byte records from `(r3,r2)` while the cursor differs from
`(r5,r4)`, and for each record `{u32le count, u32le dest}` it writes `count`
**zero** bytes at `dest` (`r4` is forced to 0 at `0x28D62`).  The call at
`0x15F6` passes `(r3,r2) = 0x1C` and `(r5,r4) = 0x24`, i.e. exactly one
record, which asks for `0x8F2` zeros at `0x936C`.  Full derivation:
`fon-dialog-copy-helper-28d56.md`.

**`CFG` bit 8 is the only `CFG` bit this firmware writes.**  The reference
project TobleMiner (`device/crt0.s`) sets the same bit with the comment
*"Setup CPU to read exception handlers as 32 bit wide"*, and every image
here sets it **before** writing `INTBASE`, whose entries are 32-bit values.
That is a strong hypothesis for the bit's purpose.  It is **not** documented
for the SC14448 and it is **not** evidence about address aliasing.

## 3. Interrupt vectors

`INTBASE = 0x24` means the dispatch table lives at `0x24`.  At `0x24` the
image holds:

```text
0x24: e5 46 01 00 e5 46 01 00 e5 46 01 00 e5 46 01 00
0x74: e5 46 01 00 e5 46 01 00 e5 46 01 00 e5 46 01 00
0x84: cb 44 01 00 ...
0x8C: 68 46 01 00 ...
0x98: 4a 45 01 00 ...
```

Read as **little-endian 32-bit values** the region contains
`0x000146E5` (repeating, the stub), with the differing entries at
**`0x84`** (`0x000144CB`), **`0x8C`** (`0x00014668`) and **`0x98`**
(`0x0001454A`).  **Doubling them** gives `0x28DCA`, `0x28996`, `0x28CD0`,
`0x28A94` — all instruction boundaries inside the image.  Indices **20–22**
(`0x74`, `0x78`, `0x7C`) all hold the stub, not a different entry.
That is a word-offset encoding, so the entries do **not** point outside the
image.  Derivation and the probability argument are in
`fon-dialog-low-memory-analysis.md`.

**Confirmed.**  The table is 31 entries at `0x24`–`0x9F`; entry *n* is at
`0x24 + 4n`, and the stored value is the handler byte address **divided by
two**.  From `0xA0` the bytes `01 05 ff ff …` begin a TLV block
(`tag 1 = RFPI`, length 5, per `include/piglet_protocol.h`), so `0xA0` is
data and not a 32nd vector.

The start-up call at `0x15F6` does **not** touch this table: it is
`fn_28d56(0x1C, 0x24)`, which processes the single record at `0x1C`
(`{count = 0x8F2, destination = 0x936C}`) and clears `0x8F2` zero bytes
there.  See `fon-dialog-copy-helper-28d56.md`.

No `retx` handler is reachable from `0x1602` in mode A.  That is consistent
with the handlers being entered through the dispatch the core performs, not
through a call, and it is **not** evidence that they are absent.

## 4. Reset entry

| Candidate | Why not proven |
|---|---|
| `0x1602` (normal) / `0x1084` (p2test) | reachable from itself only; the block before it (`0x15AA`/`0x102C`) has **no direct caller** in the image |
| `0x15AA` (normal) / `0x102C` (p2test) | the block that sets USP/ISP/CFG/INTBASE; no `bal`/`br` in the image targets it, so it can only be entered from outside (a vector or the loader) |

The start-up block is a **system-register initialisation sequence**, and
nothing in either image jumps to it.  The most economical explanation is
that it is entered by the bootloader or by a vector after a reset, but this
is an inference (**L3 at best**), not a proven reset entry.

## 5. The first-level image (available and analysed)

`firmware/dectfw_firstlevel_441_slow.hex` is present in the repository.  It
covers `0x10080`–`0x102E8` (215 instructions) and is a **boot loader**, not
an application: it programs a UART at `0x000F4900`–`0x000F4906`
(`loadb 0xf4900:m`, `tbit $5`/`$6`,`storw $1,0xf4904/0xf4906`) with a
`0xC350` iteration timeout, which is the classic "wait for the upload,
then hand over" pattern.

### `CFG` bit 8: set *and* cleared

| Site | Image | Operation |
|---|---|---|
| `0x10080`–`0x10088` | first-level | `spr cfg,r0` / `andw $0xFEFF,m` / `lpr r0,cfg` — **clears bit 8** |
| `0x10090`–`0x10094` | first-level | `spr psr,r0` / `andw $0xF5FF,m` / `lpr r0,psr` — clears PSR bits 9 and 11 |
| `0x10278`–`0x10280` | first-level | `spr cfg,r0` / `orw $0x100,m` / `lpr r0,cfg` — **sets bit 8** before a wait loop |
| `0x15D2`–`0x15DA` | second-level (normal) | sets bit 8 (see §2) |
| `0x1054`–`0x105C` | second-level (p2test) | sets bit 8 |

So bit 8 is **toggled around boot phases** (cleared early, set before a
hand-over wait), not held at a constant value during normal operation.

**This does not establish that bit 8 controls address decoding.**  It is
consistent with a boot-mode / hand-over flag.  No offline document describes
the bit, so its function is **UNKNOWN**.

### Other first-level findings

* `storb $0x30,0xf4020:m` and read-modify-writes of `0xF4000`, `0xF400E`,
  `0xF4836`, `0xF4838`, `0xF4900` — the same `0x000F40xx` block the
  second-level image uses.
* `storw $0xff,0xf4c00:m` at `0x102a0` and `0x102ca` — a **direct 16-bit
  write to `0x000F4C00`**, whereas the second-level image writes
  `0xFF4C00` with `storb`.  Same low 20 bits, different high bits, different
  width, different images.  This is a candidate pair, not evidence.
* Branches at `0x1017C`, `0x10250` and `0x10298` are four-byte `disps17`
  forms; under the corrected rule
  (`signed16(word1 & 0xFFFE)`) all three return to **`0x10100`**, the start
  of the UART retry loop.  They are not hand-off branches.

## 6. Remaining gaps

| Question | Status |
|---|---|
| the reset vector | **UNKNOWN** — no vector table at a fixed address was found; `INTBASE = 0x24` and the table there is not plausible code |
| initial dispatch-table contents | **UNKNOWN** — the copy at `0x15F6` runs before interrupts are enabled and its destination is not resolved |
| address-window setup before the second-level image | the first-level image sets and clears `CFG` bit 8 only; no other address-related configuration was found |
| what `CFG` bit 8 does | **UNKNOWN** — not documented offline |

These are recorded as explicit gaps, not filled by assumption.
