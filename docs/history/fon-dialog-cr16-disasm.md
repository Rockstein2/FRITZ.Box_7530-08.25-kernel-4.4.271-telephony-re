# SC14448 firmware: real CR16 disassembly of the PCM path

> **Status: static disassembly with a working CR16 toolchain.**
> No firmware was executed and no hardware was touched.  This document
> supersedes the earlier byte-level scan for the PCM question.

---

## 1. Toolchain

`binutils-multiarch` from Ubuntu does **not** include CR16.  A CR16-capable
`objdump` was built locally from the binutils source already present in the
OpenWrt download cache:

```sh
tar xJf dl/binutils-2.44.tar.xz
./configure --target=cr16-elf --prefix=/tmp/opencode/cr16/inst \
            --disable-nls --disable-werror --disable-gdb --disable-sim \
            --disable-ld --disable-gas
make -j all-binutils
```

Nothing was installed into the system.  Validation: the known-good snippet

```text
2582: 70 00 ff 00   movd $0xff6006:l,(r1,r0)
2586: 06 60
2588: b2 5a 80 00   movw $0x80:m,r2
258c: 20 d0         storw r2,0x0:s(r1,r0)
```

is reproduced exactly, so the disassembler is trustworthy for this target.

---

## 2. The function that writes `0xFF6006`

It starts at **`0x2558`** (the earlier report treated `0x2582` as the entry,
which was wrong).

```text
2558  push  RA
255a  addd  $0xfffe:m,(sp)          ; 2-byte stack frame
255e  storw $0x0:s,0xf6400:m        ; (1)
2562  movw  $0xf0:m,r0
2566  storw r0,0xf6402:m            ; (2)
256a  movd  (sp),(r5,r4)            ; base from the stack
256c  movb  $0x2:s,r3
256e  movb  $0x2:s,r2
2570  bal   (ra),<far function>     ; (3) call into another block
2574  loadw 0x0:s(sp),r0
2576  movb  r0,r3
2578  loadw 0x0:s(sp),r0
257a  lshw  $-8:s,r0
257c  movb  r0,r2
257e  bal   (ra),<far function>     ; (4) call into another block
2582  movd  $0xff6006:l,(r1,r0)     ; PCM / DMA register pointer
2588  movw  $0x80:m,r2
258c  storw r2,0x0:s(r1,r0)         ; [0xff6006] = 0x80     <-- the write
258e  sprd  psr,(r3,r2)             ; save PSR
2592  di                            ; interrupts off
2596  movd  $0xff5406:l,(r4,r3)     ; interrupt controller register
259c  loadw 0x0:s(r4,r3),r5
259e  andw  $0xf0ff:m,r5            ; clear bits 11..8
25a2  storw r5,0x0:s(r4,r3)
25a4  movzw r2,(r3,r2)
25a6  lprd  (r3,r2),psr             ; restore PSR  <-- interrupts back on
25aa  loadw 0x0:s(r1,r0),r2         ; (5) read back [0xff6006]
25ac  movw  $0x400:m,r2             ; value overwritten immediately
25b0  storw r2,0xf5402:m            ; (6) interrupt controller
25b4  storw $0x0:s,0x0:s(r1,r0)     ; (7) [0xff6006] = 0      <-- cleared
25b6  addd  $0x2:s,(sp)
25b8  popret RA
```

### 2.1 What this actually is

The write at `0x258c` is **not** a persistent configuration.  The same
function clears the register again nine instructions later:

```text
258c  [0xff6006] = 0x80      ; set
...
25b4  [0xff6006] = 0x00      ; clear
```

So `0xFF6006` is a **pulse/trigger register**.  Writing `0x80` requests
something; clearing it ends the request.  Bit 7 (`0x80`) is the only bit set,
and the surrounding instructions save/restore PSR and touch the interrupt
controller, which makes this a short critical-section toggle rather than a
PCM format setup.

This corrects the earlier conclusion twice over:

| Earlier claim | Reality |
|---|---|
| "exactly one PCM register access in the image" | **wrong** — one `movd` immediate, but that function does three accesses (write, read back, clear) and there is a second access via the stack frame at `0x256a` |
| "writes `0x80` to configure PCM" | it **pulses** `0x80` and clears it in the same function |

### 2.2 What it tells us about the PCM block

`0xFF6006` behaves like a **request/gate**, not a divider or a mode register.
Nothing in the function carries a sample rate, word size or master/slave bit.
That is consistent with the SC14448 taking its PCM format from the running
application, or with the format being fixed in hardware.

---

## 3. Data structure accessed through the stack

`0x256a` loads a pointer from the stack into `(r5,r4)`, and later
`loadw 0x0:s(sp),r0` reads the caller's first argument, then shifts it by 8
and passes both bytes as `r3`/`r2` into two calls at `0x2570` and `0x257e`.

Those two calls target addresses outside this block (`*+0x3c8c` and
`*-0x24f8` relative encodings), i.e. they cross into other firmware regions.
Following them needs a linker map, which the image does not contain.
**Not analysed.**

---

## 4. Callers

A whole-image scan finds **no direct `bal`/`jal` to `0x2558`**.  The block is
reached some other way: through a function-pointer table, an indirect call,
or a vector.  `0x2558` sits inside the block that starts at `0x24f8`, whose
first instructions do a `cmpw`/`beq` dispatch on `r2`:

```text
24f8  cmpb  $0x0:s,r2
24fa  beq   *+0x2556:s
```

so `0x2558` is one arm of a **dispatcher keyed by a small integer**.
Determining which key reaches it requires finding the table that supplies
`r2`, which is again outside this block.

Honest status: **the caller path is not yet recovered.**

---

## 5. What is still needed

| Task | Why it is not done |
|---|---|
| find the dispatch table that calls `0x2558` | needs data-flow across blocks; the image has no symbols |
| decode the two far calls at `0x2570`/`0x257e` | targets lie in other blocks; relative encodings do not resolve without the map |
| prove whether `0xFF600E` is touched | only one immediate was found; indirect access cannot be excluded |
| find a slot-5 / FON handler | not found yet; does not mean absent |

---

## 6. Confidence

| Claim | Confidence | Basis |
|---|---|---|
| `0xFF6006` is written `0x80` then cleared to `0` | **high** | disassembly of one contiguous function |
| it is a trigger, not a format register | **high** | set-then-clear within 9 instructions, no format fields |
| `0xFF6006` is the only PCM *immediate* | medium | indirect access cannot be excluded |
| the function is reachable via a dispatch arm | high | `cmpb`/`beq` at the block entry |
| caller chain | **unknown** | no table found yet |
