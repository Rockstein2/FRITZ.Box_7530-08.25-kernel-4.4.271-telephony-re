# Comparing the Dialog boot loader, the AVM first-level and the TobleMiner stub

Status: **offline comparison.**  Three different things share the phrase
"UART boot".  Keeping them apart is the point of this document.

---

## 1. The three levels

| | A. Dialog ROM loader | B. AVM first-level | C. TobleMiner stub |
|---|---|---|---|
| runs from | on-chip ROM (no image available) | RAM at `0x10080` (image present) | RAM, image built by the reference |
| source | none offline | `firmware/dectfw_firstlevel_441_slow.hex` | `device/*.s`, `device/*.c` |
| protocol owner | Dialog | AVM | the stub itself |
| purpose | receive a first image | receive the second-level image | test/demo firmware |

**A is not available.**  Every statement about the ROM loader is an
inference from what B and C assume.

## 2. What each side actually implements

### B — AVM first-level (proven from disassembly)

| Step | Evidence |
|---|---|
| reads a 4-byte big-endian **address**, then a 4-byte big-endian **length**, then that many data bytes | `0x1019A`–`0x10234`, `fon-dialog-uart-boot-protocol.md` |
| stores each byte at the header address | `0x1022C` |
| XOR-accumulates a checksum | `0x10198`, `xorb r2,r11` |
| sends the checksum and waits for `0x06` | `0x10240`, `0x1024E` |
| NAK is `0x15` | `0x1028A`, `0x1028C` |
| UART status bits: RI = 6, TI = 5 | `0x102AC`, `0x102DA` |
| baud field bits 2–4 set to `0xC` → 115200 | `0x100EA`, `0x100EE` |

`u32be` lengths and addresses are **big-endian** here.

### C — TobleMiner host tool

`host/dialogtool.py` packs with `struct.pack("<BH", ...)` — **little-endian**
on the host.  Its stub `device/uart.c` speaks its own framed protocol with
`0xA5` and CRC32 (see the reference), which is *not* the ROM protocol.

So B and C use **different field endianness** and **different framing**.
They are two independent implementations, not one protocol.

### The AVM host side

`include/piglet_protocol.h` and `fon_dialog_build_image()` in this
repository build `u32be address, u32be length, data` — matching B.

## 3. Where the reference is authoritative

| Question | Reference answer | Applies to |
|---|---|---|
| handler table encoding (÷2) | `device/vectors.s` | **yes**, confirmed by our boundaries |
| `CFG` bit 8 meaning | `crt0.s`: *"Setup CPU to read exception handlers as 32 bit wide"* | **likely**, see §4 |
| UART bit layout | `device/uart.h` | **yes**, confirmed by our bit tests |
| watchdog `0xff` | `device/watchdog.h` | **yes**, same value and role |
| memory layout `RES = 0x10000`, `RAM = 0x10080` | `sc14441-uart.ld` | **candidate only** |
| `.bss` zeroing in start-up | `device/startup.c` | **yes**, matches our record |

## 4. `CFG` bit 8

Reference `crt0.s`:

```asm
spr cfg, r0
orw $0x100, r0        ; "Setup CPU to read exception handlers as 32 bit wide"
lpr r0, cfg
```

Our images:

| Image | Site | Operation |
|---|---|---|
| first-level | `0x10080`–`0x10088` | **clear** bit 8 (`andw $0xFEFF`) |
| first-level | `0x10278`–`0x10280` | **set** bit 8 (`orw $0x100`) just before a wait |
| normal | `0x15D2`–`0x15DA` | set bit 8 |
| p2test | `0x1054`–`0x105C` | set bit 8 |

All three images set bit 8 **before** programming `INTBASE`:

```text
0x15D2  spr cfg,r0 / orw $0x100 / lpr r0,cfg
0x15E6  lprd (r2,r1),intbase        ; INTBASE = 0x24
```

and the table entries **are** 32-bit values (÷2).  That is consistent with
the reference comment: with bit 8 set, the core reads 32-bit handler words.

Why the first-level **clears** it at `0x10080` is still open.  The most
economical reading is that it resets the CPU to the 16-bit table format
before doing anything else, then restores 32-bit format when it hands over.
No offline document confirms the bit, so:

**Status: strong hypothesis (L2 + external reference), not documented.**

It is **not** evidence about address aliasing.

## 5. Linker memory map

Reference `sc14441-uart.ld`:

```text
RES : 0x00010000, LENGTH 0x80
ram : 0x00010080, LENGTH 0x3F80
```

Our first-level image starts at **`0x10080`** — exactly the reference's RAM
origin.  That is a striking coincidence, and it is also the only evidence
for it: a linker script of a *different* device, and one image whose load
address happens to match.

| Claim | Status |
|---|---|
| `0x10080` is RAM on SC14441 | reference linker script |
| `0x10080` is RAM on SC14448/7530 | **UNKNOWN** |
| the first-level image runs from RAM | likely, but unproven |
| `0x10000`–`0x1007F` is a ROM window | reference only |

## 6. Summary table

| Property | A (ROM) | B (AVM first-level) | C (TobleMiner stub) |
|---|---|---|---|
| length field | unknown | `u32be` | little-endian |
| address field | unknown | `u32be` | little-endian |
| checksum | unknown | XOR, echoed, ACK `0x06` | CRC32, `0xA5` framing |
| NAK | unknown | `0x15` | reference-specific |
| start baud | unknown | field `0xC` = 115200 | settable |
| entry into payload | unknown | `0x10284` (target unresolved) | `br _c_entry` |

**Do not treat B and C as the same protocol.**  They agree on nothing except
that both are UART uploads on the same core.
