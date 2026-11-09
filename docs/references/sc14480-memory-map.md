# SC14480 memory map and E3 cross-check

> **Status: related-device reference; not an SC14448 datasheet.**
> File: `reference/hardware/SC14480.pdf` (outside Git)
> SiTel SC14480A5M / SC14480A2M6, revision 1.0, 2009-01-21, 259 pages.
> SHA256: `a0b0300cc0dc50ac98bff4c9021dcbb86ba7b063554f406ac8f65c84a51782d0`

Page references below use the **printed page numbers** in the datasheet.
The physical PDF page is normally one greater; e.g. printed page 131 is PDF
page 132.

## 1. Memory map (SC14480 only)

| Address | SC14480 meaning | Printed page |
|---|---|---|
| `0x0000.0000–0x0000.7FFF` | reserved | p131 |
| `0x0000.8000–0x0000.9FFF` | non-shared RAM (A5M only) | p131 |
| `0x0001.0000–0x0001.FFFF` | shared RAM for CR16Cplus, Gen2DSP and DIP | p131–132 |
| `0x000F.0000–0x002E.FFFF` | program FLASH/ROM (device-size dependent) | p131 |
| `0x00FE.F000–0x00FE.F7FF` | boot ROM | p131 |
| `0x00FF.0000–0x00FF.FBFF` | on-chip peripheral and chip-ID registers | p131 |
| `0x00FF.FC00–0x00FF.FFFF` | ICU vectors and traps | p131 |
| `0x0100.0000–0x0100.03FF` | **DIP Sequencer RAM**, 512 × 16 bit | p131–132 |
| `0x0100.0002` | first DIP instruction executed after `URST=0` | p33 |
| `0x0100.0400–0x0100.0FFF` | reserved DIP microcode space | p132 |
| `0x0102.0000–0x0102.53FF` | shared data ROM | p132 |
| `0x0102.7F80–0x0102.7FFF` | **Gen2DSP registers** | p132 |
| `0x0102.7FD8` | **DSP_INT_REG** | p177 |
| `0x0103.0000–0x0103.07FF` | Gen2DSP microcode RAM | p132 |

The low `0x000F.xxxx` range and the high `0x00FF.xxxx` range are different
**decoded** spaces in this map.  The map is for SC14480, not SC14448.

> **E3.2 correction:** the SC14448 firmware's `0x000Fxxxx` operands are not
> decoded addresses.  They are 20-bit abs20 fields; CR16Cplus expands fields
> above `0xEFFFF` by OR `0xF00000`, so encoded `0xF6006` is effective
> `0x00FF6006`.  This does not change the SC14480 map; it changes how the
> firmware's encoded operand is interpreted.

## 2. DIP control window (SC14480, printed p171–172)

| Address | Register | Key meaning |
|---|---|---|
| `0x00FF6000` | `DIP_STACK_REG` | DIP stack pointer, read-only |
| `0x00FF6002` | `DIP_PC_REG` | DIP program counter, valid on break/freeze |
| `0x00FF6004` | `DIP_STATUS_REG` | read-only DIP status |
| `0x00FF6006` | `DIP_CTRL_REG` | bit 7 `URST`: write 1 stops DIP; write 0 starts at `DIP_RAM+1` |
| `0x00FF6400` | `BMC_CTRL_REG` | BMC control |
| `0x00FF6402` | `BMC_CTRL2_REG` | BMC control 2 |

Writing `0x0080` to `DIP_CTRL_REG` sets `URST=1` (stop); writing `0` starts
the sequencer at the second 16-bit word.  This is the sequence seen in the
SC14448 firmware's `0x2558` path at normal `0x2582`/`0x258C`/`0x25B4`
(p2test shifted), but the SC14448 register identity is still a hypothesis.

## 3. Interrupt registers (SC14480, printed p196–197)

`RESET_INT_PENDING_REG` is at `0x00FF5402` and is write-one-to-clear:

| Bit | Symbol | Meaning |
|---:|---|---|
| 13 | `DSP_INT_PEND` | write 1 clears pending DSP interrupt |
| 10 | `DIP_INT_PEND` | write 1 clears pending DIP interrupt |

The values `0x0400` (bit 10) and `0x2000` (bit 13) seen in `dip_int` and
`dsp_int` are **semantically consistent** with this table.  However, the
firmware instructions observed by E3 write to `0x000F5402` (20-bit/absolute
low space), not to `0x00FF5402`; see section 5.

`DSP_INT_REG` at `0x01027FD8` is a 16-bit Gen2DSP-to-CR16Cplus vector
register.  A set bit requests `DSP_INT`; writing a 1 to a set bit clears that
bit.  This is a strong functional analogy for the `dsp_int` read/test/write
sequence, but it is not proof of SC14448 address identity.

## 4. DIP RAM and the 511 writes

SC14480 has 512 words of DIP sequencer RAM at `0x01000000–0x010003FF`; the
first instruction after reset is at `0x01000002`.  The E3 firmware loop:

```text
normal:  control 0x25F90, static store 0x25D0
p2test:  control 0x26750, static store 0x1E8C
base = 0x01000000 + 2*index, index = 1…511
payload = 0x1001 (constant)
```

exactly fills 511 words starting at the second DIP word.  This is a **strong
structural match** to DIP RAM, but the payload needs decoding:

- the observed store writes constant `0x1001` on every iteration;
- in SC14480 Table 10, the 8-bit opcode `0x01` is `BR` (branch always);
- if the low byte is the opcode, `0x1001` could be `BR` with parameter `0x10`;
- the opposite byte order, instruction-width and parameter semantics are not
  proven; all 511 words being identical is not enough to call it a valid DIP
  program.

E3 therefore classifies the loop as **DIP-RAM fill candidate**, not “proven
DIP microcode”.  The missing fact is the DIP instruction encoding/byte order
and the meaning of the repeated `0x1001` payload.

## 5. Address-space conflict: `0x000Fxxxx` vs `0x00FFxxxx`

The SC14480 map says:

```text
0x000F0000…  Program FLASH/ROM
0x00FF0000…  Peripheral registers
```

The firmware observed by E3 uses a short encoded form and a 24-bit literal
form.  After E3.2 both are interpreted with the CR16Cplus effective-address
rule:

| Firmware access | Bytes / form | Encoded field | Effective address |
|---|---|---|---|
| `0x000F6006` read/write | abs20 `0F 89 06 60` etc. | `0xF6006` | `0x00FF6006` |
| `0x00FF6006` write/read | `movd $0x00FF6006` + pair access | `0x00FF6006` | `0x00FF6006` |
| `0x000F5402` write `0x400`/`0x2000` | abs20 `0F C9 02 54` etc. | `0xF5402` | `0x00FF5402` |
| `0x00FF5402` | no direct 24-bit access found | — | peripheral `RESET_INT_PENDING_REG` space |
| `0x000F6400/6402` write | abs20 | `0xF6400`/`0xF6402` | `0x00FF6400`/`0x00FF6402` |
| `0x000F6002` poll | abs20 `0F 89 02 60` | `0xF6002` | `0x00FF6002` |

Therefore:

- `0x00FF6006` is a strong independent match for `DIP_CTRL_REG` and the
  `0x80 → 0` stop/start sequence;
- `0x01027FD8` is a strong independent match for `DSP_INT_REG`;
- `0x01000000` is a strong structural match for DIP RAM;
- the old `0x000Fxxxx` / `0x00FFxxxx` “conflict” was an analyzer artifact:
  the short form expands to the high effective address.  Q57 is resolved at
  the CR16 effective-address level;
- the remaining uncertainty is SC14448 **physical register identity**, which
  still cannot be proved from an SC14480 map alone.

## 6. PCM warning

SC14480 has a **four-channel × 16-bit** PCM interface (printed p64).  The AVM
reconstruction has **eight logical 16-bit slots**.  The interfaces are not
interchangeable.

The SC14480 `1.024 MHz` mention on printed p33–34 is the DIP 8/9-mode clock,
not necessarily the PCM BCLK.  Do not use it to explain the AVM
`~1.024355 MHz` FSC/BCLK observation without a separate SC14448 measurement.

## 7. E3 impact

| E3 item | SC14480 cross-check | Status |
|---|---|---|
| `0x01000000 + 2*index` fill | 512-word DIP RAM at same base; first instruction +2 | strong structural hypothesis; payload `0x1001` undecoded |
| `[0xD6] = 0x01027F80`, `+0x58 = 0x01027FD8` | Gen2DSP register block / `DSP_INT_REG` | strong functional hypothesis; runtime pointer still static image value |
| `dsp_int` read/test/write of word at `0x01027FD8` | DSP vector register, write-1-to-clear | likely DSP interrupt handling; not proven SC14448 identity |
| `dip_int` writes `0x400` | SC14480 `RESET_INT_PENDING` bit 10 `DIP_INT_PEND` | semantic match; low-address decode unresolved |
| `dsp_int` writes `0x2000` | SC14480 bit 13 `DSP_INT_PEND` | semantic match; low-address decode unresolved |
| `0x00FF6006` `0x80 → 0` | DIP `URST` stop/start | strong same-address hypothesis |
| `0x000F6002` poll | encoded `0xF6002` expands to `0x00FF6002` | semantic candidate; SC14448 identity not proved |

No SC14480 fact is promoted to an SC14448 fact.  The Q57 address-space artifact
is resolved by the CR16 abs20 rule, not by this map.  Q46/Q55/Q75 remain open;
the SC14448 physical identity behind the resulting `0x00FFxxxx` addresses
remains CANDIDATE.
