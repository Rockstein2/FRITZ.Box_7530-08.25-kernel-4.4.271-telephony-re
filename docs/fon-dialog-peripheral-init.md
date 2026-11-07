# SC14448 firmware: peripheral bring-up around `0x25F90`

Status: **static analysis only, offline**.  No hardware action was taken for
this document.  Every statement below names the instruction address it comes
from; anything without such a reference is a hypothesis and is marked so.

Image: `firmware/dectfw_secondlevel_441.hex` (and the `p2test` variant where
noted).  Toolchain: CR16 binutils 2.44 built locally under
`/tmp/opencode/cr16`; branch targets come from `tools/cr16_branch.py`, which
is validated against that binutils (see `fon-dialog-cr16-branches.md`).

---

## 1. The three functions

Three small functions form the bring-up:

| Address | Role (observed, not named by the vendor) | Size |
|---|---|---|
| `0x25F90` | top-level sequence: fill, start, poll | `0x25F90`–`0x25FB6` |
| `0x25BA` | one fill step: stores one word and increments a counter | `0x25BA`–`0x25D6` (28 B) |
| `0x2558` | writes two peripheral registers, then calls `0x3C8C` | `0x2558`–`0x257C` |
| `0x257E` | writes `0xFF6006`, disables and restores `psr`, clears `0xFF6006` | `0x257E`–`0x25B8` |

`0x2558` and `0x257E` are **separate functions**.  `0x2558` ends at `0x257C`
by splitting the returned word into `r2`/`r3`; `0x257E` is its own entry and
falls into the `0xFF6006` code only after its first call (§4).

### 1.1 Exact listing of the main function

```text
025f90  97 01        push    $0x2,r7,RA
025f92  77 00 00 00 7c 93  movd    $0x937c:l,(r8,r7)
025f98  17 c2        storw   $0x1:s,0x0:s(r8,r7)      ; [0x937C] <- 1
025f9a  b2 5a 01 10  movw    $0x1001:m,r2            ; r2 <- 0x1001
025f9e  fd c0 1d c6  bal     (ra),*-0x25ba:m         ; call 0x25BA
025fa2  07 90        loadw   0x0:s(r8,r7),r0         ; r0 <- [0x937C]
025fa4  b0 52 00 02  cmpw    $0x200:m,r0            ; compare with 0x200
025fa8  49 1f        bhi     *-0x25f9a:s             ; loop body ends at 0x25F9A
025faa  fd c0 af c5  bal     (ra),*-0x2558:m         ; call 0x2558
025fae  0f 89 02 60  loadw   0xf6002:m,r0            ; r0 <- [0x000F6002]
025fb2  10 52        cmpw    $0x1:s,r0               ; compare with 1
025fb4  1d 1f        bne     *-0x25fae:s             ; poll
025fb6  97 03        popret  $0x2,r7,RA
```

All six branch targets were re-decoded with the validated decoder:

| Site | Bytes | Mnemonic | Decoded target | Note |
|---|---|---|---|---|
| `0x25F9E` | `fd c0 1d c6` | `bal` | `0x25BA` | fill helper |
| `0x25FA8` | `49 1f` | `bhi` | `0x2619A` | **not** `0x25F9A` |
| `0x25FAA` | `fd c0 af c5` | `bal` | `0x2558` | selector |
| `0x25FB4` | `1d 1f` | `bne` | `0x261AE` | **not** `0x25FAE` |

### 1.2 The loop is not a loop

`0x25FA8` and `0x25FB4` are 2-byte conditional branches of the `dispe9`
family.  Decoded correctly they point **forward** to `0x2619A` and `0x261AE`,
about 10 instructions past the end of the function.  The instruction at
`0x2619A` is `popret $0x4,r7,RA`, i.e. the epilogue of a *different* function.

What that means for the analysis:

* the `bhi`/`bne` targets currently found are **real decoded values**, but no
  proof exists that execution ever passes through them;
* if the bytes at `0x25FA8`/`0x25FB4` are genuine branch instructions rather
  than data inside a larger construct, the function would leave its own body
  after the first fill step;
* the "loop 512 times" and "poll until ready" readings in older documents
  cannot be supported by the encoding alone.

The safe statement is therefore:

> `0x25F90` calls `0x25BA` once, reads `[0x937C]`, compares it with `0x200`,
> and — **if the conditional at `0x25FA8` is taken as printed** — continues at
> `0x2619A`, outside the function.  The loop and the readiness poll are
> **unproven**.

A future iteration must resolve this byte-level contradiction (the function is
clearly generated as a loop by a compiler, so one of the two decoded
conditionals is being mis-parsed).  Until then the loop travel count is
unknown, and neither 512 nor "until 0x200" may be quoted as fact.

---

## 2. `0x25BA`, the fill step

```text
0025ba  07 01              push    $0x1,r7
0025bc  70 00 00 00 7c 93  movd    $0x937c:l,(r1,r0)
0025c2  30 90              loadw   0x0:s(r1,r0),r3         ; r3 <- [0x937C]
0025c4  74 00 00 01 00 00  movd    $0x1000000:l,(r5,r4)    ; base = 0x01000000
0025ca  36 5f              movzw   r3,(r7,r6)              ; (r7,r6) <- zero-ext(r3)
0025cc  16 4c              ashud   $1:s,(r7,r6)            ; *2
0025ce  64 61              addd    (r7,r6),(r5,r4)         ; base + 2*index
0025d0  24 d0              storw   r2,0x0:s(r5,r4)         ; [base+2*index] <- r2
0025d2  13 32              addw    $0x1:s,r3               ; index + 1
0025d4  30 d0              storw   r3,0x0:s(r1,r0)         ; [0x937C] <- index + 1
0025d6  07 03              popret  $0x1,r7
```

Proven per instruction:

| Address | Operation | Basis |
|---|---|---|
| `0x25C2` | reads the word at `0x0000937C` | `loadw 0x0:s(r1,r0)` after `movd $0x937c:l` |
| `0x25C4` | data base `0x01000000` | `movd ...:l` |
| `0x25CA`–`0x25CC` | index × 2 | `movzw` then `ashud $1` |
| `0x25CE` | address = `0x01000000 + 2·index` | `addd` |
| `0x25D0` | stores the **argument `r2`** as 16 bits | `storw` |
| `0x25D2`–`0x25D4` | counter incremented and written back to `0x937C` | `addw`, `storw` |

So one call writes **one word** at `0x01000000 + 2·index` and leaves the
incremented index in `0x937C`.  The value written is the caller's `r2`; in
`0x25F90` that is `0x1001`.

`0x25BA` has three other callers: `0x2BB4`, `0x333E`, `0x3350` (all
`bal (ra),*-0x25ba`).  At `0x26020` the sequence around a call is

```text
026016  13 00 10 30 7c 93  storw   $0x1:s,0x937c:l     ; index <- 1
02601c  b2 5a 01 09        movw    $0x901:m,r2         ; value 0x901
026020  fd c0 9b c5        bal     (ra),*-0x25ba:m     ; one word
```

so the same helper writes **other values** at other call sites.  `0x937C` is
reset to `1` before the fill and written as a plain 16-bit counter.

---

## 3. `0x2558`, the two-register sequence

```text
002558  1e 01              push    RA
00255a  bf 60 fe ff        addd    $0xfffe:m,(sp)          ; 2-byte scratch
00255e  0f c1 00 64        storw   $0x0:s,0xf6400:m        ; [0x000F6400] <- 0
002562  b0 5a f0 00        movw    $0xf0:m,r0
002566  0f c9 02 64        storw   r0,0xf6402:m            ; [0x000F6402] <- 0xF0
00256a  f4 55              movd    (sp),(r5,r4)
00256c  23 58              movb    $0x2:s,r3
00256e  22 58              movb    $0x2:s,r2
002570  00 c0 1c 17        bal     (ra),*+0x3c8c:m         ; call 0x3C8C
002574  0f 90              loadw   0x0:s(sp),r0
002576  03 59              movb    r0,r3
002578  0f 90              loadw   0x0:s(sp),r0
00257a  80 49              lshw    $-8:s,r0
00257c  02 59              movb    r0,r2
```

The two stores are **proven**: `storw $0x0:s` to the 16-bit absolute
`0x000F6400`, then `storw r0` with `r0 = 0x00F0` to `0x000F6402`.  The function
returns the word left on the stack by `0x3C8C`, split into two bytes in `r2`
and `r3`.

What these two registers *do* is **not** established.  See §5.

---

## 4. `0x257E`, the `0xFF6006` sequence

```text
00257E  ff c0 7b ff        bal     (ra),*-0x24f8:m     ; call 0x24F8 (r2 = high byte)
002582  70 00 ff 00 06 60  movd    $0xff6006:l,(r1,r0)
002588  b2 5a 80 00        movw    $0x80:m,r2
00258c  20 d0              storw   r2,0x0:s(r1,r0)     ; [0xFF6006] <- 0x0080
00258e  14 00 92 30        sprd    psr,(r3,r2)         ; save psr
002592  04 00              di                          ; disabled i-bit
002594  00 2c              nop
002596  73 00 ff 00 06 54  movd    $0xff5406:l,(r4,r3)
00259c  53 90              loadw   0x0:s(r4,r3),r5     ; read  [0xFF5406]
00259e  b5 22 ff f0        andw    $0xf0ff:m,r5        ; clear bits 8..11
0025a2  53 d0              storw   r5,0x0:s(r4,r3)     ; write [0xFF5406]
0025a4  22 5f              movzw   r2,(r3,r2)
0025a6  14 00 92 10        lprd    (r3,r2),psr        ; restore psr
0025aa  20 90              loadw   0x0:s(r1,r0),r2     ; read  [0xFF6006]
0025ac  b2 5a 00 04        movw    $0x400:m,r2
0025b0  2f c9 02 54        storw   r2,0xf5402:m        ; [0x000F5402] <- 0x0400
0025b4  00 c2              storw   $0x0:s(r1,r0)       ; [0xFF6006] <- 0
0025b6  2f 60              addd    $0x2:s,(sp)
0025b8  1e 03              popret  RA
```

Points that are proven by the bytes:

* the **first** `bal` argument is whatever `r2` holds on entry; `0x257E` does
  not set it, so the value passed to `0x24F8` is inherited;
* the read at `0x25AA` (`loadw 0x0:s(r1,r0)`) discards its result: `r2` is
  overwritten by `movw $0x400` at the next instruction;
* the sequence writes `0x80`, then `0xF0FF`-masked `0xFF5406`, then `0x400` to
  `0x000F5402`, then `0` back to `0xFF6006` — a **set/clear pulse around an
  interrupt-mask edit with interrupts disabled**;
* whether `0xFF6006` bit 7 starts a transfer, clears a FIFO, or is a level
  handshake is **unknown**.

Note the odd instruction at `0x25B4`: `storw $0x0:s(r1,r0)` has no separate
source operand register in its text (`00 c2`), so the store value is the
literal `0`.  That is what the encoder produced and what objdump prints; it
is not a register write.

---

## 5. The registers

| Address | Site | Operation | Known | Unknown |
|---|---|---|---|---|
| `0xFF6006` | `0x2582`, `0x258C`, `0x25AA`, `0x25B4` | word RMW | 32-bit absolute (`movd ...:l`), bit 7 set then cleared | function of bit 7; what the read returns |
| `0xFF5406` | `0x2596`, `0x259C`, `0x25A2` | read-modify-write | 32-bit absolute | which peripheral (the address block also holds the GPIO registers at `0xFF4836`/`0xFF4856`) |
| `0xFF400A` | `0x2500`–`0x2534` (in `0x24F8`) | loop over bits 8..10 of a word | 32-bit absolute | bitfield meaning |
| `0x000F6400` | `0x255E` | write `0` | **16-bit** (`:m`) | whether hardware sees `0x000F6400` or `0xFF6400` |
| `0x000F6402` | `0x2566` | write `0x00F0` | **16-bit** (`:m`) | as above |
| `0x000F5402` | `0x25B0` | write `0x0400` | **16-bit** (`:m`) | as above |
| `0x000F6002` | `0x25FAE` | read | **16-bit** (`:m`) | function; expected value `1` |

### 5.1 `:m` versus `:l` — what the encoding shows

`movd $imm32:l,(rp)` emits a 6-byte instruction and can address the full
24-bit space.  `storw r,imm16:m` and `loadw imm16:m,r` emit a **4-byte**
instruction with a 16-bit immediate; the disassembler prints the immediate
as given (`0xf6400:m`), i.e. as the value encoded in the field, with no
segment extension visible.

There is therefore a measurable difference between the two spellings —
`movd` really carries `0x00FF6006`, while `storw`/`loadw` carry only the low
16 bits — but **the firmware does not show whether the core sign- or
segment-extends a 16-bit `:m` address**.  Q44 stays open.

The firmware never uses a `:m` access to any address in the `0xFF00xx` range,
so no comparison is possible inside the image.

---

## 6. Pseudo-code, with provenance

Only proven operations are written as code.  Every line ends with the
instruction that produced it.  Unknown meanings are left as numbers.

```c
/* 0x25F90 -- proven part only */
void unknown_init(void)                    /* 0x25F90 */
{
    /* push $0x2,r7,RA */                  /* 0x25F90 */
    volatile uint16_t *counter = (uint16_t *)0x0000937C;   /* 0x25F92 */
    *counter = 1;                          /* 0x25F98 */
    /* loop and poll are NOT proven: see section 1.2 */

    unknown_fill(0x1001);                  /* 0x25F9E -> 0x25BA */

    if (*counter > 0x200)                  /* 0x25FA2, 0x25FA4, 0x25FA8 */
        goto 0x2619A;                      /* decoded target, unproven */

    /* 0x25FAA -> 0x2558 */
    unknown_selector();                    /* 0x25FAA */

    if (*((volatile uint16_t *)0x000F6002) != 1)   /* 0x25FAE, 0x25FB2 */
        goto 0x261AE;                      /* decoded target, unproven */
}

/* 0x25BA */
void unknown_fill(uint16_t value)          /* arg in r2 */
{
    volatile uint16_t *counter = (uint16_t *)0x0000937C;   /* 0x25BC */
    uint32_t index = *counter;             /* 0x25C2 */
    volatile uint16_t *base = (uint16_t *)0x01000000;      /* 0x25C4 */
    base[index] = value;                   /* 0x25CA..0x25D0 */
    *counter = (uint16_t)(index + 1);      /* 0x25D2, 0x25D4 */
}

/* 0x2558 */
void unknown_selector(void)
{
    *((volatile uint16_t *)0x000F6400) = 0x0000;   /* 0x255E */
    *((volatile uint16_t *)0x000F6402) = 0x00F0;   /* 0x2566 */
    uint16_t r = unknown_3C8C(2, 2);               /* 0x2570 */
    /* r is returned in r3:r2, low byte then high byte */  /* 0x2574..0x257C */
}

/* 0x257E */
void unknown_pulse(uint16_t inherited_r2)
{
    unknown_24F8(inherited_r2);            /* 0x257E */
    volatile uint32_t *ctl = (uint32_t *)0x00FF6006;       /* 0x2582 */
    *ctl = 0x0080;                         /* 0x2588, 0x258C */
    save_and_disable_irq();                /* 0x258E..0x2594 */
    *((volatile uint32_t *)0x00FF5406) &= 0xF0FF;          /* 0x2596..0x25A2 */
    restore_irq();                         /* 0x25A4, 0x25A6 */
    (void)*ctl;                            /* 0x25AA, result discarded */
    *((volatile uint16_t *)0x000F5402) = 0x0400;           /* 0x25B0 */
    *ctl = 0;                              /* 0x25B4 */
}
```

---

## 7. Address `0x01000000`

Proven only:

* it is the base written by `0x25BA`, indexed by the 16-bit counter at
  `0x0000937C`;
* the same base appears as a literal in five other places in the image
  (`0x2E72`, `0x2F98`, `0x36BA`, `0x36EC`, plus the helper at `0x25C4`);
* `0x01000000` is **not part of any loaded run** (runs end at `0x00FFFF`, so
  the address space above `0x00FFFF` belongs to RAM/peripherals, not to the
  code image).

Not proven: that it is a PCM buffer.  The value written is `0x1001`, but its
meaning (descriptor? control word? channel config?) is open.

## 8. Normal versus `p2test`

At the `p2test` addresses the identical instruction sequence exists:

```text
026746  97 01              push    $0x2,r7,RA
026748  77 00 00 00 b6 94  movd    $0x94b6:l,(r8,r7)     ; different counter!
02674e  17 c2              storw   $0x1:s,0x0:s(r8,r7)
026750  b2 5a 01 10        movw    $0x1001:m,r2
026754  fd c0 23 b7        bal     (ra),*-0x1e76:m
026758  07 90              loadw   0x0:s(r8,r7),r0
```

Same value `0x1001`, same 16-bit counter mechanism, but the counter lives at
`0x94B6` instead of `0x937C`.  The fill base inside the called helper
(`0x1000000` at `0x1E80`/`0x1EC0`) is the same.  The two builds are therefore
**not byte-identical** and are only proven to share the pattern:

* value `0x1001`,
* a 16-bit counter,
* base `0x01000000`,
* a readiness read of `0x000F6002`.

Anything beyond that ("functionally identical") is not established.  In
particular `p2test` has no reachable mode-A path from `0x1602` in the current
CFG, and the normal image's `0x25F90` block is reachable from `0x1602`.

---

## 9. What this document does and does not claim

Proven: the instruction streams, the arithmetic of `0x25BA`, the two
`0x000F640x` stores, the `0xFF6006`/`0xFF5406`/`0x000F5402` sequence, the
counter address in both images.

Not proven: the loop count, the poll semantics, the meaning of every
peripheral register, or that any of this is PCM initialisation.  The chain
`0x1602 → … → 0x25F90` is reachable in the CFG, but reachability is not
execution.
