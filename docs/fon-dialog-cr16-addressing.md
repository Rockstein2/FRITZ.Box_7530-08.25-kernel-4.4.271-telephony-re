# CR16 addressing: what the core guarantees, and what it does not

Status: **offline analysis.**  Evidence levels: **L1** bytes, **L2** decode,
**L4** semantics under the stated ISA assumptions, **L5** hardware.  No L5
statement appears in this file.

The purpose is to separate three different questions that are easy to
confuse:

1. what the **CR16A core** guarantees about addresses (documented);
2. what the **SC14448** exposes as memory (a SoC property, not a core
   property — **no document available offline**);
3. what this **firmware** actually addresses (observable in the bytes).

---

## 1. CR16A: 18-bit addresses

The CR16A Programmer's Reference Manual (`/tmp/opencode/cr16a.txt`), §2.4
"Memory Organization":

> The CR16A implements 18-bit addresses.  This allows the CPU to access up
> to 256 Kbytes of data, and 128 Kbytes of program memory.  The memory is a
> uniform linear address space.  Memory locations are numbered sequentially
> starting at 0 and ending at 2^18−1.

| Property | CR16A value | Source |
|---|---|---|
| data address width | **18 bits** (`0 … 0x3FFFF`) | manual §2.4 |
| program address | even addresses in `0 … 0x1FFFE` | manual §2.3.3 |
| PC | 18 bits, bit 0 and bit 17 always 0 | manual §2.3.3 |
| byte order | little endian | manual §2.4.1 |
| word alignment | none required for data | manual §2.4.1 |

**Consequence for this firmware.**  Every address under study is larger
than `0x3FFFF`:

```text
0x000F6006  = 1 007 622
0x00FF6006  = 16 736 262
```

so the core is **not** CR16A.  The image demonstrates this independently of
any document: it contains `abs24` operands (`R_CR16_ABS24`,
`bfd/elf32-cr16.c`), which CR16A does not have.

## 2. CR16C: what is established and what is not

| Question | Status | Basis |
|---|---|---|
| PC width | **24 bits** is the value quoted for CR16C in third-party descriptions of comparable cores (e.g. the CP3UB26 family).  Not verified against a CR16C manual: none was readable offline | L2, secondary source |
| data address width | **not established offline**.  The assembler accepts a 24-bit `abs24` field, which bounds an *immediate* operand at `0 … 0xFFFFFF`, not the bus width | L2 |
| relocation limit | `R_CR16_ABS24` refuses values above `0xFFFFFF` (`bfd_reloc_overflow`) | L1 (bfd source) |
| relocation limit, `abs20` | `R_CR16_ABS20` refuses values above `0xFFFFF` | L1 (bfd source) |
| binutils' idea of the address width | 32 bits (`bfd/cpu-cr16.c`: `32, /* Bits in an address. */`) — a BFD field, **not** a core property | L1 |
| `INTBASE`, `CFG`, `DBS`, `ISP`, `USP` | present as processor registers in `cr16-opc.c`, with 16-bit (`intbasel`/`intbaseh`) and 32-bit (`intbase`) forms | L1 |
| any address masking, windowing or translation done by the core | **none documented** in the CR16A manual; the CR16C behaviour is unverified | — |

**Do not infer the data bus width from the PC width.**  They are different
things and no offline source ties them for this part.

## 3. How the two forms under study encode their address

| Form | Bytes | Field | Bits in the instruction | Verified against |
|---|---|---|---|---|
| `storw r,<abs>:m` (4 bytes) | `2f c9 06 60` | `abs20` | `((b0 & 0x0F) << 16) \| b2 \| (b3 << 8)` = 20 bits | assembler round trip; 258 memory instructions use it in `normal`, 186 in `p2test` |
| `<abs>:l` (6 bytes) | `13 00 20 ff 06 60` | `abs24` | 24 bits over the three halfwords | assembler round trip; 375 memory instructions use it in `normal`, 427 in `p2test` |
| `movd $imm:l,(rp)` | `70 00 ff 00 06 60` | 24-bit immediate | the pair receives a **value**, not an address | assembler round trip |

### `0x000F6006` (direct)

```text
0x1348  storw r2,0xf6006:m       2f c9 06 60
0x145c  storw r0,0xf6006:m       0f c9 06 60
0x2602c loadw 0xf6006:m,r0       0f 89 06 60
0x28cde loadw 0xf6006:m,r0       0f 89 06 60
```

The operand is a **4-byte `abs20`**: bits 0–19 of the address are in the
instruction, bits 20–23 are implicitly zero.  `0xF6006` fits in 20 bits, so
the encoding is exact and the bus sees `0x000F6006` (assuming no
translation, which is the open question).

### `0x00FF6006` (indirect)

```text
0x2582  movd  $0xff6006:l,(r1,r0)   70 00 ff 00 06 60
0x258c  storw r2,0x0:s(r1,r0)       20 d0
0x25aa  loadw 0x0:s(r1,r0),r2       20 90
0x25b4  storw $0x0:s,0x0:s(r1,r0)   00 c2
```

Here `0x00FF6006` is **data**, not an address field: the 24-bit constant is
loaded into `(r1,r0)`, and the memory instruction has displacement 0.  The
address on the bus is whatever `(r1,r0)` holds, i.e. the immediate itself.

**Nothing in the decoder or in the relocation logic masks, shifts or remaps
either value.**  The two numbers reach the core as written.

## 4. What the assembler shows

| Source | Encoding produced | Note |
|---|---|---|
| `storw r2,0xf6006:m` | `13 00 20 ff 06 60` | the assembler rewrites `:m` to the 6-byte `abs24` form, because `0xF6006` does not fit a 20-bit field in its model |
| `storw r2,0xf6006:l` | same 6-byte form | |
| `movd $0xff6006:l,(r1,r0)` | `70 00 ff 00 06 60` | identical to the firmware |
| `movd $0x20000:l,(r1,r0)` | `02 05 00 00` (`:m` form) | the assembler refuses `:l` for `movd`; the emission is `imm:m` |

**Important negative result.**  For `storw r2,0xf6006:m` the assembler
produces a 6-byte `abs24` encoding, but the firmware uses a 4-byte `abs20`
one (`2f c9 06 60`).  The two encodings carry the **same numeric address**;
they differ only in how many bits are present.  This means the assembler
and the firmware disagree about which form a `:m` operand should take, and
the firmware is the authority for the firmware.  It does **not** mean the
address is different.

The assembler therefore confirms the *format* of both encodings.  It says
nothing about how the SC14448 decodes the address on its bus.

## 5. What no offline source establishes

| Claim | Why it is missing |
|---|---|
| SC14448 has a 24-bit or a 32-bit peripheral address space | no SC14448 (or Dialog/Renesas CR16C) memory map offline |
| the SC14448 ignores address bits 20–23 for peripheral decode | no decoder documentation |
| some window maps `0x000Fxxxx` and `0x00FFxxxx` together | no system-controller documentation |
| `CFG` bits control address decoding | `CFG` is written once at `0x15D2` (`0x1054` in `p2test`) with bit 8 set, and its bit layout is **not** documented offline |

These are exactly the questions that `fon-dialog-address-alias-hypotheses.md`
keeps open.
