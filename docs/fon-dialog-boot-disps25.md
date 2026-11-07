# The six-byte `disps25` branch at `0x10284`

Status: **offline analysis.**  **Result: UNKNOWN, with a specific reason and
a strong alternative reading.**

---

## 1. The instruction, and whether it is an instruction at all

```text
0x10280  lpr   r0, cfg         14 00 80 00     (4 bytes, assembler-verified)
0x10284  br    *-0x8:l         10 00 ef 0e 85 fd (6 bytes)
0x1028A  movb  $0x15:l, r2     b2 58 15 00     (4 bytes)
```

**Boundaries are confirmed.**  `lpr r0,cfg` assembles to exactly the four
bytes at `0x10280` with the same operand encoding, so `0x10284` is the next
instruction, not the middle of the previous one.  The image ends at
`0x102E9`, so the six bytes are inside the loaded block.

`0x10284` is reachable from `0x10080` by fall-through after
`0x10280 lpr r0,cfg`, and the block that starts there continues into the
error path at `0x1028A`.

## 2. The encoding, from the toolchain sources

`cr16-opc.c`:

```c
/* opc4 c4 disps25 */
{NAME, 3, (OPC<<4), 16, BRANCH_INS | RELAXABLE, {{cc,4}, {disps25,16}}}
```

`bfd/elf32-cr16.c` `R_CR16_DISP24` (the relocation this form uses):

```c
Rvalue = (((Rvalue >> 20) & 0xf) | (((Rvalue >> 16) & 0xf) << 8)
          | (bfd_get_16 (input_bfd, hit_data)))
        | (((Rvalue & 0xfffe) | ((Rvalue >> 24) & 0x1)) << 16);
```

with `dst_mask = 0x1ffffff`, i.e. a **25-bit** field.

Applying that layout to `0x10284` bytes `10 00 | ef 0e | 85 fd`:

```text
word@2 = 0x0EEF   word@4 = 0xFD85
lo   = 0x0EEF & 0x0F        = 0xF      (bits 20-23)
mid  = (0x0EEF >> 8) & 0x0F = 0xE      (bits 16-19)
rest = (0x0EEF >> 16)       = 0x0000   (bits 0-15, bit 0 = sign)
word@4 should be the high half: 0xFD85, which the formula does not use
```

This gives `disp = 0xFE0000` → target `0xF90284`, far outside the image and
not an instruction.

The formula does not reproduce the one assembled example either: `gas`
emits `10 00 e0 00 00 00` for both `+0x13880` and `+0x1D4C0`, because the
bytes are emitted as a **relocation placeholder** (`R_CR16_DISP24`) and the
displacement is filled in by the linker.  No linker was available in this
environment, so **gas provides no valid fixture for this form**.

## 3. How often the form occurs

| Image | six-byte branch instructions |
|---|---|
| first-level | **1** (`0x10284`) |
| second-level `normal` | **1** (`0x92FC`) |
| second-level `p2test` | **0** |

Both occurrences sit in data:

* `0x92E4`–`0x92FC` (normal) is a block whose instructions do not decode
  coherently (`andd $0x46380000`, `cbitb $0x3,[r12]0x8004b`, `ashud
  $0,(sp)`), i.e. data decoded as code;
* `0x10284` follows a valid `lpr r0,cfg`, so it is *not* obviously data,
  but it is the only code-like instance and it cannot be decoded.

`test.bin` from the reference project contains the same byte pattern
`10 00 e2 00` at file offset `0x1A4E`, but it is **not** a branch there: the
surrounding bytes form a table of little-endian 32-bit values
(`0x000100E2`, `0x000100E8`, `0x000100EE`, …, increasing by 6), i.e. a table
of addresses in the `0x100xx` range.  The file loads at `0x10000`, so those
are vector-handler addresses; the bytes that happen to look like a `br` are
the low halfword of a table entry.

This is a useful negative control: the pattern `10 XX XX XX` is not by
itself a `disps25` branch, and a disassembler that treats it as one will
produce a bogus target exactly as `objdump` does here (`*-0x201a4e`).

**There is therefore no working CR16C `disps25` example anywhere in the
material available offline.**  Any formula adopted for it would be fitted to
a single undecodable site.

## 4. What the instruction would have to mean in the flow

The bytes sit exactly where the loader, after setting `CFG` bit 8, would
hand over.  The surrounding structure:

```text
0x10254  handshake with 0xf4836 / 0xf4838 / 0xf4900
0x10270  cbitw $0,0xf4838
0x10274  storw $0,0xf4900
0x10278  spr cfg,r0 / orw $0x100 / lpr r0,cfg     <- bit 8 set
0x10284  10 00 ef 0e 85 fd                       <- target unresolved
0x1028A  movb $0x15,r2 / send / send r3          <- NAK + reason
```

So the semantic reading — "jump out of the loader after the upload
completed" — is consistent with the position, but the *target* is not
recoverable from the bytes with any rule this analysis could validate.

## 5. What would settle it

| Missing thing | Why it decides the question |
|---|---|
| a CR16C/Dialog branch encoding table for `disps25` | the field layout cannot be inferred from one undecodable sample |
| a linked binary containing a `disps25` branch with a known source label | it would give the displacement-to-bytes mapping directly |
| the ROM loader or the loader's caller | it may encode the entry address instead of the loader computing it |
| an address trace of the hand-off | shows the fetched PC without needing the encoding |

Until one of those exists, the target of `0x10284` is **UNKNOWN**, and
`cr16_cfg.py` is deliberately **not** changed: wiring in a formula fitted to
one sample would replace one unknown with a wrong answer.
