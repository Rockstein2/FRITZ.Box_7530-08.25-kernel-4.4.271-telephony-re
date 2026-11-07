# Initialisation dependencies around `0x25F90`

Status: **offline static analysis.**  Evidence levels: L1 bytes, L2 decode,
L3 control flow, L4 semantics under the stated ISA assumptions, L5 hardware —
**nothing in this document is L5**.

This document answers only one question: *in which order does the firmware
touch the peripheral registers of the `0x25F90` sequence, and what has to
have happened before?*  It deliberately does not name any register.

**Address discipline.**  `0x000Fxxxx` and `0x00FFxxxx` are different numbers.
No evidence shows that the SC14448 maps them to the same hardware register,
so they are never merged, never summed and never described as one register.

---

## 1. The call chain up to `0x25F90`

```text
0x1602  bal 0x39F8           (entry candidate; sets PSR 0x800 at 0x15FE)
0x39F8  ... 0x3A08 DI
         ... 0x3A0C bal 0x1388   -> writes 0xF5404/6/8/A and 0x000F6006
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

## 2. Order of the hardware writes

### 2.1 `0x25F90` itself

| # | Address | Instruction | Value | Guard / condition |
|---|---|---|---|---|
| 1 | `0x0000937C` | `storw $1` | 1 | none |
| 2 | `0x01000000 + 2·index` (**`SYMBOLIC`**) | `storw r2,0x0:s(r5,r4)` | `0x1001` | 511 times, loop bound proven in `fon-dialog-peripheral-init.md` |

Both stores are reached only after `movd $0x937c` / `movd $0x1000000` into a
register pair; the second also has an index added (`movzw`, `ashud $1`,
`addd`), so the scanner reports it as `0x01000000 + 2*r3`, not as a single
address.  The span `0x01000002 … 0x010003FE` is therefore an **inferred
range**, not an address the code states.

### 2.2 `0x2558` — called from the loop body of `0x25F90`

Exact instruction order (normal image; `p2test` has the same structure in the
routine starting at `0x1E0C`, with the same operations at `0x1E12`, `0x1E1A`,
`0x1E3E`…`0x1E70`):

| # | Site | Address | Operation | Value |
|---|---|---|---|---|
| 3 | `0x255E` | `0x000F6400` | `storw $0` | 0 |
| 4 | `0x2566` | `0x000F6402` | `storw r0` (`0x2562 movw $0xf0`) | `0x00F0` |
| 5 | `0x2582` | `0x00FF6006` | `ADDRESS_LOAD` (`movd $0xff6006:l,(r1,r0)`) | — |
| 6 | `0x258C` | `0x00FF6006` | `storw r2` (`0x2588 movw $0x80`) | `0x0080` |
| 7 | `0x2592` | — | `di` (PSR saved at `0x258E`) | interrupts off |
| 8 | `0x2596` | `0x00FF5406` | `ADDRESS_LOAD` | — |
| 9 | `0x259C` | `0x00FF5406` | `loadw` | read |
| 10 | `0x259E` | — | `andw $0xF0FF,r5` | `new = old & 0xF0FF` |
| 11 | `0x25A2` | `0x00FF5406` | `storw r5` | read-modify-write |
| 12 | `0x25A6` | — | `lprd (r3,r2),psr` | PSR restored |
| 13 | `0x25AA` | `0x00FF6006` | `loadw 0x0:s(r1,r0),r2` | read (discarded) |
| 14 | `0x25B0` | `0x000F5402` | `storw r2` (`0x25AC movw $0x400`) | `0x0400` |
| 15 | `0x25B4` | `0x00FF6006` | `storw $0` | `0x0000` |

The `0x0080` write (6) and the clear (15) bracket the masked write to
`0x00FF5406` (9–11); `0x000F5402 <- 0x0400` (14) sits between them.

**`0x000F6006` does not take part in this pulse.**  Every `0x6006` access in
`0x2558` is to `0x00FF6006`; the `0x000F6006` rows in section 3 are separate
writers in other routines.

### 2.3 After the sequence

| Site | Address | Instruction | Note |
|---|---|---|---|
| `0x25FAE` | `0x000F6002` | `loadw 0xf6002:m,r0` | polled until `== 1` (`0x25FB2` `cmpw $1`, `0x25FB4` `bne` back to `0x25FAE`) |

The poll is unbounded: the only exit is the value becoming `1`.

## 3. `0x000F6006` — a separate register with its own writers

| Site | Routine | Value |
|---|---|---|
| `0x1348` | `0x1330` | `0x0080`, guarded by `[0x00D6] == 0x01027F80` **and** `r2 == 0` (`0x133A`, `0x1342`) |
| `0x145C` | `0x1388` (called from `0x3A0C`) | `0x0080`, after clearing `0xF5404/6/8/A` under DI (`0x1392`–`0x139E`), setting bits `0xC000` in `0xFF4856` (`0x144E`) and bit 1 of `0xF401A` (`0x1454`) |

Readers of `0x000F6006`: `0x2602C` (value discarded) and `0x28CDE` (moved to
`r2`).  `p2test`: writers `0x0DBE`, `0x0ED2`, readers `0x267E2`, `0x27C96`.

Nothing in the code links these writers to the `0x00FF6006` pulse of
`0x2558`.  The only shared feature is the value `0x80`, which is not
evidence of the same register.

## 4. Where `0x000F5402 <- 0x0400` appears

| Site | Context |
|---|---|
| `0x25B0` | inside `0x2558`, after the `0x00FF6006` read |
| `0x26034` | after `0x2602C` reads `0x000F6006` |
| `0x28CE8` | after `0x28CDE` reads `0x000F6006` |

`0x000F5402` is also written with `0xFFFF` (`0x3A28`, before the sequence),
`0x2000` (`0x1934`, `0x28B00`) and `0x0100` (`0x289A8`).

## 5. Dependencies that are proven, and that are only plausible

| Claim | Level | Basis |
|---|---|---|
| the sequence runs with interrupts disabled when entered from `0x1602` | L3 | `0x3A08 di` … no `ei` on the path |
| `0x000F5402` is written before the sequence and again inside it | L2 | `0x3A28`, `0x25B0` |
| `0x00FF6006` receives `0x0080` then `0` inside `0x2558` | L2 | `0x258C`, `0x25B4` |
| `0x000F6006` receives `0x0080` from two other routines | L2 | `0x1348`, `0x145C` |
| `0x000F6006` and `0x00FF6006` are the same register | **not proven** | different addresses; only the shared value `0x80` |
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
