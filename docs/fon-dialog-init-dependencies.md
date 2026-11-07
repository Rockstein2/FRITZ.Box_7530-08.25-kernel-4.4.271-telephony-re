# Initialisation dependencies around `0x25F90`

Status: **offline static analysis.**  Evidence levels: L1 bytes, L2 decode,
L3 control flow, L4 semantics under the stated ISA assumptions, L5 hardware —
**nothing in this document is L5**.

This document answers only one question: *in which order does the firmware
touch the peripheral registers of the `0x25F90` sequence, and what has to
have happened before?*  It deliberately does not name any register.

---

## 1. The call chain up to `0x25F90`

```text
0x1602  bal 0x39F8           (entry candidate; sets PSR 0x800 at 0x15FE)
0x39F8  ... 0x3A0C bal 0x1388   -> writes 0xF5404/6/8/A with 0 under DI
         ... 0x3A10 bal 0x131C   -> 0x11CE, then 0x12EA if bit 0 of 0x93CD
         ... 0x3A28 storw 0xFFFF,0xf5402:m
         ... 0x3A2C bal 0x25FB8
0x25FB8 bal 0x25F90          -> the sequence under study
0x25FB8 bal 0x25EA6          -> after the sequence returns
```

Two facts follow directly (L3, L4):

* the sequence runs **after** interrupts were disabled at `0x3A08` and after
  `0x000F5402` was written with `0xFFFF` at `0x3A28`;
* the sequence is followed, still in the same routine, by `0x25EA6`
  (`movd $0x1469e` into a pair, indirect `jal`, loop over `0xFF0`).

## 2. Order of the hardware writes inside the sequence

| # | Address | Instruction | Value | Guard / condition |
|---|---|---|---|---|
| 1 | `0x0000937C` | `storw $1` | 1 | none |
| 2 | `0x01000000 + 2·index` | `storw r2` | `0x1001` | 511 times, loop condition `index+1 < 0x200` |
| 3 | `0x000F6400` | `storw $0` | 0 | none |
| 4 | `0x000F6402` | `storw r0` | `0x00F0` | none |
| 5 | `0x000F6006` | `storw r2` | `0x0080` | none |
| 6 | `0x00FF5406` | `loadw`, `andw 0xF0FF`, `storw` | bits 8..11 cleared | interrupts disabled around it |
| 7 | `0x000F5402` | `storw r0` | `0x0400` | none |
| 8 | `0x000F6006` | `storw $0` | 0 | none |
| 9 | `0x000F6002` | `loadw` in a loop | polled for 1 | unbounded |

The `0x0080` write (5) and the clear (8) bracket an interrupt-mask edit (6);
`0x000F5402 <- 0x0400` (7) sits between them.  Reads of `0x000F6006`
(`0x25AA`) discard the value.

## 3. What precedes the sequence elsewhere

The same register `0x000F6006` is written by two other routines, and both
write the identical value `0x0080`:

| Site | Guard before the write |
|---|---|
| `0x1348` (`0x1330`) | reads `[0x00D6]` and compares it with `0x01027F80` (`0x133A`); writes only on equality **and** `r2 == 0` |
| `0x145C` (routine starting at `0x1388`) | clears `0xF5404/6/8/A` under DI (`0x1392`–`0x139E`), then sets bits `0xC000` in `0xFF4856` (`0x144E`), sets bit 1 of `0xF401A` (`0x1454`), then writes `0x80` |

The routine at `0x1388` is the one called from `0x3A0C`, i.e. **immediately
before** the `0x25F90` path when entered from `0x1602`.  Its sequence
(clear `0xF540x`, set `0xFF4856` bits, set `0xF401A` bit 1, write `0x80`) is
a hardware bring-up with the same `0x80` value as `0x25F90`.

## 4. What follows

| Site | Address | After the `0x80` write |
|---|---|---|
| `0x2602C` | `0x000F6006` | `loadw` (discarded), then `0x000F5402 <- 0x0400`, DI |
| `0x28CDE` | `0x000F6006` | `loadw` moved to `r2`, then `0x000F5402 <- 0x0400` |
| `0x25AA` | `0x00FF6006` | read (discarded), `0x000F5402 <- 0x0400`, clear |
| `0x25EA6` | — | after the whole `0x25F90`: indirect `jal` into `0x1469E`, loop over `0xFF0` |

`0x000F5402 <- 0x0400` appears after *every* read of `0x000F6006` and in the
`0x25F90` sequence itself.  `0x000F5402` is also written with `0xFFFF`
before the sequence and with `0x2000` / `0x0100` elsewhere.

## 5. Dependencies that are proven, and that are only plausible

| Claim | Level | Basis |
|---|---|---|
| the sequence runs with interrupts disabled when entered from `0x1602` | L3 | `0x3A08 di` … no `ei` on the path |
| `0x000F5402` is written before the sequence and again inside it | L2 | `0x3A28`, `0x25B0` |
| the `0x80` value is shared by three independent routines | L2 | `0x1348`, `0x145C`, `0x258C` |
| the `0x0080` write is a start/commit command | **not proven** | the value is reused, but nothing shows what it starts |
| `0x000F6002 == 1` means "operation finished" | **not proven** | only one reader, no writer in the image |
| `0x000F5402` selects a channel or a clock divider | **not proven** | several values, no map |

## 6. Search for a hardware manual

Checked offline, with the result for each source:

| Source | Result |
|---|---|
| GPL telephony modules in this repository | no peripheral register names; only AVM's own abstraction |
| The project's `docs/` (all files) | no `0xF6002`, `0xFF6006` or `0xFF5406` outside our own notes |
| `firmware/*.hex` (both images) | no strings, no symbol table, no address map |
| CR16A manual (public) | instruction set only; no SC14448 peripherals |
| first-level firmware / loader | not present in the repository |
| Public Dialog/Renesas SC14448 datasheet | **not available offline**; a web search found no public datasheet with a register map |

Consequence: no register in this document is given a name.
