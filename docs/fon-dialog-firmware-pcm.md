# SC14448 firmware: what it programs, and what that means for FON

> **Correction (2026-11-07, later the same day).**
> A working CR16 disassembler showed that the function starting at
> `0x2558` **writes `0x80` and then clears the same register to `0`**, so
> `0xFF6006` is a trigger, not a configuration.  The claim below that
> "there is exactly one PCM register access" is also too strong: the scan
> only found one *immediate*, while that function performs three accesses.
> See `fon-dialog-cr16-disasm.md` for the full disassembly.  The rest of
> this document remains valid as the byte-level record.


> **Status: static analysis of the AVM firmware images.**
> No firmware was executed and no hardware was touched.  The decoder used
> here is validated against a known-good snippet, not assumed.

---

## 1. The passive TDM measurement came first

Before this analysis, all eight PCM candidate pins were sampled on the
running OpenWrt system for two seconds each:

```text
GPIO20 1 0 edges   GPIO24 1 0 edges
GPIO21 0 0 edges   GPIO25 0 0 edges
GPIO22 1 0 edges   GPIO26 1 0 edges
GPIO23 1 0 edges   GPIO27 1 0 edges
```

**No pin toggles were observed, in either pinmux group.**

**This result does NOT prove the clocks are absent.**  The sampler ran `cat`
on a sysfs file once per sample, i.e. one process per measurement, which is
in the 10-100 kHz range at best and additionally goes through the GPIO
subsystem rather than the TLMM register directly.  A fast periodic signal
can change state several times between two reads and be invisible.

What the measurement does support: no steady low-frequency oscillation and no
glitchy/floating behaviour.  Anything about 8 kHz or 1 MHz is **outside the
resolution of this method**.  A kernel-side edge counter, validated against a
known signal, is required; see `fon-tdm-clock-software-check.md`.

---

## 2. Method and decoder validation

Tool: `tools/fon_dialog_pcm_scan.py`.

The firmware addresses peripherals with `movd $imm32:l,(r1,r0)`, opcode
`70 00`.  The immediate is stored as two 16-bit words, low word first, each
little-endian.  The rule was **derived from the known-good snippet** at
offset `0x2582` in `dectfw_secondlevel_441.hex`:

```text
0x2582: 70 00 ff 00 06 60   movd $0xff6006:l,(r1,r0)
```

`ff 00` -> `0x00ff`, `06 60` -> `0x6006`, combined as `0xff6006`.  Any
decoder that does not reproduce exactly `0xff6006` for these six bytes is
wrong; two earlier attempts failed this check and were discarded.

---

## 3. What the firmware touches

`dectfw_secondlevel_441.hex`, 175 `movd` immediates, filtered to the
peripheral window:

| Address | Hits | Block |
|---|---|---|
| `0x00ff4812` | 1 | GPIO |
| `0x00ff481e` | 1 | GPIO |
| `0x00ff4836` | 1 | GPIO direction |
| `0x00ff4838` | 1 | GPIO |
| `0x00ff4856` | 2 | GPIO |
| `0x00ff4858` | 1 | GPIO |
| `0x00ff4960` | 1 | UART / data |
| `0x00ff5802` | 1 | timer / platform |
| **`0x00ff6006`** | **1** | **PCM / DMA** |
| `0x00ff7052` | 1 | radio / analog |
| `0x00ff7056` | 1 | radio / analog |

The `p2test` image shows the same set with two extra GPIO addresses
(`0xff4860`, `0xff4960`) and the same single `0xff6006`.

**One `movd` immediate targets the PCM block.**  This does **not** mean the
firmware touches PCM only once: the function that uses it reads, writes and
clears the register, and other forms of addressing were not searched.  See
the correction banner and `fon-dialog-cr16-disasm.md`.

### 3.1 The PCM block, byte by byte

```text
0x257a: 80 49 02 59 ff c0 7b ff
0x2582: 70 00 ff 00 06 60        movd $0xff6006:l,(r1,r0)
0x2588: b2 5a 80 00              movw $0x80:m,r2
0x258c: 20 d0                    storw r2,0x0:s(r1,r0)     ; [0xff6006] = 0x80
0x258e: 14 00 92 30              sprd psr,(r3,r2)
0x2592: 04 00                    di
0x2594: 00 2c 73 00
0x2598: ff 00 06 54              movd $0xff5406:l,...
0x259c: 53 90 b5 22 ff f0 53 d0
0x25a4: 22 5f
0x25a6: 14 00 92 10              sprd ...
0x25aa: 20 90 b2 5a 00 04        movw $0x400:m,r2
0x25b0: 2f c9 02 54              storw r2,0xf5402:m         ; interrupt controller
```

Verified facts:

- `0xFF6006` receives the constant **`0x80`** (`movw $0x80` then a store
  through the pointer);
- the sequence runs with interrupts disabled (`di`), so it is a critical
  section;
- immediately after, the code touches the **interrupt controller**
  (`0xFF5402`), not more PCM registers.

Not verified: what bit `0x80` means, and whether `0xFF600E` is ever used as a
register rather than appearing only as an immediate elsewhere.

### 3.2 GPIO

`0xFF4836` is the direction register and is written with `0x20` then `0xC0`
in the block at `0x12fc`.  The set/reset registers `0xFF4856`/`0xFF4858` are
each touched, plus `0xFF4812` and `0xFF481e`.

This is ordinary DECT hardware setup (handset I/O, radio control).  **No
sequence in the image looks like a SLIC line-feed or ring generator**: there
is no repeated pattern on a single GPIO with timing constants, and no
adjacent ADC reads.

---

## 4. Interpretation for the FON

| Question | Answer from the firmware |
|---|---|
| Does the chip configure PCM itself? | once, with a single `0x80` write |
| Does it need a host to program PCM? | not visible; the value is its own |
| Is there a FON-specific routine? | **no identifiable one** |
| Does firmware disable PCM under OpenWrt? | it never runs, so the question is moot |

The practical conclusion is unchanged and now better supported: **the FON
stops at the same place as everything else — the SC14448 has no firmware
running.**

---

## 5. What this does not prove

- that `0x80` means "enable" or a clock divider;
- that the analog path is driven by the DECT core rather than by a
  separate FXS block with its own registers;
- that the radio/analog addresses `0xFF7052`/`0xFF7056` are unrelated to
  the analog line — they could be the SLIC, but nothing shows it;
- anything about `0xFF600E`, which appears in the earlier report but not as
  a decoded immediate in this scan.

Those need either a CR16 disassembler (not available here without building
binutils with `--target=cr16-elf`) or targeted dynamic tracing after the
firmware runs.

---

## 6. Next step that follows from this

The firmware analysis is now **saturated**: without a disassembler, further
byte inspection yields diminishing returns.  The blocking item is not
knowledge, it is state: the chip does not run.

Order of work that follows:

1. determine the current GPIO40 (DECT reset) level — **done while writing
   this document**: GPIO40 reads `dir=in, val=0`, i.e. the pad is an input
   held low and nothing in Linux drives it.  The AVM board table declares it
   as `OUT_ACTIVE_HIGH`, so a low pad with a high-active reset would mean
   **the SC14448 is being held in reset**;
2. if the chip is held in reset, releasing it is the next active step and
   needs explicit approval;
3. only after the chip runs does the PCM format matter.
