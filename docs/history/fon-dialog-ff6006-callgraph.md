# SC14448 firmware: memory map, `0xFF6006` call graph, and an unresolved decoder question

> **Status: static analysis, partially conclusive.**
> This document is deliberately blunt about what is proven and what is not.
> The last section explains why some addresses below must be treated as
> provisional.

---

## 1. Tool

`binutils-multiarch` does not include CR16.  A CR16 `objdump` was built from
`binutils-2.44` (source already present in the OpenWrt download cache) into
`/tmp/opencode/cr16`, with **nothing installed system-wide**.

Data-path validation is solid: the snippet at `0x2582` decodes to
`movd $0xff6006:l,(r1,r0)`, byte for byte.

Branch-target resolution is **not** solid.  See section 7.

`tools/cr16_fw_map.py` keeps every contiguous run separate (no 0xFF filling
between blocks) and disassembles each at its own VMA.

---

## 2. Memory map (`dectfw_secondlevel_441.hex`)

| Run | Size | Shape |
|---|---|---|
| `0x000000-0x0000d4` | 213 B | **data**, not code |
| `0x0000d6-0x0002b2` | 477 B | small code |
| `0x0002b4-0x001aad` | 6138 B | code, heavy call traffic |
| `0x0024f8-0x003cfd` | 6150 B | code, contains the `0xFF6006` path |
| `0x009000-0x00936a` | 875 B | mostly data |
| `0x009c5e-0x009fff` | 930 B | code |
| `0x017300-0x017e79` | 2938 B | code |
| `0x017fe0-0x017ff7` | 24 B | constants |
| `0x020000-0x028dcd` | 36 302 B | large utility block |

Linear disassembly of the first run yields `illegal` almost everywhere and
long repeated words: it is **data**, and treating it as code produces
nonsense.  This matters because one branch lands there (section 5).

### `p2test` variant

8 runs, 49 736 B; the `0xFF6006` access moves from `0x2582` to `0x1E3E`, the
GPIO set and the UART access shift as well, and one extra GPIO register
(`0xFF4860`) is used.

---

## 3. The `0xFF6006` function (`0x2558`-`0x25B8`)

```text
2558  push RA
255a  addd $0xfffe:m,(sp)
255e  storw $0x0:s,0xf6400:m      ; 0xFF6400 <- 0
2562  movw $0xf0:m,r0
2566  storw r0,0xf6402:m          ; 0xFF6402 <- 0xF0
256a  movd (sp),(r5,r4)           ; argument from the stack
256c  movb $0x2:s,r3
256e  movb $0x2:s,r2
2570  bal ...                     ; call #1  (target disputed, see 7)
2574  loadw 0x0:s(sp),r0
2576  movb r0,r3
2578  loadw 0x0:s(sp),r0
257a  lshw $-8:s,r0
257c  movb r0,r2
257e  bal ...                     ; call #2  (target disputed, see 7)
2582  movd $0xff6006:l,(r1,r0)
2588  movw $0x80:m,r2
258c  storw r2,0x0:s(r1,r0)       ; [0xFF6006] = 0x80
258e  sprd psr,(r3,r2)
2592  di
2596  movd $0xff5406:l,(r4,r3)
259c  loadw 0x0:s(r4,r3),r5
259e  andw $0xf0ff:m,r5           ; clear bits 11..8
25a2  storw r5,0x0:s(r4,r3)
25a4  movzw r2,(r3,r2)
25a6  lprd (r3,r2),psr
25aa  loadw 0x0:s(r1,r0),r2       ; read back, value discarded
25ac  movw $0x400:m,r2
25b0  storw r2,0xf5402:m          ; interrupt controller <- 0x400
25b4  storw $0x0:s,0x0:s(r1,r0)   ; [0xFF6006] = 0
25b6  addd $0x2:s,(sp)
25b8  popret RA
```

### 3.1 Proven about `0xFF6006`

| Claim | Status |
|---|---|
| written `0x80`, read back, written `0` | **proven** |
| `0x80` is `BIT(7)` | **proven** (by value) |
| a trigger, not a format register | **proven**: no rate/word-size/master bit exists in the function, and the value is cleared nine instructions later |
| the read-back value is used | **disproven**: `r2` is overwritten by `movw $0x400` at `0x25ac` |
| what bit 7 *does* to the PCM block | **unknown** |

### 3.2 The surrounding peripherals

`0xFF6400` and `0xFF6402` are written before the PCM access.  Neither is in
the candidate windows from the task, so their meaning is unknown; `0xF0`
into a register that is first zeroed looks like a mask or a divider.

`0xFF5406` gets bits `11..8` cleared, then the interrupt controller is
poked with `0x400`, all inside a `di` / `lprd psr` critical section.  That is
a short critical window, not a PCM configuration.

---

## 4. How `0x2558` is reached

- No direct branch to `0x2558` exists in the image.
- The enclosing block starts at `0x24F8` with:

```text
24f8  cmpb $0x0:s,r2
24fa  beq  *+0x2556:s
```

so the block is a **two-way split on `r2`**, and `0x2558` is the arm taken
when `r2 != 0`.

- The block is not entered by any direct branch either; it is reached by a
  `jump (ra)` from elsewhere, or by an indirect call.

**Caller: not found.**  That is a concrete, bounded negative result over the
whole image, not a guess.

---

## 5. The two calls

Under the interpretation that `objdump` prints an absolute target, the calls
resolve to:

| Call | Target | Content |
|---|---|---|
| `0x2570` | `0x3C8C` / `0x3C90` | inside the same run; code that moves pointers and calls `0x28CF4` and `0x28D3C`, which behave like `memcpy` and `memset` |
| `0x257E` | `0x008A` / `0x0000` | inside the **data** run, depending on the base used |

Under the other interpretation (printed value is a displacement from the run
base) the first call leaves the mapped memory entirely.  The two
interpretations cannot both be right, and the evidence does not yet decide
between them.  See section 7.

---

## 6. Peripheral map

| Firmware | Peripheral | Block |
|---|---|---|
| `0x0011D4` | `0xFF4858` | GPIO set/clear |
| `0x0011E8` | `0xFF4856` | GPIO set/clear |
| `0x0011FA` | `0xFF481E` | GPIO |
| `0x0012B0` | `0xFF5802` | timer |
| `0x0012EA` | `0xFF4838` | GPIO |
| `0x0012FC` | `0xFF4836` | GPIO direction |
| `0x0013A8` | `0xFF4812` | GPIO |
| `0x001414` | `0xFF4808` | GPIO |
| `0x001446` | `0xFF4856` | GPIO set/clear |
| **`0x002582`** | **`0xFF6006`** | PCM/DMA candidate |
| `0x00270A` | `0xFF7056` | RF/analog |
| `0x00271A` | `0xFF7052` | RF/analog |
| `0x026062` | `0xFF4960` | UART |
| `0x002560` | `0xFF6400` | unknown |
| `0x002566` | `0xFF6402` | unknown |

`0xFF600E` was **not found** as an immediate.  Indirect access is not
excluded, so "unused" is not claimed.

`0xFF4000` is used by two small helpers at `0x28A4C` / `0x28A70`; the latter
reads it, masks `0xFFF8` and ORs a value in — a low-three-bit set/clear.

---

## 7. The unresolved decoder question (most important)

The same four bytes produce different printed targets depending on
`--adjust-vma`:

```text
vma 0x0000  bal (ra),*-0xffff7a:m
vma 0x1000  bal (ra),*-0xf7a:m
```

For those bytes both give the same result if the target is
`vma + printed` (`0x86` in both cases).  But applying that rule to the real
function gives `0x6184`, which is outside every mapped run, while the other
rule gives `0x3C8C`, which is inside one.

Neither interpretation is consistent with all observations.  Possible causes:

1. `objdump` prints `target - section_vma` for some encodings and an absolute
   address for others;
2. our assumption that a run's load address equals its HEX address is wrong
   for one of the blocks;
3. the `bal` encodings at `0x2570` and `0x257E` differ in a way the generic
   decode misses.

**Consequence: every branch target in this document is provisional.**
Instruction bytes, instruction boundaries inside a run, and all immediate
values (peripheral addresses, constants) are **not** affected and remain
valid.

---

## 8. PCM / FON search result

Searched the two large code blocks for a receive handler: something that
reads a PCM word, compares it against a table, and drives GPIO.

- the only reader of `0xFF6006` discards the value;
- no path masks a 16-bit word, indexes a table and then writes
  `0xFF4856`/`0xFF4858`;
- the GPIO bit-number-to-mask helper at `0x289B0` is generic, used by many
  callers.

**A slot-5 / FON command handler was not found.**  Boundary: the search
covered every immediate peripheral reference in the image and the full
`0x24F8-0x3CFD` and `0x20000-0x28DCD` blocks.  It cannot exclude code
reached only through a pointer table that was not itself located.

---

## 9. What blocks progress, and what to do next

| Blocker | Why it matters |
|---|---|
| branch-target encoding | every call-graph claim depends on it |
| caller of `0x24F8` | decides what `r2` is, and therefore whether `0x2558` ever runs |
| no link map | cross-block data flow cannot be followed with confidence |

**Recommended next step (offline, no hardware): validate the decoder on a
known-good branch.**  Take a call inside a run whose callee is unmistakable —
for example a call whose target must be the start of a function with a
prologue — and check which interpretation reproduces it.  Until that test
passes, no further call-graph conclusions should be drawn.

Only after that is worth asking whether the SC14448 ever receives slot-5
data.  That answer is more likely to come from running the firmware than
from more static text, and the two directions are independent.
