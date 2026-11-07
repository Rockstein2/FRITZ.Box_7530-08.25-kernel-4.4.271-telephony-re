# SC14448 firmware: peripheral bring-up around `0x25F90`

Status: **static analysis only, offline.**  Every claim carries a level:

| Level | Meaning |
|---|---|
| **L1 BYTES** | instruction bytes and their addresses read from the image |
| **L2 DECODE** | the encoding is confirmed by binutils and/or the CR16A manual |
| **L3 CFG** | control-flow edges between basic blocks |
| **L4 SEMANTICS** | flags, arguments, stack and the effect of the operations |
| **L5 HARDWARE** | observed on a real SC14448 — **not reached in this document** |

Image: `firmware/dectfw_secondlevel_441.hex`
(sha256 `7cac33c72b222246…`); the `p2test` variant is compared in §8.

---

## 1. `0x25F90`, the exact algorithm

### 1.1 Listing

```text
025f90  97 01               push    $0x2,r7,RA
025f92  77 00 00 00 7c 93   movd    $0x937c:l,(r8,r7)
025f98  17 c2               storw   $0x1:s,0x0:s(r8,r7)       ; [0x937C] = 1
025f9a  b2 5a 01 10         movw    $0x1001:m,r2              ; r2 = 0x1001
025f9e  fd c0 1d c6         bal     (ra),*-0x25ba:m           ; call 0x25BA
025fa2  07 90               loadw   0x0:s(r8,r7),r0           ; r0 = [0x937C]
025fa4  b0 52 00 02         cmpw    $0x200:m,r0
025fa8  49 1f               bhi     *-0x25f9a:s              ; -> 0x25F9A
025faa  fd c0 af c5         bal     (ra),*-0x2558:m           ; call 0x2558
025fae  0f 89 02 60         loadw   0xf6002:m,r0
025fb2  10 52               cmpw    $0x1:s,r0
025fb4  1d 1f               bne     *-0x25fae:s              ; -> 0x25FAE
025fb6  97 03               popret  $0x2,r7,RA
```

### 1.2 The two branch targets (L2)

| Site | Bytes | Field | Sign | Displacement | Target |
|---|---|---|---|---|---|
| `0x25FA8` | `49 1f` | `0x0E` | 1 | −0x0E | `0x25F9A` |
| `0x25FB4` | `1d 1f` | `0x06` | 1 | −0x06 | `0x25FAE` |

Both agree with `objdump` at the instruction's own address, and the field
arithmetic follows binutils `cr16-dis.c` `case 8` (see
`fon-dialog-cr16-branches.md` §2).  So `0x25F9A..0x25FA8` is a loop and
`0x25FAE..0x25FB4` is a wait loop.  (L3)

### 1.3 `CMPW` and `BHI` (L4, from the CR16A manual)

* `cmpw $0x200, r0` — immediate form, `Rsrc = 0x200`, `Rdest = r0`.
  The instruction subtracts `src1` from `src2` and sets three flags:
  `PSR.Z` (equal), `PSR.N` (signed greater), **`PSR.L` (the Low flag:
  “set to 1 if the second operand Rdest is less than the first operand
  Rsrc, unsigned”)**.
* `bhi` — “Conditional Branch if Higher”: **taken when `L` is 1**,
  i.e. when `Rdest < Rsrc`, here when `r0 < 0x200`.

There is no carry/borrow flag involved; the condition is the `L` flag.

### 1.4 The fill step `0x25BA` (L1 + L2)

```text
0025ba  07 01               push    $0x1,r7
0025bc  70 00 00 00 7c 93   movd    $0x937c:l,(r1,r0)
0025c2  30 90               loadw   0x0:s(r1,r0),r3          ; r3 = [0x937C]
0025c4  74 00 00 01 00 00   movd    $0x1000000:l,(r5,r4)     ; base
0025ca  36 5f               movzw   r3,(r7,r6)
0025cc  16 4c               ashud   $1:s,(r7,r6)             ; index * 2
0025ce  64 61               addd    (r7,r6),(r5,r4)
0025d0  24 d0               storw   r2,0x0:s(r5,r4)          ; store
0025d2  13 32               addw    $0x1:s,r3
0025d4  30 d0               storw   r3,0x0:s(r1,r0)          ; [0x937C] = index + 1
0025d6  07 03               popret  $0x1,r7
```

One call writes one 16-bit word at `0x01000000 + 2·index` and increments the
counter.

### 1.5 Iteration count (L4)

The counter runs `1 → 0x200`, and the loop test is `r0 < 0x200` with `r0`
read *after* the increment:

| index before write | address written | counter after | `cmpw` operands | `L` | `bhi` |
|---|---|---|---|---|---|
| 1 | `0x01000002` | 2 | `0x200` vs `r0=2` | 1 | taken |
| 2 | `0x01000004` | 3 | `0x200` vs 3 | 1 | taken |
| 510 | `0x010003FC` | 511 | `0x200` vs 511 | 1 | taken |
| 511 | `0x010003FE` | 512 | `0x200` vs 512 | 0 | **not taken** |
| 512 | — | — | — | — | loop already left |

**511 writes**, indices 1…511, addresses `0x01000002` … `0x010003FE`, run
end `0x01000400`.  The previous “512” counted the initial value 1 as a write,
which it is not: the first store happens inside the loop.

Corroboration: two more loops in the same image use the identical
`addw $1` / `cmpw $0x28` / `bhi <back>` shape — `0x25C5E`–`0x25C64`
(looping to `0x25C4A`) and `0x25E5E`–`0x25E64` (looping to `0x25D9E`).  With
`Rdest < Rsrc` both are genuine bounded loops; the opposite operand order
would make each of them execute once and leave, which no compiler emits for
an explicitly counter-based construct.

The equivalence “`bhi` after `cmpw $imm, rX` means `rX < imm`” was checked
by hand on the three loops above; it depends on the manual's flag table and
is **not** an observation on silicon (no L5).

## 2. Address operands: `abs20` (L1 + L2)

The four instructions of the sequence use two different address forms.

| Instruction | Bytes | Operand form | Address field | Effective address |
|---|---|---|---|---|
| `loadw 0xf6002:m,r0` | `0f 89 02 60` | `{abs20,0}` + `regr` | `((0x0F & 0x0F) << 16) \| 0x6002` | `0x000F6002` |
| `storw r0,0xf6402:m` | `0f c9 02 64` | `abs20` + `regr` | `(0x0F << 16) \| 0x6402` | `0x000F6402` |
| `storw r2,0xf5402:m` | `2f c9 02 54` | `abs20` + `regr` | `(0x0F << 16) \| 0x5402` | `0x000F5402` |
| `movd $0xff6006:l,(r1,r0)` | `70 00 ff 00 06 60` | `imm32` = `{abs24,16}` | 24-bit literal | `0x00FF6006` |

Details:

* the `:m` suffix is a **display width marker**, not the access width:
  `loadw`/`storw` are 16-bit accesses, `loadd`/`stord` 32-bit, and the
  suffix only tells how many bits the address field holds (`:s` ≤ 8,
  `:m` 16/20, `:l` 24/32);
* the field is `((byte0 & 0x0F) << 16) | (byte2 | byte3 << 8)`; sweeping
  `byte0` over `0x0…0xF` moves the address by `0x10000` each time, which
  was verified with objdump on synthetic words as well as on the image;
* **there is no segment register and no page mapping** for these accesses:
  the address is complete in the instruction.  The CR16A manual's absolute
  load/store figure (A-9) shows only the low 16 bits plus two upper bits,
  while the firmware needs bit 19 for `0xF6006`, so the SC14448 uses a wider
  field than the CR16A drawing shows; this is recorded as the remaining
  format question (Q44), not as a segment translation.

## 3. Access widths

Three widths are easy to confuse in this code; the table keeps them apart.

| Item | Width | Evidence |
|---|---|---|
| hardware address field | `abs20` for `:m` operands, 24 bits in the `movd` literal | `cr16-opc.c` operands `{abs20,0}` and `{op1,0},{regp,16}` |
| address in a register pair | 32 bits (`r1:r0`, `r4:r3`, …) | `movd $0xff6006:l,(r1,r0)` loads both halves |
| the operation on the bus | 16 bits for `loadw`/`storw`, 32 bits for `loadd`/`stord` | instruction mnemonic |
| the value operand | 16 bits (`r2`, `$0x80:m`) | `movw`/`storw` register operands |

So `movd $0xff6006:l,(r1,r0)` is a **32-bit address load**, and the write that
follows it, `storw r2,0x0:s(r1,r0)`, is a **16-bit store**.  Nothing in the
sequence writes 32 bits to `0xFF6006` or `0xFF5406`.

## 4. Register table (L1/L2 only)

| Address | Sites | Access | What is proven | What is not |
|---|---|---|---|---|
| `0x0000937C` | `0x25BC`…`0x25FA2` | 16-bit R/W | fill counter | — |
| `0x01000000` | `0x25C4` | 16-bit writes, `+2·idx` | fill base | what the area is |
| `0x000F6400` | `0x255E` | write 0 | value sent | function |
| `0x000F6402` | `0x2566` | write `0x00F0` | value sent | function |
| `0x000F6002` | `0x25FAE` | read | polled for 1 | which event sets it |
| `0x000F5402` | `0x25B0`, `0x3A28`, `0x1934` | write `0x400`, `0xFFFF`, … | values | function |
| `0x00FF6006` | `0x2582`/`0x258C`/`0x25AA`/`0x25B4` | 32-bit R/W | `0x80` set then cleared | what bit 7 does |
| `0x00FF5406` | `0x2596`/`0x25A2` | 32-bit RMW | bits 8..11 cleared | which block |

No claim is made that `0x000F6400` and `0x00FF6400` are the same register.

## 5. `0x2558` – `0x25B8`: one function (L3 + L4)

| Address | Instruction | Effect |
|---|---|---|
| `0x2558` | `push RA` | SP −2 |
| `0x255A` | `addd $0xfffe,(sp)` | SP −2, 2-byte scratch |
| `0x255E` | `storw $0,0xf6400:m` | write 0 |
| `0x2562`/`0x2566` | `movw $0xf0,r0` / `storw r0,0xf6402:m` | write 0xF0 |
| `0x256A`–`0x2570` | `movd (sp),(r5,r4)`, arguments 2,2, `bal 0x3C8C` | call |
| `0x2574`–`0x257C` | read the scratch word; `r3 = low byte`, `r2 = high byte` | split |
| `0x257E` | `bal 0x24F8` | call with `r2` |
| `0x2582`–`0x25B4` | pulse sequence (see §5) | writes |
| `0x25B6` | `addd $0x2,(sp)` | SP +2 |
| `0x25B8` | `popret RA` | SP +2, return |

There is no return or jump between `0x257C` and `0x257E`; the block from
`0x257E` on is reached by falling through.  No `bal` anywhere in either
image targets `0x257E`, so it is **not** a separately called function.
`0x24F8` receives the byte in `r2` and returns when it is zero.

## 6. The `0xFF6006` pulse (L2)

```text
002582  movd $0xff6006:l,(r1,r0)
002588  movw $0x80:m,r2
00258c  storw r2,0x0:s(r1,r0)      ; [0xFF6006] = 0x0080
00258e  sprd psr,(r3,r2)           ; save PSR
002592  di                         ; interrupts disabled
002596  movd $0xff5406:l,(r4,r3)
00259c  loadw 0x0:s(r4,r3),r5
00259e  andw $0xf0ff:m,r5          ; clear bits 8..11
0025a2  storw r5,0x0:s(r4,r3)
0025a4  movzw r2,(r3,r2)
0025a6  lprd (r3,r2),psr           ; restore PSR
0025aa  loadw 0x0:s(r1,r0),r2      ; read back, overwritten below
0025ac  movw $0x400:m,r2
0025b0  storw r2,0xf5402:m         ; [0x000F5402] = 0x0400
0025b4  storw $0x0:s,0x0:s(r1,r0)  ; [0xFF6006] = 0
```

## 7. Normal versus `p2test`

| Item | normal | `p2test` |
|---|---|---|
| fill value `0x1001` | `0x25F9A` | `0x26750` |
| counter | `0x937C` | `0x94B6` |
| fill base | `0x01000000` (`0x25C4`) | `0x01000000` (`0x1E80`) |
| readiness read | `0xF6002` (`0x25FAE`) | `0xF6002` (`0x26764`) |
| loop bound | `0x200` | `0x200` |
| same-pattern loops with bound 0x28 | `0x25C4A`, `0x25D9E`, `0x25E5E` | present at shifted addresses |

The structure (value, counter, base, readiness read, bound) repeats, but the
counter lives at a different address and the surrounding blocks differ, so
the two builds are **not** declared identical.

## 8. Pseudo-code with provenance

```c
void unknown_init(void)                       /* 0x25F90, L3 */
{
    volatile uint16_t *counter = (uint16_t *)0x0000937C;   /* 0x25F92 */
    *counter = 1;                                          /* 0x25F98 */

    do {
        unknown_fill(0x1001);                              /* 0x25F9A, 0x25F9E */
    } while (*counter < 0x200);                            /* 0x25FA2..0x25FA8 */
    /* 511 words at 0x01000002 .. 0x010003FE, L4 */

    unknown_two_registers();                               /* 0x25FAA */

    while (*((volatile uint16_t *)0x000F6002) != 1)        /* 0x25FAE..0x25FB4 */
        ;                                                  /* no timeout */
}

void unknown_fill(uint16_t value)             /* 0x25BA, L2 */
{
    volatile uint16_t *counter = (uint16_t *)0x0000937C;
    uint16_t index = *counter;                             /* 0x25C2 */
    ((volatile uint16_t *)0x01000000)[index] = value;      /* 0x25D0 */
    *counter = index + 1;                                  /* 0x25D4 */
}

void unknown_two_registers(void)              /* 0x2558..0x25B8, L3 */
{
    *((volatile uint16_t *)0x000F6400) = 0;                /* 0x255E */
    *((volatile uint16_t *)0x000F6402) = 0x00F0;           /* 0x2566 */
    unknown_3C8C(2, 2);                                    /* 0x2570 */
    unknown_24F8(/* r2 = high byte of the result */);      /* 0x257E */
    /* 16-bit accesses: the operand is `0x0:s(r1,r0)` and the instructions
       are `storw`/`loadw`.  The 32-bit value is only the ADDRESS, which the
       firmware loads into the register pair (r1,r0) with `movd $0xff6006:l`;
       the bus cycles themselves are 16 bits wide.                        */
    *((volatile uint16_t *)0x00FF6006) = 0x0080;           /* 0x2588..0x258C */
    *((volatile uint16_t *)0x00FF5406) &= 0xF0FF;          /* 0x2596..0x25A2 */
    *((volatile uint16_t *)0x000F5402) = 0x0400;           /* 0x25AC..0x25B0 */
    *((volatile uint16_t *)0x00FF6006) = 0x0000;           /* 0x25B4 */
}
```

## 9. What remains unknown

| Item | Level reached |
|---|---|
| meaning of `0x01000000`, of `0x1001`, of `0x937C` | L2 only |
| what events set `0x000F6002` to 1 | L2 only |
| what bit 7 of `0xFF6006` triggers | L2 only |
| whether `0xFFFF` written to `0x000F5402` at `0x3A28` is a reset value | L2 only |
| is this PCM initialisation | **not established** |
