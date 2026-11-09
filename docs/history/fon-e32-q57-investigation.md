# E3.2 history — Q57 investigation

> **Status: historical analysis, offline.**
> No router, UART, MMIO, DMA or bus trace.  K1/K2 remain NO-GO.

## 1. Starting point

Q57: do `0x000Fxxxx` and `0x00FFxxxx` map to different hardware, or is there
an address decode that aliases them?

The old evidence was:

- 12 pairs with equal low 20 bits in both firmware images;
- `0x00FF6006` is a 24-bit `movd` literal followed by pair accesses;
- `0x000F6006` is a 4-byte abs20 operand;
- the SC14480 map places `0x000F0000` in program FLASH/ROM and
  `0x00FF0000` in peripherals;
- no SC14448 memory map or bus trace.

## 2. What changed

The abs20 encoding was already known.  E3.2 asked what the **core** does with
a 20-bit field above `0xEFFFF`; the old analyzer assumed zero extension.

Two independent implementations implement expansion:

| Implementation | Rule |
|---|---|
| QEMU CR16C `target/cr16c/translate.c` (CompactCall/qemu-cr16 `4f9e07e0ffdc4d16026e7d66f5a270b84aa12e77`) | `if (addr > 0xEFFFF) addr \|= 0xF00000` |
| binutils GAS `tc-cr16.c` | `OP_ABS20` caps at `0xEFFFF`; `adjust_if_needed` masks high abs24 values to 20 bits and selects abs20 |

Consequences:

```text
encoded 0xF6006 -> effective 0x00FF6006
encoded 0xF5402 -> effective 0x00FF5402
encoded 0xF6002 -> effective 0x00FF6002
encoded 0xF6400 -> effective 0x00FF6400
encoded 0xF6402 -> effective 0x00FF6402
encoded 0xF4858 -> effective 0x00FF4858
```

The firmware's low-looking `0x000Fxxxx` values are the **printed encoded
fields**, not effective addresses.  The old tool zero-extended the field and
was wrong for this range.

## 3. Hypothesis table

| Hypothesis | Supporting facts | Contradictions | Status |
|---|---|---|---|
| Address truncation | old analyzer printed only 20 bits | the core expands high fields; the field is not the final address | **REFUTED as final model** |
| Zero extension | simple reading of the 20-bit field | GAS `OP_ABS20` range, `adjust_if_needed`, QEMU `reloc_abs20` | **REFUTED for 0xF0000–0xFFFFF** |
| Sign extension / `RELOC_ABS20` | both QEMU and GAS implement the same threshold; all 12 pairs match exactly | no vendor CR16Cplus core manual in the offline set | **PROVEN_BY_ISA** (implementation evidence) |
| Hardware alias/window | the 12 pairs looked like a window | not needed once abs20 is expanded; no window register | **NOT REQUIRED** |
| Different address spaces | SC14480 map separates low FLASH and high peripherals | SC14480 is a different device and describes decoded addresses, not the encoded field | **NOT SUPPORTED for SC14448** |
| Analyzer decoding error | old reports used zero-extended addresses | raw bytes and oracle disassembly agree on the form | **PROVEN for the extension model** |
| Chip-specific peripheral map | `0x00FF6006` etc. still need SC14448 meanings | no SC14448 map | **UNKNOWN / CANDIDATE** |

## 4. Final answer

**Q57 address-space part: resolved.**  There are not two effective addresses.
`0x000F6006` is an encoded abs20 field that expands to `0x00FF6006`; the
firmware does not access a separate effective `0x000F6006` register through
that instruction.

**Physical register identity: still CANDIDATE.**  The SC14480 map gives
`0x00FF6006` = `DIP_CTRL_REG`, `0x00FF5402` = `RESET_INT_PENDING_REG`,
`0x00FF6002` = `DIP_PC_REG`, and `0x00FF6400/6402` = BMC control.  Those are
related-device meanings, not SC14448 proof.

The remaining blocker is therefore precise: an SC14448 memory map or a
read-only bus observation of one `0x00FFxxxx` access.  Neither requires
changing the address theory.

## 5. What would falsify this

- a CR16Cplus vendor manual stating that abs20 is always zero-extended;
- a firmware or loader path that demonstrates a distinct effective
  `0x000F6006` access not attributable to an abs20 field;
- a bus observation showing two different physical targets for the two
  numeric forms.

Until then, the project uses `0x00FFxxxx` as the canonical effective address
and keeps `0x000Fxxxx` only as `encoded_address`.
