# `0x10284` → `0x000008`: the first-level hand-off

Status: **offline analysis.**  The target is now **decoded**, not guessed.

This document replaces an earlier conclusion that said the target could not
be recovered without a linker.  That was wrong: `cr16-dis.c` already
implements the extraction, and the assembler/linker is only needed to
*produce* such an instruction, not to read one.

---

## 1. The instruction

```text
0x10280  lpr   r0, cfg      14 00 80 00      (4 bytes, assembler-verified)
0x10284  10 00 ef 0e 85 fd                   (6 bytes, disps25 form)
0x1028A  movb  $0x15, r2    b2 58 15 00      (4 bytes)
```

`0x10284` is a real instruction boundary: `lpr r0,cfg` assembles to exactly
those four bytes, and the loader reaches `0x10284` by fall-through after
setting `CFG` bit 8.

## 2. The encoding, from `cr16-dis.c`

For a branch with a 24-bit-class displacement and a three-word encoding,
`make_argument()` packs bits 16..47 and rebuilds:

```c
p = makelongparameter(allWords, 16, inst_bit_size);
constant = (((p >> 16) & 0xF) << 20) | (((p >> 24) & 0xF) << 16) | (p & 0xFFFF);
```

`print_arg()` then applies the sign and the PC base:

```c
longdisp = a->constant;
if (longdisp & 1) { sign_flag = 1; longdisp = ~longdisp + 1; }
a->constant = longdisp & ((1 << a->size) - 1);      /* size 16 or 24 */
number = memaddr + (sign_flag ? ((-a->constant) & 0xFFFFFE) : a->constant);
print(number & ((1 << 24) - 1));
```

Note two details that are easy to get wrong:

* the sign is **bit 0 of the field**, not its most significant bit;
* the magnitude is masked to `a->size`, which is **16** for `disps17` and
  **24** for `disps25` (from `cr16_optab`).  Masking to the wrong width
  shifts the target by `0x100000`.

## 3. Applying it

```text
bytes             10 00 | ef 0e | 85 fd
words             0x0010    0x0EEF    0xFD85
p = (w1<<16 | w2) 0x0EEFFD85
constant          0xFEFD85        bit 0 = 1, so the branch is negative
magnitude         0x01027B        (~constant + 1) & 0xFFFFFF
a->constant       0x01027B        magnitude, already inside the 24-bit mask
number            0x10284 + ((-0x01027B) & 0xFFFFFE)
                = 0x10284 + 0xFEFD84 = 0x1000008
target            0x1000008 & 0xFFFFFF = 0x000008
```

The addition wraps past 24 bits; the mask at the end drops the carry, which
is exactly why the printed value is the small `0x8` and not a negative
offset.  This is the same arithmetic `objdump` performs — it prints
`*-0x8`, and the `*-` only marks `sign_flag`.

The instruction therefore is `br` to **`0x000008`**.

### Validation

| Case | Bytes | Target | Source of truth |
|---|---|---|---|
| field 0, forward | `10 00 80 00 00 00` | `0x10284` (itself) | `objdump` |
| field 0, conditional | `10 00 00 00 00 00` | `0x10284` | `objdump` |
| the hand-off | `10 00 ef 0e 85 fd` | **`0x000008`** | `objdump` prints `*-0x8` |
| known data artefact | `10 00 4d 00 07 4e` | `0xD0E102` | `objdump` prints `*-0xd0e102` |

The same routine also reproduces every `disps17` case in both images: the
branch validation suite reports **0 MISMATCH** for 7 807 branches after the
change (previously the backward forms were `UNSUPPORTED`).

## 4. What is at `0x000008`

Both second-level images place their first block at `0x0`, so `0x8` is
loaded data.  Bytes:

| Image | bytes at `0x8` | decoded |
|---|---|---|
| normal | `10 00 e0 00 a2 15` | `disps25` branch, target **`0x15AA`** |
| p2test | `10 00 e0 00 1e 10` | `disps25` branch, target **`0x1026`** |

Applying the same rule:

```text
normal : 0x8 + delta  -> 0x15AA   = the system-register start-up block
p2test : 0x8 + delta  -> 0x1026   = six bytes before the start-up block
```

`0x15AA` is the block that sets `USP`, `ISP`, `CFG` and `INTBASE` and then
falls through to `0x15BC`.  In `p2test` the corresponding block starts at
`0x102C`; the branch lands on `0x1026`, which is `movb $0,r0` followed by
`storb r0,0x1F3` — the first instructions of the same routine.

**So the chain is:**

```text
first-level loader (UART)
  0x10284  br  0x000008
      |
      v
second-level 0x000008
  br  0x15AA  (normal)  /  br  0x1026  (p2test)
      |
      v
start-up: USP, ISP, CFG bit 8, INTBASE = 0x24, .bss clear
      |
      v
0x1602  ->  0x39F8  ->  ...  ->  0x25F90
```

## 5. Confidence

| Claim | Level |
|---|---|
| `0x10284` is a 6-byte `disps25` branch | L2 (boundary + encoding) |
| its target is `0x000008` | **L2, from `cr16-dis.c` and re-validated against 7 807 branches** |
| `0x000008` holds a branch to `0x15AA` / `0x1026` | L2 |
| `0x15AA` is the start-up block | L2/L3 |
| therefore the loader hands control to the second-level image | **L3: a static chain with every link decoded, but never observed on hardware** |

This closes the static question Q65.  It does **not** prove that the
FRITZ!Box actually reaches `0x10284` at run time; that still needs the
UART capture or an address trace.

## 6. What the earlier text got wrong

| Earlier claim | Correction |
|---|---|
| "the layout cannot be validated without a linker" | `cr16-dis.c` decodes it; the linker is only needed to *emit* one |
| "`objdump` prints `*-0x8`, i.e. offset −8" | the printed value is the **absolute target** `0x8`, not a displacement |
| "`0x1028A` is the continuation of the block after `0x10284`" | `0x10284` is a `br`: control goes to `0x8`, and `0x1028A` is only reachable from the error paths that branch there |
| "the `10 XX XX XX` pattern is not a branch" | correct for the reference `test.bin` table, but `0x8` here really is one: the target depends on the following bytes, which a table halfword does not |
