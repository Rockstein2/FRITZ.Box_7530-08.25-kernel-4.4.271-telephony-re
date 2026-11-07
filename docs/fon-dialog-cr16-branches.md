# CR16 branch decoding — rules, validation, and the resulting call graph

> **Status: decoder solved and validated; call graph re-derived.**
> Everything below is static analysis.  No hardware was touched.

---

## 1. How CR16 computes a branch target

Taken from `binutils-2.44/opcodes/cr16-dis.c` and confirmed on firmware.

### 1.1 Instruction word assembly

```c
cr16_allWords = ((ULONGLONG) word[0] << 32)
              + ((unsigned long) word[1] << 16) + word[2];
```

### 1.2 Field extraction

```c
makelongparameter(val, start, end) = EXTRACT(val, 48 - end, end - start);
```

For a two-word `bal`/branch the argument is 24 bits starting at bit 8:

```c
case 24:
  if (instruction->size == 3) { ... }          /* 3-word form */
  else if (instruction->size == 2)
      p = makelongparameter(cr16_allWords, 8, inst_bit_size);
```

### 1.3 Sign

```c
if (longdisp & 1) { sign_flag = 1; longdisp = ~longdisp + 1; }
```

**The sign is in bit 0 of the displacement field, not in the top bit.**
That is the single most surprising part of the encoding.

### 1.4 Target

```c
number = (relative ? memaddr : 0)
       + (sign_flag ? ((-a->constant) & 0xffffffe) : a->constant);
print_address_func (number & ((1 << 24) - 1));
```

`memaddr` is the **address of the instruction itself**, not the next one.
The result is masked to 24 bits.

### 1.5 What objdump prints

`objdump` prints the **absolute target**, preceded by `*+` or `*-` chosen from
`sign_flag`.  The sign character is **cosmetic** and does not mean the target
is negative.

Decisive evidence (`docs` earlier mis-read this): the branch at `0x0AF0`

```text
  af0: ff c0 a7 f9   bal (ra),*-0x496:m
```

targets `0x496`, and `0x496` begins with

```text
  496: e7 01   push $0x7,r7,RA
```

a function prologue.  A prologue cannot sit mid-function, so the printed
magnitude is the target and `addr - magnitude` (which would be `0x65A`) is
wrong.

`tools/cr16_branch.py` implements this arithmetic; it is used everywhere
instead of parsing objdump's text.

---

## 2. Validation

### 2.1 Positive in-block branch

| | |
|---|---|
| Instruction | `0x2570` |
| Raw | `00 c0 1c 17` |
| Length | 2 words (4 bytes) |
| Field | `0x171c`, bit 0 = 0 → no sign |
| Base | `0x2570` (the instruction) |
| Target | `0x2570 + 0x171c = 0x3c8c` |
| At target | `push $0x3,r7,RA` — prologue |
| Result | **confirmed** |

### 2.2 Negative (sign-flagged) in-block branch

| | |
|---|---|
| Instruction | `0x257E` |
| Raw | `ff c0 7b ff` |
| Field | `0xffff7b`, bit 0 = 1 → sign |
| After negation | `0x85`; `(-0x85) & 0xfffffe = 0xfffff7a` |
| Target | `0x257e + 0xfffff7a = 0x24f8` |
| At target | `cmpb $0x0:s,r2` — block entry |
| Result | **confirmed** |

Second instance: `0x131E` `ff c0 b1 fe` targets `0x11CE`, which begins with
`push $0x1,r7`.  Independent confirmation of the same rule.

### 2.3 Cross-block call

| | |
|---|---|
| Instruction | `0x25E2` |
| Raw | `02 c0 c8 66` |
| Field | `0x266c8`, even → forward |
| Target | `0x25e2 + 0x266c8 = 0x28caa` |
| Block of target | `0x20000–0x28dcd`, a different run |
| At target | `beq0w r3,*+8` (middle of a function, still valid code) |
| Result | **confirmed** — cross-block resolution works |

Independent cross-check: `0x2C6` `02 c0 76 8a` → `0x28d3c`, inside the same
far run; `0x36C` `00 c0 20 01` → `0x48c`, back in the small run.

### 2.4 Sanity statistics

Of 1298 candidate `bal` encodings in the image, **1289 resolve inside a
loaded run**.  The other 9 are near the very end of the image where the
4-byte window runs past the data.

---

## 3. The two calls in `0x2558`

### 3.1 Call #1 — `0x2570` → `0x3C8C`

```text
3c8c: a7 01        push $0x3,r7,RA
3c8e: 37 59        movb r3,r7
3c90: 48 55        movd (r5,r4),(r9,r8)
3c92: ff c0 c5 ff  bal (ra),*-0x3c56   -> 0x3c3c?  (see note)
3c96: 04 55        movd (r1,r0),(r5,r4)
3c98: 72 5d        movzb r7,r2
3c9a: 22 5f        movzw r2,(r3,r2)
3c9c: 00 56        cmpd $0x0:s,(r1,r0)
3c9e: 0a 10        beq  *+0x3cb2
3ca0: bf 60 fc ff  addd $0xfffc:m,(sp)
3ca4: 2f e0        stord (r3,r2),0x0:s(sp)
3ca6: 24 60        addd $0x2:s,(r5,r4)
3ca8: 82 55        movd (r9,r8),(r3,r2)
3caa: 02 c0 4a 50  bal (ra),*+0x28cf4
3cae: 4f 60        addd $0x4:s,(sp)
3cb0: a7 03        popret $0x3,r7,RA
3cb2: 25 55        movd (r3,r2),(r6,r5)
3cb4: 04 5a        movw $0x0:s,r4
3cb6: 82 55        movd (r9,r8),(r3,r2)
3cb8: 02 c0 84 50  bal (ra),*+0x28d3c
3cbc: a7 03        popret $0x3,r7,RA
```

**Interpretation.**  The caller sets `r3 = 2` (a count) and passes a pointer
in `(r5,r4)`.  The callee stores the third byte of its first argument in
`r7` (`movb r3,r7` saves the count), then walks the pointer:

- `movzb r7,r2` scales the **byte count** by `sizeof` of the element,
- `movzw r2,(r3,r2)` reads a 16-bit word,
- `cmpd $0x0,(r1,r0)` treats it as a pointer and compares it to null,
- non-null → the 16-bit value is copied through the far helper `0x28CF4`,
- null → the element is zero-filled through `0x28D3C`.

`0x28CF4` is `memcpy`-shaped (reads source word, writes destination word,
adds 2 to the destination pointer, loops on a count) and `0x28D3C` is
`memset`-shaped (writes `r4` repeatedly).  So **`0x3C8C` is a small
"copy or clear an array of two 16-bit pointers/words" helper, not a PCM
routine.**

The `bal` at `0x3C92` is easy to misread: it sits in the *middle* of the
function, between `movd` and the loop setup.  Under the validated decoder its
target is `0x3C3C`, which is a `push`-prologue helper; the earlier reading of
`0x3C90` as the start of the function was off by four bytes because the
disassembly was started at the wrong index.

### 3.2 Call #2 — `0x257E` → `0x24F8`

This is the **entrance of the enclosing block itself**:

```text
24f8: 02 50        cmpb $0x0:s,r2
24fa: 0e 12        beq  *+0x2556
```

So the call at `0x257E` is a **recursive re-entry** into the block that
contains it, with `r2` set from the low byte of the function's own argument
(`movb r0,r2` after `loadw`/`lshw $-8`).  When that byte is zero the block
returns immediately; otherwise it falls into the `0x2558` arm again.

That is the answer to "who calls `0x24F8`": **only `0x257E`**, and it is the
function calling itself.

### 3.3 Local call graph

```text
0x2558 (block arm, r2 != 0)
 ├─ 0xFF6400 <- 0, 0xFF6402 <- 0xF0
 ├─ 0x2570 ──► 0x3C8C   copy/clear helper
 │                 ├─ 0x3C3C (prologue helper)
 │                 ├─ 0x28CF4 (memcpy-like, 85 callers image-wide)
 │                 └─ 0x28D3C (memset-like, 36 callers)
 ├─ 0x257E ──► 0x24F8   recursive re-entry of the same block
 ├─ 0xFF6006 <- 0x80
 ├─ 0xFF5406 bits 11..8 cleared, 0xFF5402 <- 0x400
 └─ 0xFF6006 <- 0
```

---

## 4. Who calls the block at `0x24F8`

Searched three ways:

1. **direct `bal`** to `0x24F8` or `0x2558`: only `0x257E` (itself);
2. **16-bit aligned words** equal to `0x24F8` / `0x2558` / `0x24FA`: none;
3. **3-byte and 4-byte little-endian pointers** equal to those values: two
   3-byte matches at `0x318D` and `0x287C7`, but both sit **inside**
   `movb $0x25:m,rN` instructions, i.e. they are instruction bytes that
   happen to equal the address, not table entries.

**Conclusion: no external caller exists in this image.**  The block is entered
only by the recursive call from its own `0x2558` arm.  Since nothing can
reach it from outside, the block is either dead code in this build or is
entered by a mechanism not present in the file (a vector installed at run
time, or a call from a block we have not loaded).

### 4.1 Cross-block edges that do exist

| From | To | Count |
|---|---|---|
| `0x2b4-0x1aad` | `0x20000-0x28dcd` | 108 |
| `0x24f8-0x3cfd` | `0x20000-0x28dcd` | 29 |
| `0x24f8-0x3cfd` | `0x9c5e-0x9fff` | 6 |
| `0x24f8-0x3cfd` | `0x2b4-0x1aad` | 6 |
| `0x9c5e-0x9fff` | `0x24f8-0x3cfd` | 5 |
| `0x2b4-0x1aad` | `0x24f8-0x3cfd` | 3 |

The graph is bidirectional between the two large blocks, so the block is not
isolated — but the specific entry at `0x24F8` still has no external caller.

---

## 5. Peripheral map update

Short CR16 operands such as `0xf6400:m` are a **16-bit absolute** operand in
the small-data area.  On this part the accumulator high half is zero, so the
effective address is `0x000F6400`.  Whether the hardware decodes that as
`0xFF6400` is **not established** — the address map in the Dialog material we
have does not cover `0x000F6400`, and the firmware never loads a segment
register around these accesses.

| Firmware site | Encoded | Effective (assuming flat) | Block |
|---|---|---|---|
| `0x0011D4` | `0xff4858:l` | `0xFF4858` | GPIO |
| `0x0011E8` | `0xff4856:l` | `0xFF4856` | GPIO |
| `0x0012FC` | `0xff4836:l` | `0xFF4836` | GPIO direction |
| `0x002582` | `0xff6006:l` | `0xFF6006` | PCM candidate |
| `0x002560` | `0xf6400:m` | `0x000F6400` (?) | **unknown** |
| `0x002566` | `0xf6402:m` | `0x000F6402` (?) | **unknown** |
| `0x00259C` | `0xff5406:l` | `0xFF5406` | interrupt controller |
| `0x0025B0` | `0xf5402:m` | `0x000F5402` (?) | interrupt controller (?) |

The `0xF5xxxx`/`0xF6xxxx` accesses all appear immediately next to
`0xFF5xxx`/`0xFF6xxx` ones, which strongly suggests they are the **same
registers reached with a different segment**, but that is an inference, not
a proof.

### 5.1 The `0xFF6400` / `0xFF6402` sequence

```text
0xFF6400 <- 0x0000
0xFF6402 <- 0x00F0
... send something ...
0xFF6006 <- 0x0080
[interrupt-controller window]
0xFF6006 <- 0x0000
```

Zero then `0xF0` in an adjacent register, followed by a set/clear pulse on
`0xFF6006`, reads like **a channel or divider reset followed by a request**.
That is a hypothesis.  Neither register's function is documented in the
material available.

---

## 6. PCM RX / FON handler search

Result: **not found**, with these boundaries:

- searched every immediate peripheral reference in the image;
- followed the cross-block call graph between all nine runs;
- examined every function that touches `0xFF6006` or the GPIO set/clear
  registers.

What *was* found and is not a FON handler:

- `0x3C8C` copies or clears arrays — a generic helper;
- `0x289B0` converts a bit number to a mask — used by many callers;
- the `0xFF6006` reader discards the value it reads.

Most likely candidates if a handler exists outside this image: the block
entered from a vector installed at run time, or one of the 9 unresolved `bal`
encodings near the end of the file.

---

## 7. What remains unknown

| Item | Why |
|---|---|
| what `0xFF6400`/`0xFF6402` are | not in any address map we have; the `0x000Fxxxx` vs `0xFFxxxx` question is unresolved |
| what `BIT(7)` of `0xFF6006` triggers | no code reads the result back |
| how the `0x24F8` block is entered | no caller in the image |
| whether a PCM RX handler exists at all | not found, but the search cannot cover run-time-installed vectors |
| meaning of the 9 unresolved branches | they sit where the 4-byte window runs off the data |
