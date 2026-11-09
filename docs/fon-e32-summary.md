# FON-E3.2 summary — CR16 address-space resolution and audit fixes

## E3.2.1 hardening (offline)

The three address analyzers now share `address_operand()` in
`tools/cr16_peripheral_xrefs.py`: load source, store destination, bit-memory
operand; pair-to-pair `movd` and register-list forms are not ordinary memory
accesses. `cr16_address_spaces.py` requires both SHA256-matched images, an
executable oracle and two converged, structurally valid results before staging
and promoting its five JSON reports. Failed runs leave confirmed reports
unchanged and emit `cr16-address-spaces.incomplete.json` with a reason.
Replay now uses an empty temporary directory and checks exit status and all
five JSON files. E2 matching requires every *known* old memory-use field in
the new record; missing/changed fields invalidate the proof, while unknown old
fields are listed explicitly. The regenerated audit remains 25 → 11/3/11
(normal) and 10 → 3/2/5 (p2test); interproc remains 43/58 and 22/69
PROVEN/CANDIDATE. DIP `0x1001` is a decoded nearby literal, but its
def-use path into the store is unresolved; 1…511 and base+2×index retain
`PREVIOUSLY_RECONSTRUCTED` provenance, not independent path-sensitive proof.
Q57 remains closed only for architectural abs20 extension, not SC14448
physical register identity. Q46/Q55/Q75 remain open; K1/K2 remain NO-GO.
Address-form records remain 5735/5183. Direction-aware classification
corrects 161/130 records (mostly pair-valued `stord` into stack/indexed
destinations), including 3/5 `stord` ABS24 destinations previously labelled
as register-pair forms; the represented effective addresses at these sites
do not change. The high abs20 fields retain their canonical `0x00FFxxxx`
addresses. The report's `address_mode` is now the actual memory destination,
not the first parseable pair-valued operand.

> **Status: offline research completed; no hardware action.**
> K1/K2 remain **NO-GO**.  No router, UART, MMIO, DMA, GPIO, firmware
> execution, TDM or ringing was used.

## 1. Results at a glance

| Item | Result |
|---|---|
| E3.1 memory-use audit | now compares instruction, effective address, operation, known displacement and pair; old E2 uses re-audited |
| Missing/corrupt E2 baseline | fail-closed; non-zero exit; no report overwrite |
| Table def-use | explicitly `LOCAL_BASIC_BLOCK_ONLY`; unreachable clobber branch removed |
| Q57 address-space conflict | **resolved at the CR16 effective-address level** |
| `0x000F6006` | encoded abs20 field `0xF6006`, effective **`0x00FF6006`** |
| `0x000F5402` | encoded abs20 field `0xF5402`, effective **`0x00FF5402`** |
| `0x000F6002` | encoded abs20 field `0xF6002`, effective **`0x00FF6002`** |
| `0x000F4858` | encoded abs20 field `0xF4858`, effective **`0x00FF4858`** |
| physical SC14448 register identity | **CANDIDATE**, still based on the related-device SC14480 map |
| DIP fill payload `0x1001` | both byte orders give a branch opcode (`BR` / `BR_B0`); parameter and target remain undecoded |
| slot-5 consumer (Q75) | **still open**; no source-to-sink proof |

The important correction is that `0x000Fxxxx` was never an effective address.
It is the **printed 20-bit operand field**.  CR16Cplus expands an abs20 field
above `0xEFFFF` by setting bit 20–23 to `0xF`, so the effective address is
`0x00FFxxxx`.  The old analyzer zero-extended the field and therefore split
one architectural address into two.

## 2. E3.2-A — the three E3.1 fixes

### A1 — full memory-use comparison

`tools/cr16_e3.py` now matches an old use on:

- instruction address;
- effective address;
- `READ` / `WRITE` / `RMW`;
- displacement when it exists in the old record;
- register pair when both records carry one.

A missing old field is recorded as `old_displacement_available: false`, not as
equality.  A present but changed field produces `mismatched`; an absent use
produces `missing`; either makes the old proof `INVALID`.

The stricter audit also removed false E2 uses that were actually
`movd (pair),(pair)` register moves, not memory accesses.  This changed the
old 25/10 audit:

| Image | E2 PROVEN audited | still PROVEN | CANDIDATE | INVALID |
|---|---:|---:|---:|---:|
| normal | 25 | 11 | 3 | 11 |
| p2test | 10 | 3 | 2 | 5 |

### A2 — fail-closed baseline

`old_report()` now requires the E2 baseline from the immutable commit (or a
local backup with the same SHA256), validates its structure and firmware
SHA256, and raises `RuntimeError` if it is missing or corrupt.  `main()`
returns exit code 1 and writes no confirmed report in that case.

### A3 — table def-use scope

`_find_table_consumer()` now only searches backwards inside one basic block.
The unreachable `CLOBBERED_AFTER_LOAD` branch was removed.  Every table
candidate carries `def_use_scope: LOCAL_BASIC_BLOCK_ONLY`; this is not a
claim of inter-block def-use.  The proven-table-target count remains zero.

## 3. E3.2-B — CR16 address form and extension

### 3.1 The two forms in the firmware

| Firmware form | Bytes | Decoded form | Encoded field | Effective address |
|---|---|---|---|---|
| `storw r2,0xf6006:m` at normal `0x1348` | `2f c9 06 60` | abs20 | `0xF6006` | `0x00FF6006` |
| `loadw 0xf6002:m,r0` at normal `0x25FAE` | `0f 89 02 60` | abs20 | `0xF6002` | `0x00FF6002` |
| `storw r0,0xf5402:m` at normal `0x1934` | `0f c9 02 54` | abs20 | `0xF5402` | `0x00FF5402` |
| `movd $0xff6006,(r1,r0)` at normal `0x2582` | `70 00 ff 00 06 60` | 24-bit literal into pair | `0x00FF6006` | `0x00FF6006` |
| `storw r2,0x0:s(r1,r0)` at normal `0x258C` | `20 d0` | pair + displacement 0 | value in pair | `0x00FF6006` |

The `abs20` field is 20 bits.  The toolchain and an independent emulator
implement the same expansion:

- QEMU CR16C `target/cr16c/translate.c` (CompactCall/qemu-cr16 `4f9e07e0ffdc4d16026e7d66f5a270b84aa12e77`):
  `if (addr > 0xEFFFF) addr |= 0xF00000;`
- binutils GAS `tc-cr16.c`: `OP_ABS20` rejects values above `0xEFFFF`, and
  `adjust_if_needed()` rewrites an `abs24` value above `0xF00000` to its low
  20 bits and selects the `abs20` form.

Values `0x00000…0xEFFFF` stay zero-extended.  Values `0xF0000…0xFFFFF`
expand to `0xFF0000…0xFFFFFF`.  This is the CR16 effective-address rule; it
is **not** evidence that the SC14448 peripheral bus ignores address bits.

### 3.2 Synthetic assembler result

A local binutils-2.44 CR16 assembler was built offline and used only for
format checks:

```text
loadw 0xf6006,r0       -> 12 00 00 ff 06 60   abs24, 0xF6006
storw r2,0xf6006       -> 13 00 20 ff 06 60   abs24, 0xF6006
loadw 0xff6006,r0      -> 0f 89 06 60         abs20, encoded 0xF6006
movd  $0xff6006,(r1,r0)-> 70 00 ff 00 06 60   24-bit literal
storw r2,0(r1,r0)      -> 20 d0               pair, displacement 0
```

The assembler's `loadw 0xff6006` choice confirms the sign-extension model: it
uses the short abs20 form for a value that must expand back to `0x00FF6006`.
The store side is asymmetric (it keeps abs24), which is why the report treats
each site from raw firmware bytes, not from assembler intent.

### 3.3 Where the old analyzer was wrong

`X.abs20_address()` used to return only the 20-bit field.  E3.2 keeps that
value as `encoded_address` and adds the architectural address.  The report
contains both, so no instruction-level provenance is lost.

## 4. Q57 verdict

| Hypothesis | Verdict | Evidence |
|---|---|---|
| address truncation in the analyzer | **refuted as the final model** | raw field is 20 bits, but the ISA expands high values |
| zero extension | **refuted for `0xF0000…0xFFFFF`** | GAS `OP_ABS20` range and QEMU `reloc_abs20` |
| sign extension / `RELOC_ABS20` | **PROVEN_BY_ISA** | QEMU and binutils agree; raw bytes match all sites |
| hardware alias/window | **not needed** for the 12 observed pairs | the low form expands to the same effective address |
| different physical spaces | **not supported** by the effective-address model | `0x000F…` is not an effective address |
| SC14448 physical register identity | **CANDIDATE** | still only the related-device SC14480 map; no SC14448 bus trace |

**Q57 is closed for the address-space question.**  The remaining question is
no longer “do `0x000F6006` and `0x00FF6006` alias?” but “which SC14448
physical register is at `0x00FF6006`?”.  That needs an SC14448 memory map or
bus evidence; SC14480 is a related-device analogy.

## 5. DIP RAM payload

The 511-word fill is still `DIP_RAM_FILL_CANDIDATE`; `0x1001` is not declared
a valid program.  The SC14480 DIP command table gives:

| Byte order | Opcode | Parameter | Meaning |
|---|---|---|---|
| little-endian | `0x01` | `0x10` | `BR` |
| big-endian | `0x10` | `0x01` | `BR_B0` |

Both interpretations are branches, but the parameter/target, instruction
length and byte order remain unproved.  The fill starts at `0x01000002`,
matching the SC14480 rule that execution starts at the second DIP word.

## 6. DSP/DIP IRQ comparison after canonicalisation

| Path | Encoded form | Effective address | SC14480 related-device meaning |
|---|---|---|---|
| `dip_int` read | `0x000F6006` | `0x00FF6006` | `DIP_CTRL_REG`, `URST` bit 7 |
| `dip_int` ack | `0x000F5402` | `0x00FF5402` | `RESET_INT_PENDING_REG`, bit 10 `DIP_INT_PEND` |
| `dsp_int` ack | `0x000F5402` | `0x00FF5402` | same register, bit 13 `DSP_INT_PEND` |
| `dsp_int` pointer | `0x01027F80 + 0x58` | `0x01027FD8` | `DSP_INT_REG` |
| DIP poll | `0x000F6002` | `0x00FF6002` | `DIP_PC_REG` |

The address-space part is now consistent.  The physical register semantics
remain **CANDIDATE_RELATED_DEVICE_MAP**, not proven SC14448 facts.  The
`dsp_int` pointer target is above 24 bits; its bank/extension mechanism is
still unresolved.

## 7. Reports and tests

New reports:

- `tools/reports/cr16-address-forms-normal.json`
- `tools/reports/cr16-address-forms-p2test.json`
- `tools/reports/cr16-address-space-conflicts.json`
- `tools/reports/cr16-dip-ram-fill.json`
- `tools/reports/cr16-e32-audit.json`

New test:

- `tools/tests/test_cr16_address_spaces.py`

All offline checks are listed in `docs/history/fon-e32-proof-audit.md`.
No hardware was authorized or performed.

## 8. Q status after E3.2

| Q | Status |
|---|---|
| Q44 / Q57 address translation | **resolved at the CR16 effective-address level** |
| Q46 `0x01000000` | **open**: DIP RAM candidate; payload `0x1001` not proved |
| Q55 indexed writer/reader | **open**: one static store, reader still unresolved |
| Q75 slot-5 consumer | **open**: no source-to-sink proof |

K1/K2 remain NO-GO.  FON-E4 was not started.
