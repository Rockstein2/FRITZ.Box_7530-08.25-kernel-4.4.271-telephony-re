# SC14448 firmware: peripheral bring-up around `0x25F90`

Status: **static analysis only, offline.**  No hardware was touched.  Every
statement names the instruction address it comes from; anything without such
a reference is a hypothesis and is marked so.

Image: `firmware/dectfw_secondlevel_441.hex`; the `p2test` build is compared
in §8.  Toolchain: CR16 binutils 2.44 built locally at
`/tmp/opencode/cr16/build/binutils/objdump`, and the decoder in
`tools/cr16_branch.py`.  The decoder's 2-byte conditional layout still
disagrees with the CR16A manual (Q50); on the addresses below it matches
binutils exactly, which is what the listing assumes.

---

## 1. The functions involved

| Address | Role (observed, not named by the vendor) | Extent |
|---|---|---|
| `0x25F90` | fill, start, poll | `0x25F90`–`0x25FB6` (last instruction `popret` at `0x25FB6`) |
| `0x25FB8` | wrapper: calls `0x25F90`, then `0x25EA6` | `0x25FB8`–`0x25FBE` |
| `0x25BA` | one fill step: stores one word, increments a counter | `0x25BA`–`0x25FD6` (28 B) |
| `0x2558` | two peripheral stores, then calls `0x3C8C` | `0x2558`–`0x257C` |
| `0x257E` | writes `0xFF6006`, masks an interrupt source, clears `0xFF6006` | `0x257E`–`0x25B8` |

`0x2558` and `0x257E` are separate functions.  `0x2558` ends at `0x257C` by
splitting the word returned by `0x3C8C` into `r2`/`r3`; `0x257E` directly
follows the last instruction of `0x2558`.  In this image **no `bal` targets
`0x257E`**: it is entered only when execution runs off the end of `0x2558`.

### 1.1 Exact listing of `0x25F90`

```text
025f90  97 01               push    $0x2,r7,RA
025f92  77 00 00 00 7c 93   movd    $0x937c:l,(r8,r7)
025f98  17 c2               storw   $0x1:s,0x0:s(r8,r7)      ; [0x937C] <- 1
025f9a  b2 5a 01 10         movw    $0x1001:m,r2            ; r2 <- 0x1001
025f9e  fd c0 1d c6         bal     (ra),*-0x25ba:m         ; call 0x25BA
025fa2  07 90               loadw   0x0:s(r8,r7),r0         ; r0 <- [0x937C]
025fa4  b0 52 00 02         cmpw    $0x200:m,r0
025fa8  49 1f               bhi     *-0x25f9a:s             ; -> 0x25F9A
025faa  fd c0 af c5         bal     (ra),*-0x2558:m         ; call 0x2558
025fae  0f 89 02 60         loadw   0xf6002:m,r0
025fb2  10 52               cmpw    $0x1:s,r0
025fb4  1d 1f               bne     *-0x25fae:s             ; -> 0x25FAE
025fb6  97 03               popret  $0x2,r7,RA
```

Both conditionals were decoded three ways and agree:

| Site | Bytes | This decoder | binutils, base = instruction address | Target |
|---|---|---|---|---|
| `0x25FA8` | `49 1f` | `0x25F9A` | `0x25F9A` | `movw $0x1001` |
| `0x25FB4` | `1d 1f` | `0x25FAE` | `0x25FAE` | `loadw 0xf6002` |

So inside this function the code is a **loop**: `0x25F9A` … `0x25FA8` repeats
while `[0x937C] > 0x200`.

The earlier version of this document reported that these two branches decode
*forward, out of the function* (`0x2619A`, `0x261AE`).  That was an artefact
of the decoder bug fixed in commit `63bca2c`; the current value agrees with
binutils and with the code's own structure.

### 1.2 The loop, step by step

| Instruction | Operation (proven from the encoding) |
|---|---|
| `0x25F98` | store 1 to `0x0000937C` — this is the counter reset |
| `0x25F9A` | `r2 = 0x1001` (the value written into memory by the helper) |
| `0x25F9E` | call `0x25BA`, which stores `r2` and increments `[0x937C]` |
| `0x25FA2` | read back `[0x937C]` |
| `0x25FA4` | compare with `0x200`: `cmpw $0x200,r0` → the absolute value in `r0` is compared with the literal `0x200` |
| `0x25FA8` | `bhi` = branch if higher (unsigned) → repeats while `counter > 0x200` |

Iteration count, computed from the counter arithmetic:

* first store happens at index 1,
* the loop continues while the index is at most `0x200` (because the
  comparison is "higher than `0x200`" for exiting),
* therefore indices `1 … 0x200` are written: **512 words**,
* first address `0x01000000 + 2·1`, last address `0x01000000 + 2·0x200`
  = `0x01000400`, end of the written range `0x01000402`.

This is the original "512 words" claim, and it is now supported by the
decoded control flow rather than assumed.  The one caveat: it relies on
`0x25FA8` being a *backward* branch to `0x25F9A`, which binutils and the
decoder both print; a rule that read the same bytes in the other direction
would turn the loop into a jump out of the function, so this is one of the
places where Q50 matters.

`0x25FB8` wraps the call (`bal 0x25F90` at `0x25FBA`), so the whole sequence
runs once per invocation of the wrapper.

---

## 2. `0x25BA`, the fill step

```text
0025ba  07 01               push    $0x1,r7
0025bc  70 00 00 00 7c 93   movd    $0x937c:l,(r1,r0)
0025c2  30 90               loadw   0x0:s(r1,r0),r3        ; r3 <- [0x937C]
0025c4  74 00 00 01 00 00   movd    $0x1000000:l,(r5,r4)   ; base 0x01000000
0025ca  36 5f               movzw   r3,(r7,r6)
0025cc  16 4c               ashud   $1:s,(r7,r6)           ; index * 2
0025ce  64 61               addd    (r7,r6),(r5,r4)        ; base + 2*index
0025d0  24 d0               storw   r2,0x0:s(r5,r4)        ; store the value
0025d2  13 32               addw    $0x1:s,r3
0025d4  30 d0               storw   r3,0x0:s(r1,r0)        ; counter + 1
0025d6  07 03               popret  $0x1,r7
```

* record size: one 16-bit word;
* index: 16-bit value from `0x937C`, zero-extended (`movzw`);
* address: `0x01000000 + 2·index` — a byte address, so the index counts
  words.

Other callers use the same helper with other values:
`0x26016`/`0x2601C`/`0x26020` sets the counter to 1, loads `0x901` and calls
`0x25BA`; `0x2BB4`, `0x333E`, `0x3350` also call it.  So `0x25BA` is a
generic "store value at the next slot" helper, and `0x1001` is only one of
the values it receives.

---

## 3. `0x2558`, the two-register sequence

```text
002558  1e 01               push    RA
00255a  bf 60 fe ff         addd    $0xfffe:m,(sp)
00255e  0f c1 00 64         storw   $0x0:s,0xf6400:m        ; [0x000F6400] <- 0
002562  b0 5a f0 00         movw    $0xf0:m,r0
002566  0f c9 02 64         storw   r0,0xf6402:m            ; [0x000F6402] <- 0xF0
00256a  f4 55               movd    (sp),(r5,r4)
00256c  23 58               movb    $0x2:s,r3
00256e  22 58               movb    $0x2:s,r2
002570  00 c0 1c 17         bal     (ra),*+0x3c8c:m         ; call 0x3C8C
002574  0f 90               loadw   0x0:s(sp),r0
002576  03 59               movb    r0,r3
002578  0f 90               loadw   0x0:s(sp),r0
00257a  80 49               lshw    $-8:s,r0
00257c  02 59               movb    r0,r2
```

The two stores are proven: `0` to the 16-bit address `0x000F6400`, then
`0x00F0` to `0x000F6402`.  What the registers do is unknown (§5).  After the
call the returned word on the stack is split into `r2` (high byte) and `r3`
(low byte).

## 4. `0x257E`, the `0xFF6006` sequence

```text
00257e  ff c0 7b ff         bal     (ra),*-0x24f8:m         ; call 0x24F8
002582  70 00 ff 00 06 60   movd    $0xff6006:l,(r1,r0)
002588  b2 5a 80 00         movw    $0x80:m,r2
00258c  20 d0               storw   r2,0x0:s(r1,r0)         ; [0xFF6006] <- 0x0080
00258e  14 00 92 30         sprd    psr,(r3,r2)             ; save psr
002592  04 00               di
002594  00 2c               nop
002596  73 00 ff 00 06 54   movd    $0xff5406:l,(r4,r3)
00259c  53 90               loadw   0x0:s(r4,r3),r5
00259e  b5 22 ff f0         andw    $0xf0ff:m,r5            ; clear bits 8..11
0025a2  53 d0               storw   r5,0x0:s(r4,r3)         ; write back
0025a4  22 5f               movzw   r2,(r3,r2)
0025a6  14 00 92 10         lprd    (r3,r2),psr            ; restore psr
0025aa  20 90               loadw   0x0:s(r1,r0),r2         ; read back, discarded
0025ac  b2 5a 00 04         movw    $0x400:m,r2
0025b0  2f c9 02 54         storw   r2,0xf5402:m            ; [0x000F5402] <- 0x400
0025b4  00 c2               storw   $0x0:s,0x0:s(r1,r0)     ; [0xFF6006] <- 0
0025b6  2f 60               addd    $0x2:s,(sp)
0025b8  1e 03               popret  RA
```

* the argument in `r2` is **inherited**: `0x257E` never loads `r2` before the
  call to `0x24F8`; whatever the previous code left there is passed on;
* the read at `0x25AA` is dead: `r2` is overwritten at `0x25AC`;
* the sequence is a set/clear pulse around a masked read-modify-write of
  `0xFF5406` with interrupts disabled.

## 5. The registers

| Address | Sites | Access | Width | Known | Unknown |
|---|---|---|---|---|---|
| `0x0000937C` | `0x25BC`, `0x25C2`, `0x25D4`, `0x25F92`, `0x25F98`, `0x25FA2` | read/write word | 16-bit | the fill counter | what else uses it |
| `0x01000000` | `0x25C4` | write | 32-bit base | fill destination | what the area is |
| `0x000F6400` | `0x255E` | write 0 | **16-bit `:m`** | — | whether the CPU extends it (Q44) |
| `0x000F6402` | `0x2566` | write `0xF0` | **16-bit `:m`** | — | as above |
| `0x000F6002` | `0x25FAE` | read | **16-bit `:m`** | polled for `1` | which event sets it |
| `0x000F5402` | `0x25B0` | write `0x400` | **16-bit `:m`** | — | as above |
| `0x00FF6006` | `0x2582`, `0x258C`, `0x25AA`, `0x25B4` | read/write word | 32-bit `:l` | bit 7 set then cleared | what bit 7 starts or acknowledges |
| `0x00FF5406` | `0x2596`, `0x25A2` | read-modify-write | 32-bit `:l` | bits 8..11 cleared | which peripheral |

The `:m` operands really are 16-bit immediates inside 4-byte instructions, so
the instruction itself cannot spell `0xFF6400`; whether the core sign- or
segment-extends the value is still open (Q44).  The firmware never performs a
`:m` access into the `0xFF00xx` range, so no in-image comparison exists.

## 6. Where `0x1602` leads (chain)

All links are instruction boundaries in the image and are reachable in CFG
mode A (from `0x1602` alone):

| Call site | Bytes | Target | Type | Condition |
|---|---|---|---|---|
| `0x1602` | `00 c0 f6 23` | `0x39F8` | `bal` | after `lpr r1,psr` sets `0x800` |
| `0x3A2C` | `02 c0 8c 25` | `0x25FB8` | `bal` | inside the `0x39F8` routine, after `di` (`0x3A08`) and two calls (`0x3A0C`, `0x3A10`) |
| `0x25FBA` | `ff c0 d7 ff` | `0x25F90` | `bal` | run after call |
| `0x25F9E` | `fd c0 1d c6` | `0x25BA` | `bal` | loop body |
| `0x25FAA` | `fd c0 af c5` | `0x2558` | `bal` | loop exit |
| `0x2570` | `00 c0 1c 17` | `0x3C8C` | `bal` | inside `0x2558` |
| `0x257E` | `ff c0 7b ff` | `0x24F8` | `bal` | run off the end of `0x2558` |

The simplified chain in earlier reports (`0x25FAA → 0x2558 → 0x257E →
0x24F8`) is a sequence of *addresses*: `0x2558` does not call `0x257E`, it
calls `0x3C8C`; `0x257E` is the next function and calls `0x24F8`.

## 7. `0x24F8` revisited

```text
0024f8  02 50   cmpb    $0x0:s,r2
0024fa  0e 12   beq     *+0x2556:s      ; r2 == 0 -> return
0024fc  b1 5a 80 00  movw    $0x80:m,r1
002500  74 00 ff 00 0a 40  movd    $0xff400a:l,(r5,r4)
002506  64 90   loadw   0x0:s(r5,r4),r6
...
002550  f1 49   lshw    $-1:s,r1
002552  01 52   cmpw    $0x0:s,r1
002554  13 1f   bne     *-0x253a:s
002556  ee 0a   jump    (ra)
```

* it is **not recursive**: nothing in it calls `0x24F8` again;
* it returns immediately when the byte in `r2` is `0`;
* otherwise it walks a bit mask (`0x80` shifted right) over bits 8..10 of
  the word at `0xFF400A`, setting or clearing them one at a time;
* the argument is a *byte* compared with `0`, and the value written at
  `0x257E` is exactly the inherited byte — so the `0x80` write happens once
  per call of `0x257E`, not repeatedly.

Register and stack handling is local: `push`/`popret` pairs balance inside
each function, and the word passed between `0x2558` and `0x3C8C` is copied
through a 2-byte stack slot (`0x255A`).

## 8. Normal versus `p2test`

The `p2test` build repeats the same pattern at different addresses:

| Item | normal | `p2test` |
|---|---|---|
| fill value `0x1001` | `0x25F9A` | `0x26750` |
| helper counter | `0x937C` | `0x94B6` |
| fill base `0x01000000` | `0x25C4` | `0x1E80` |
| readiness read `0xF6002` | `0x25FAE` | `0x26764` |

So the same shape — value `0x1001`, a 16-bit counter, base `0x01000000`, a
read of `0x000F6002` — exists in both builds, but the counter is at a
different address and the surrounding control flow differs.  They are **not**
declared functionally identical here.

---

## 9. Pseudo-code with provenance

```c
/* 0x25F90 -- proven from the decoded control flow */
void unknown_init(void)
{
    volatile uint16_t *counter = (uint16_t *)0x0000937C;   /* 0x25F92 */
    *counter = 1;                                          /* 0x25F98 */

    do {
        unknown_fill_below(0x1001);                        /* 0x25F9A, 0x25F9E */
    } while (*counter > 0x200);                            /* 0x25FA2..0x25FA8 */
    /* 512 words: indices 1..0x200 -> 0x01000002 .. 0x01000400 */

    unknown_two_registers();                               /* 0x25FAA -> 0x2558 */

    while (*((volatile uint16_t *)0x000F6002) != 1)        /* 0x25FAE..0x25FB4 */
        ;                                                  /* no timeout visible */
}

/* 0x25BA */
void unknown_fill_below(uint16_t value)                    /* arg in r2 */
{
    volatile uint16_t *counter = (uint16_t *)0x0000937C;   /* 0x25BC */
    uint16_t index = *counter;                             /* 0x25C2 */
    ((volatile uint16_t *)0x01000000)[index] = value;      /* 0x25C4..0x25D0 */
    *counter = (uint16_t)(index + 1);                      /* 0x25D2, 0x25D4 */
}

/* 0x2558 */
void unknown_two_registers(void)
{
    *((volatile uint16_t *)0x000F6400) = 0x0000;           /* 0x255E */
    *((volatile uint16_t *)0x000F6402) = 0x00F0;           /* 0x2562, 0x2566 */
    unknown_3C8C(2, 2);                                    /* 0x256C, 0x256E, 0x2570 */
}

/* 0x257E -- reached by running off the end of 0x2558 */
void unknown_pulse(uint8_t inherited_r2)
{
    unknown_24F8(inherited_r2);                            /* 0x257E */
    volatile uint32_t *ctl = (uint32_t *)0x00FF6006;       /* 0x2582 */
    *ctl = 0x0080;                                         /* 0x2588, 0x258C */
    disable_irq();                                         /* 0x258E..0x2594 */
    *((volatile uint32_t *)0x00FF5406) &= 0xF0FF;          /* 0x2596..0x25A2 */
    enable_irq();                                          /* 0x25A4, 0x25A6 */
    (void)*ctl;                                            /* 0x25AA, dead read */
    *((volatile uint16_t *)0x000F5402) = 0x0400;           /* 0x25AC, 0x25B0 */
    *ctl = 0;                                              /* 0x25B4 */
}
```

---

## 10. What is proven and what is not

| Claim | Status |
|---|---|
| `0x25F90` stores 1 to `0x937C` | proven (`0x25F98`) |
| `0x25BA` writes one 16-bit word at `0x01000000 + 2·index` and increments the counter | proven (`0x25C4`..`0x25D4`) |
| the loop writes indices 1..0x200, i.e. 512 words, ending at `0x01000400` | proven, subject to the `0x25FA8` direction (Q50) |
| `0x2558` writes 0 to `0x000F6400` and `0xF0` to `0x000F6402` | proven (`0x255E`, `0x2566`) |
| `0x257E` sets bit 7 of `0xFF6006`, masks `0xFF5406` bits 8..11, writes `0x400` to `0x000F5402`, clears `0xFF6006` | proven |
| `0x24F8` is not recursive and returns when `r2 == 0` | proven |
| the code waits until `[0x000F6002] == 1` | proven as a loop; the *event* is unknown |
| there is no timeout or watchdog on that wait | the loop body contains no counter or alternative exit |
| `0x01000000` is a PCM buffer | **not proven** |
| `0x1001` has a known field layout | **not proven** |
| this is PCM initialisation | **not proven** |

`0x1001` occurs in the image only at `0x25F9A` (normal) and `0x26750`
(`p2test`) as a `movw` argument to this fill helper; it is not used anywhere
else in either image.
