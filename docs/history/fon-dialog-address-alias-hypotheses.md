# SC14448: hypotheses about `0x000Fxxxx` ↔ `0x00FFxxxx`

> **Status: historical analysis.**
> This document records the reasoning and evidence as of the date it was
> written.  Some of its `UNKNOWN` / `UNVERIFIED` markers have since been
> answered.
> - Current confirmed facts: `../fon-known-facts.md`
> - Current open questions: `../fon-open-questions.md`
> - This file is kept for the reasoning trail, not as a status report.

Status: **offline analysis.**  L1 bytes, L2 decode, L3 control flow,
L4 semantics under the stated ISA assumptions.  **No L5 hardware evidence
exists for anything in this file.**

The question: do `0x000F6006` and `0x00FF6006` name the same physical
register on the SC14448?

**Answer: UNKNOWN.**  Neither aliasing nor distinctness can be proven from
the material available offline.

**Update (EXTREF-1).**  An external CR16C implementation
(TobleMiner/dialog-cr16c-uart-boot, commit `3d041a68`, SC14441) uses the
*low 20 bits* of the same addresses with the **same bit layout**: UART RI =
bit 6, TI = bit 5, baud field bits 2–4, watchdog kicked with `0xFF`.  Our
first-level image matches every one of those.  That upgrades the evidence
from "the numbers share low bits" to `FUNCTIONAL_REGISTER_MATCH`, but the
physical question is unchanged: see
`fon-dialog-external-register-map.md`.  This document states exactly what is
established, what each hypothesis would require, and what is missing.

---

## 1. What is established

| Fact | Level | Source |
|---|---|---|
| the two numbers differ by `0x00F00000` | L1 | arithmetic |
| they agree on bits 0–19 (`0xF6006`) | L1 | arithmetic |
| `0x000F6006` is written in the image as a 4-byte `abs20` operand with the address bits inside the instruction | L1/L2 | `2f c9 06 60` at `0x1348` |
| `0x00FF6006` reaches the core as a 24-bit constant loaded into a register pair | L1/L2 | `70 00 ff 00 06 60` at `0x2582` |
| the decoder applies no mask, shift or remap to either value | L2 | `cr16-dis.c`, `elf32-cr16.c`; assembly round trip |
| the CR16A core has 18-bit addresses, so this is not a CR16A | L2 | CR16A manual §2.4 (addresses above `0x3FFFF` occur) |
| 12 address pairs in both images agree on the low 20 bits | L2 | `tools/reports/cr16-address-alias.json` |
| the pairing set is **identical** in `normal` and `p2test` | L2 | same report, `cross_image` |
| `CFG` bit 8 is cleared by the first-level image and set by it and by the second-level image | L2 | see `fon-dialog-cr16-system-registers.md` §5 |
| no SC14448 memory map, decoder description or system-controller document is available offline | — | — |

## 2. Candidate pairs

Produced by `tools/cr16_address_alias.py`.  Every pair differs by exactly
`0x00F00000`; there is no other difference in the images, so the "mask"
question reduces to whether bits 20–23 are significant.

Every pair below is `LOW_BITS_MATCH`; the "pattern" column only says whether
the two addresses happen to have the same set of operations, which is not
evidence (see above).

| low 20 bits | A | B | A access | B access | pattern |
|---|---|---|---|---|---|
| `0xF4000` | `0x000F4000` | `0x00FF4000` | RMW 16 | READ/WRITE 16 | **no** |
| `0xF4004` | `0x000F4004` | `0x00FF4004` | READ/WRITE 16 | READ/WRITE 16 | yes |
| `0xF4858` | `0x000F4858` | `0x00FF4858` | RMW 16 | READ/WRITE 16 | **no** |
| `0xF4C00` | `0x000F4C00` | `0x00FF4C00` | WRITE 16 | WRITE 8 | yes |
| `0xF5000` | `0x000F5000` | `0x00FF5000` | WRITE 16 | WRITE 8 | yes |
| `0xF5404` | `0x000F5404` | `0x00FF5404` | WRITE 16 | READ/WRITE 16 | **no** |
| `0xF5406` | `0x000F5406` | `0x00FF5406` | WRITE 16 | READ/WRITE 16 | **no** |
| `0xF5804` | `0x000F5804` | `0x00FF5804` | RMW 16 | READ/RMW/WRITE 16 | **no** |
| `0xF5806` | `0x000F5806` | `0x00FF5806` | RMW 16 | RMW 16 | yes |
| `0xF6006` | `0x000F6006` | `0x00FF6006` | READ/WRITE 16 | READ/WRITE 16 | yes |
| `0xF7052` | `0x000F7052` | `0x00FF7052` | READ/WRITE 16 | READ 16 | **no** |
| `0xF7056` | `0x000F7056` | `0x00FF7056` | READ 16 | READ 16 | yes |

`0x000F6002` has no partner in the `0x00FF` block.  **This is not an
argument against aliasing**: a decoder that ignores high bits aliases
whatever addresses are *used*, not every address in a range.  `0x00FF6002`
may simply never be addressed in this firmware.  The observation is recorded
because it is a fact, not because it decides anything.

Also notable: two pairs are accessed with **different widths**:

| pair | `0x000Fxxxx` | `0x00FFxxxx` |
|---|---|---|
| `0xF4C00` | `storw` 16-bit (`0x28820`) | `storb` 8-bit (`0x15AE`) |
| `0xF5000` | `storw` 16-bit (`0x1A2A`) | `storb` 8-bit (`0x15B6`) |

A single 16-bit register written by `storb` only changes 8 of its bits, so
this is not impossible; but two different widths for the same address is
what independent registers of different granularity look like.

**An access-pattern match is not evidence of anything.**  Two addresses
that both have a reader and a writer match trivially; that is what "a
register" is.  The report labels this `access_pattern_match` and keeps the
evidence level at `LOW_BITS_MATCH`.  A real dependency (`dependency_found`:
a value read at A used as the address or the written value at B) would be
needed, and this analysis does not attempt it.

## 3. The sequences are different

### `0x000F6006`

```text
0x1348  WRITE 0x0080  (guarded by [0x00D6] == 0x01027F80 and r2 == 0)
0x145C  WRITE 0x0080  (inside the 0x1388 bring-up routine)
0x2602C READ
0x28CDE READ          followed by 0x000F5402 <- 0x0400
```

### `0x00FF6006`

```text
0x258C  WRITE 0x0080
0x25AA  READ          (value discarded)
0x25B4  WRITE 0x0000  (clears the pulse)
```

Differences that a single register would have to explain:

| Observation | 0x000F6006 | 0x00FF6006 |
|---|---|---|
| is the value ever cleared? | **no** | yes (`0x25B4`) |
| does any writer verify the previous state? | yes (`0x1348` guard) | no |
| is the read result used? | at `0x28CDE` it is followed by a write | discarded |
| reachable from `0x1602` | `0x1348` yes, `0x28CDE` no | yes |
| number of writers | 2 | 2 |

If the two were one register, `0x25B4` clearing it would clear whatever
`0x145C` set, and the `0x1348` guard on a data cell would be checking a
state that a different routine had already reset.  Neither is impossible,
but both make the "one register" model more expensive than "two registers".

**Counter-argument for aliasing.** `0x0080` is written to both, which would
be a coincidence.  It is a weak one: a single bit meaning "start" is a
common encoding, and both sites are start-up code.

## 4. Hypotheses

| # | Hypothesis | Supporting | Contradicting | Status |
|---|---|---|---|---|
| A | the addresses are physically distinct | different access structure (§3); only `0x6006` pairs, `0x6002` does not; different image coverage | the shared constant `0x0080`; the identical low-bit pairing across 12 registers | **architecturally plausible, not proven** |
| B | the peripheral decoder ignores bits 20–23 | 12 address pairs agree on the low 20 bits; **and an independent SC14441 implementation uses the same low-20-bit addresses with the same bit layout for UART and the watchdog** | no document; no mechanism identified; most of the pairing is at `0x000F`/`0x00FF` which the reference never mixes in one image | **strongest hypothesis, still unproven** |
| C | a dedicated alias window maps one block onto the other | the pairing is complete and regular | no document; no evidence of a window register being programmed | **speculation** |
| D | the core or a system controller translates one form | `CFG` is written by both images, and the aliasing question is exactly about an address transformation | the core applies no translation (L2); **`CFG` bit 8 being set and cleared around boot phases does not by itself rule out a role in addressing** — a mode bit may be set when it matters and cleared when it does not | **open, not refuted** |
| E | two independent blocks that happen to share low bits | different access structure for 6 of the 12 pairs (§2); different write widths for 2 pairs | 12 coincidences in a row is unlikely if the assignment were arbitrary, but the pairing is complete and regular, which a random layout would not produce | **plausible, unproven** |

### A note on the naming

The `0x000Fxxxx` block is not "`0x0Fxxxx` split differently": the addresses
are `0x000F_xxxx`, i.e. the high half is `0x000F`, not `0x00FF`.  Writing
the pair as `0x0F4xxx` vs `0x0FFxxx` (as some notes do) suggests a
one-nibble difference; the actual difference is `0x00F00000`, i.e.
"`0x000F`" versus "`0x00FF`" in the upper 24 bits.  The numbers must be
written in full.

## 5. What each status means, and what would change it

| Level | Meaning | Who can produce it |
|---|---|---|
| architecturally possible | the core's documented behaviour does not forbid it | CR16 manual (**done**: it neither masks nor translates) |
| observed in machine code | the pattern exists in the bytes | this analysis (**done**) |
| documented for the SC14448 | a SC14448 or system-controller document states the mapping | **missing** |
| hardware-confirmed | a measurement shows both addresses reach the same state | **missing** |

## 6. What is required to move from UNKNOWN to a proven answer

In order of cost:

1. **A SC14448 memory map or the Dialog/Renesas CR16C system-controller
   description.**  This would settle the question at the document level.
   Nothing in the repository, the GPL drop or the public material found so
   far contains it.
2. **A read-only bus observation during a known access.**  Trace one
   `storw` through `0x258C` and one through `0x1348` and compare the address
   on the peripheral bus.  Requires a logic analyser on the memory bus —
   **not authorised, not performed.**
3. **A read-back experiment.**  Write a distinguishable value to
   `0x00FF6006` and read `0x000F6006`, if both are reachable from a debug
   monitor.  Requires debug access — **not authorised, not performed.**
4. **The first-level and second-level protocol.**  If the second-level
   image is relocated by the loader, the loader's map would show whether the
   `0x00FF` block is the relocated view of the `0x000F` block.  The
   first-level image is a UART loader and jumps to `0x7C`, which is empty;
   it contains no relocation of the blocks in question.

Until one of these exists, the honest answer is **UNKNOWN**, and the two
addresses must stay separate everywhere in this repository.
