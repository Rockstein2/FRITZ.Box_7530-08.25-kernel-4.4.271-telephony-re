# E3.2 history — CR16 addressing and the `0x000Fxxxx` artifact

> **Status: historical analysis, offline.**
> Current facts: `../fon-known-facts.md`.
> Current conclusion: `../fon-e32-summary.md`.
> No hardware evidence; K1/K2 remain NO-GO.

## 1. The question

E3 saw firmware accesses printed as `0x000F6006`, `0x000F5402`,
`0x000F6002`, `0x000F6400`, `0x000F4858` and separate `0x00FFxxxx` accesses.
The old analyzer treated the first group as zero-extended 20-bit effective
addresses and the second as 24-bit addresses, so they appeared to be different
spaces.  Q57 asked whether they really were.

## 2. Encoding

The 4-byte `abs20` form stores the address in bits spread over the first
halfword and the following word:

```text
encoded = ((b0 & 0x0F) << 16) | b2 | (b3 << 8)
```

Examples from `normal`:

| Site | Bytes | Printed operand | Encoded |
|---|---|---|---|
| `0x1348` | `2f c9 06 60` | `0xf6006:m` | `0xF6006` |
| `0x25FAE` | `0f 89 02 60` | `0xf6002:m` | `0xF6002` |
| `0x1934` | `0f c9 02 54` | `0xf5402:m` | `0xF5402` |
| `0x1442` | `ff 77 58 48` | `0xf4858:m` | `0xF4858` |

The 6-byte `abs24` form is a different instruction; its 24-bit field is
decoded by the formula in `fon-dialog-cr16-addressing.md`.  The high
`0x00FF6006` path is not an abs24 instruction: it is a 24-bit literal loaded
by `movd` into `(r1,r0)`, followed by a pair-based store/load.

## 3. The expansion rule

Two independent offline implementations implement the same threshold:

### QEMU CR16C target

`/tmp/opencode/qemu/target/cr16c/translate.c`:

```c
static uint32_t reloc_abs20(DisasContext *ctx, uint32_t addr) {
    if (addr > 0xEFFFF) {
        addr |= 0xF00000;
    }
    return addr;
}
```

The field is used as `%addr_abs20` for `LOAD_abs`, `STOR_abs`, bit
instructions and their indexed forms.  Thus:

| Encoded | Effective |
|---|---|
| `0xEFFFF` | `0x000EFFFF` |
| `0xF0000` | `0x00FF0000` |
| `0xF6006` | `0x00FF6006` |
| `0xF5402` | `0x00FF5402` |
| `0xFFFFF` | `0x00FFFFFF` |

### binutils GAS

`gas/config/tc-cr16.c`:

```c
if (flags & OP_ABS20) {
    if (value > 0xEFFFF)
        return OP_OUT_OF_RANGE;
}
```

and `adjust_if_needed()`:

```c
if ((instruction->operands[0].op_type == abs24)
    && (insn->arg[0].constant > 0xF00000)) {
    insn->arg[0].constant &= 0xFFFFF;
    instruction--;   /* select abs20 */
}
```

The range check reserves `0xF0000…0xFFFFF` for the sign-extended/short form;
the adjustment deliberately rewrites a high 24-bit value to the low 20-bit
field and selects abs20.  This only makes sense if abs20 expands high fields
back to `0xFFxxxx`.

### Synthetic assembler check

A binutils-2.44 CR16 assembler was built locally for format checks only:

```text
loadw 0xf6006,r0        -> 12 00 00 ff 06 60   abs24
storw r2,0xf6006        -> 13 00 20 ff 06 60   abs24
loadw 0xff6006,r0       -> 0f 89 06 60         abs20 (encoded 0xF6006)
movd  $0xff6006,(r1,r0) -> 70 00 ff 00 06 60   24-bit literal
storw r2,0(r1,r0)       -> 20 d0               pair + disp 0
```

The load assembler chooses the short form for a value that only makes sense
as `0x00FF6006` after expansion.  The store side is asymmetric and keeps
abs24; this is an assembler behavior, not a reason to reinterpret firmware
bytes.  All firmware conclusions in this project use raw bytes and the
disassembler oracle.

## 4. The old analyzer

Before E3.2, `cr16_peripheral_xrefs.abs20_address()` returned the encoded
20-bit field only.  That made `0x000F6006` look like a real effective address
and created the apparent conflict.  E3.2 changed:

```text
abs20_encoded_address(raw)  -> 0xF6006
reloc_abs20(value)          -> 0x00FF6006
abs20_address(raw)          -> 0x00FF6006
```

Reports keep both values:

- `encoded_address`: the field printed by objdump;
- `architectural_effective_address`: after `reloc_abs20`;
- `zero_extended_alternative`: the old analyzer value, retained for
  provenance and audit.

## 5. Consequences

| Old observation | Corrected interpretation |
|---|---|
| `0x000F6006` read/write | encoded `0xF6006`, effective `0x00FF6006` |
| `0x000F5402` acknowledgement | encoded `0xF5402`, effective `0x00FF5402` |
| `0x000F6002` poll | encoded `0xF6002`, effective `0x00FF6002` |
| `0x000F6400/6402` bring-up | effective `0x00FF6400/6402` |
| `0x000F4858` RMW | effective `0x00FF4858` |
| 12 low/high pairs | low form is the encoded field; no second address |
| SC14480 low FLASH/ROM | SC14480 map remains valid for SC14480; it does not describe the encoded operand |

The final statement is deliberately limited: this proves the **CR16
effective address**, not the SC14448 physical register identity.  The latter
still relies on SC14480 analogies until an SC14448 map or bus observation
exists.

## 6. Evidence levels

| Statement | Level |
|---|---|
| abs20 field is 20 bits | L1/L2, raw bytes + objdump |
| `0xF6006` is encoded by the firmware | L1, `2f c9 06 60` |
| `reloc_abs20` expands it to `0x00FF6006` | L2, two implementations |
| SC14448 uses the same core rule | L2/L4, CR16Cplus family assumption |
| SC14448 peripheral register is DIP_CTRL | **CANDIDATE**, related-device map |
| physical bus address observed | **not available (L5)** |
