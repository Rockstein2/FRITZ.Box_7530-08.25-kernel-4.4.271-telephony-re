# Dialog register cross-reference

> **Status: comparison table, not a second SC14448 datasheet.**
> Source registry: `dialog-external-sources.md`.
> Firmware evidence: `tools/reports/peripheral-xrefs.json`,
> `tools/reports/cr16-dataflow-*.json` and `docs/fon-known-facts.md`.

## 1. Confidence labels

| Label | Meaning |
|---|---|
| `EXACT_SC14448_EVIDENCE` | an instruction at a known SC14448 address performs the stated access; this proves the access, not necessarily the peripheral meaning |
| `SAME_ADDRESS_DIFFERENT_CHIP` | the same numeric address/symbol appears in the SC14CVMDECT datasheet and in SC14448 firmware; correspondence of function is plausible but not proven |
| `FAMILY_ANALOGY` | related-family naming or behavior suggests a function; no SC14448 proof |
| `CONFLICT` | the reference and firmware evidence do not agree, or the same symbol is claimed in two address spaces |
| `UNKNOWN` | insufficient evidence |

**E3.2 correction:** the `0x000Fxxxx` labels below are printed abs20 fields.
CR16Cplus expands fields above `0xEFFFF` to `0x00FFxxxx`, so a row such as
`0x000F6006` is the short encoding of effective `0x00FF6006`.  The table
keeps both numeric forms for provenance; physical register identity remains
a related-device CANDIDATE.

## 2. Register rows

| Address | Reference symbol / function | Reference chip | Observed SC14448 access | Normal / p2test correspondence | Confidence | Source |
|---|---|---|---|---|---|---|
| `0xFF481E` | `PAD_CTRL_REG`; P2[2,5] and P2[3,4] open-drain, P2[0/1] open-drain | SC14CVMDECT | `0x00FF481E` RMW bits 6/7 at normal `0x1200`, `0x1202`; p2test `0x0C76`, `0x0C78` | same low address; both images | `SAME_ADDRESS_DIFFERENT_CHIP` | PDF p29; firmware xrefs |
| `0xFF4830` | `P0_DATA_REG` | SC14CVMDECT | not found as a resolved access | none | `FAMILY_ANALOGY` | PDF p30 |
| `0xFF4840` | `P1_DATA_REG` | SC14CVMDECT | not found | none | `FAMILY_ANALOGY` | PDF p30 |
| `0xFF4850` | `P2_DATA_REG` | SC14CVMDECT | not found | none | `FAMILY_ANALOGY` | PDF p30 |
| `0xFF4860` | `P3_DATA_REG` | SC14CVMDECT | `0x00FF4860` RMW at normal `0x122E`, `0x1240`; p2test `0x0CA4`, `0x0CB6` | same low address; both images | `SAME_ADDRESS_DIFFERENT_CHIP` | PDF p30; firmware xrefs |
| `0xFF4856` | `P2_DIR_REG` | SC14CVMDECT | `0x00FF4856` read/write at normal `0x11EE…0x11F8`; p2test `0x0C64…0x0C6E` | same low address; both images | `SAME_ADDRESS_DIFFERENT_CHIP` | PDF p31; firmware xrefs |
| `0xFF4858` | `P2_MODE_REG`; for CVM, `01` on P2[2] = PCM_CLK, P2[3] = PCM_DI, P2[4] = PCM_DO, P2[5] = PCM_FSC | SC14CVMDECT | `0x00FF4858` read/write at normal `0x11D4…0x11E6`; p2test `0x0C4A…0x0C5C` | same low address; both images | `SAME_ADDRESS_DIFFERENT_CHIP` for the register; **PCM pinmux is not proved** | PDF p32–33; firmware xrefs |
| `0xFF4836` | `P0_DIR_REG` | SC14CVMDECT | `0x00FF4836` read/write at normal `0x12FC…0x1308`; p2test `0x0D72…0x0D7E` | same low address; both images | `SAME_ADDRESS_DIFFERENT_CHIP` | PDF p31; firmware xrefs |
| `0xFF4838` | `P0_MODE_REG` | SC14CVMDECT | `0x00FF4838` read/write normal `0x12EA…0x12FA`; p2test `0x0D60…0x0D70` | same low address; both images | `SAME_ADDRESS_DIFFERENT_CHIP` | PDF p31–32; firmware xrefs |
| `0xFF4866` | `P3_DIR_REG` | SC14CVMDECT | `0x00FF4866` read/write normal `0x1214…0x1250`; p2test `0x0C8A…0x0CC6` | same low address; both images | `SAME_ADDRESS_DIFFERENT_CHIP` | PDF p31; firmware xrefs |
| `0xFF4868` | `P3_MODE_REG`; P3[7:5] have analog RINGp/RINGn/RINGING modes for CVM | SC14CVMDECT | `0x00FF4868` read/write normal `0x1208…0x1248`; p2test `0x0C7E…0x0CBE` | same low address; both images | `SAME_ADDRESS_DIFFERENT_CHIP` for register; **ring pin mapping not proved** | PDF p33–34; firmware xrefs |
| `0xFF4808` | not identified in retrieved PDF pages | SC14CVMDECT | `0x00FF4808` RMW normal `0x1414…0x141C`; p2test `0x0E8A…0x0E92` | same low address; both images | `UNKNOWN` | firmware xrefs; PDF not found |
| `0xFF4810` | not identified in retrieved PDF pages | SC14CVMDECT | `0x00FF4810` read normal `0x19D4`; p2test `0x27A5E` | same low address; both images | `UNKNOWN` | firmware xrefs |
| `0xFF4812` | not identified in retrieved PDF pages | SC14CVMDECT | `0x00FF4812` RMW normal `0x13A8…0x13AE`; p2test `0x0E1E…0x0E24` | same low address; both images | `UNKNOWN` | firmware xrefs |
| `0xFF5804` | not identified in retrieved PDF pages | — | `0x00FF5804` RMW normal `0x1252…` | unknown | `UNKNOWN` | firmware xrefs |
| encoded `0x000F4858` | `P2_MODE_REG` candidate | SC14CVMDECT analogy | abs20 RMW normal `0x1442`; p2test `0x0EB8`; effective `0x00FF4858` | same effective address as the pair accesses | `SAME_ARCHITECTURAL_ADDRESS`; physical identity `CANDIDATE` | firmware xrefs; E3.2 |
| encoded `0x000F6002` | no CVM mapping; `DIP_PC_REG` candidate | SC14480 analogy | `loadw 0xF6002` normal `0x25FAE`; p2test `0x26764`; effective `0x00FF6002` | both images | `EXACT_SC14448_EVIDENCE` for access; semantics `CANDIDATE` | firmware xrefs; E3.2 |
| encoded `0x000F6006` | `DIP_CTRL_REG` candidate | SC14480 analogy | `loadw` normal `0x2602C`, `0x28CDE`; p2test `0x267E2`, `0x27C96`; writers normal `0x1348`, `0x145C`; p2test `0x0DBE`, `0x0ED2`; effective `0x00FF6006` | same effective address as the pair accesses | `SAME_ARCHITECTURAL_ADDRESS`; physical identity `CANDIDATE` | firmware xrefs; E3.2 |
| `0x00FF6006` | `DIP_CTRL_REG` candidate | SC14480 analogy | pulse/read/write normal `0x2582…0x25B4`; p2test `0x1E3E…0x1E70` | both images, shifted; same effective address | `EXACT_SC14448_EVIDENCE` for access; physical identity `CANDIDATE` | firmware xrefs; E3.2 |
| encoded `0x000F5402` | `RESET_INT_PENDING_REG` candidate | SC14480 analogy | writes `0x100`, `0x400`, `0x2000` at normal `0x1934`, `0x25B0`, `0x289A8`, `0x28B00`, `0x28CE8`; effective `0x00FF5402` | both images | `EXACT_SC14448_EVIDENCE` for access; physical identity `CANDIDATE` | firmware xrefs; E3.2 |
| encoded `0x000F6400/6402` | `BMC_CTRL`/`BMC_CTRL2` candidate | SC14480 analogy | `0xF6400=0`, `0xF6402=0xF0` normal `0x255E/0x2566`; effective `0x00FF6400/6402` | both images | `EXACT_SC14448_EVIDENCE` for access; physical identity `CANDIDATE` | firmware xrefs; E3.2 |
| `0x00FF5406` | no CVM mapping; SC14448 control candidate | — | RMW normal `0x1A14…0x1A22`, `0x2596…0x25A2`; p2test shifted | both images | `EXACT_SC14448_EVIDENCE` for access; semantics `UNKNOWN` | firmware xrefs |

## 2a. Full `0xFF48xx` family map

The SC14CVMDECT PDF lists the following address family (pages 30–34).  The
last column is the SC14448 firmware evidence found in the current xref report.

| Port | DATA | SET | RESET | DIR | MODE | SC14448 firmware evidence |
|---|---|---|---|---|---|---|
| P0 | `0xFF4830` | `0xFF4832` | `0xFF4834` | `0xFF4836` | `0xFF4838` | DIR/MODE used at `0x00FF4836/38`; DATA/SET/RESET not resolved |
| P1 | `0xFF4840` | `0xFF4842` | `0xFF4844` | `0xFF4846` | `0xFF4848` | none resolved |
| P2 | `0xFF4850` | `0xFF4852` | `0xFF4854` | `0xFF4856` | `0xFF4858` | DIR/MODE used at `0x00FF4856/58`; DATA/SET/RESET not resolved |
| P3 | `0xFF4860` | `0xFF4862` | `0xFF4864` | `0xFF4866` | `0xFF4868` | DATA/DIR/MODE used at `0x00FF4860/66/68`; SET/RESET not resolved |

The family also includes `0xFF4808`, `0xFF4810`, `0xFF4812` and `0xFF481E`
used by the firmware.  `0xFF481E` is `PAD_CTRL_REG`; the other three were not
identified in the retrieved CVM pages and remain `UNKNOWN`.

## 2b. SC14480 cross-reference (related device, highest priority)

The SC14480A5M/A2M6 datasheet provides a much closer peripheral map than the
SC14CVMDECT module.  Page numbers are printed pages; see
`sc14480-memory-map.md` for the detailed map.

| Address | SC14480 symbol | Firmware observation | Comparison |
|---|---|---|---|
| `0x01000000–0x010003FF` | DIP Sequencer RAM, 512×16 | fill loop writes `0x01000002…0x010003FE` | **strong structural match**: 511 words start at DIP `+1` |
| `0x01027F80–0x01027FFF` | Gen2DSP registers | `[0xD6] = 0x01027F80`; base for `+0x58` | **strong base match**; runtime pointer is a static image candidate |
| `0x01027FD8` | `DSP_INT_REG` | `dsp_int` reads/tests/writes the word at pointer+0x58 | **strong functional hypothesis**: DSP interrupt vector/clear-on-write |
| `0x00FF5402` | `RESET_INT_PENDING_REG`, bit 10 DIP / bit 13 DSP | abs20 `0xF5402` expands to `0x00FF5402` | semantic candidate; physical identity not proved |
| `0x00FF6000` | `DIP_STACK_REG` | not seen in current scan | reference only |
| `0x00FF6002` | `DIP_PC_REG` | abs20 `0xF6002` expands to `0x00FF6002` | semantic candidate; physical identity not proved |
| `0x00FF6004` | `DIP_STATUS_REG` | not seen | reference only |
| `0x00FF6006` | `DIP_CTRL_REG`, bit 7 `URST` | pair accesses at `0x00FF6006` and abs20 `0xF6006` expand to the same effective address | **strong effective-address match**: stop/start DIP |
| `0x00FF6400` | `BMC_CTRL_REG` | abs20 `0xF6400` expands to `0x00FF6400` | semantic candidate; physical identity not proved |
| `0x00FF6402` | `BMC_CTRL2_REG` | abs20 `0xF6402` expands to `0x00FF6402` | semantic candidate; physical identity not proved |

SC14480 printed p33/p64/p131–132/p171–172/p177/p196–197.  These rows are
**related-device analogies**, not SC14448 proofs.  In particular:

- the `0x01000000` fill structure is strong, but the repeated payload `0x1001`
  is not decoded as a valid DIP program;
- `DSP_INT_REG` explains the `dsp_int` shape, but not any slot-5 PCM meaning;
- the short forms `0x000F5402`, `0x000F6002`, `0x000F6006` and
  `0x000F6400/6402` are encoded abs20 fields that expand to `0x00FFxxxx`;
  the address-space conflict is resolved, but the SC14448 physical register
  identity remains a related-device candidate.

## 3. What the matching registers do and do not mean

### 3.1 `0x00FF48xx` family

SC14448 firmware repeatedly accesses `0x00FF481E`, `0x00FF4856`, `0x00FF4858`,
`0x00FF4860`, `0x00FF4866`, `0x00FF4868`, `0x00FF4836` and `0x00FF4838`.
Their low 16-bit addresses match the SC14CVMDECT GPIO/PAD register family
exactly.  That is useful evidence for a shared family layout.

It does **not** prove that the SC14448 has the same pin functions.  In
particular, the observed `P2_MODE` write at normal `0x11D4` writes value
`0x5` in the low nibble, not the CVM `01` fields for P2[2..5] PCM.  The
firmware may use a different pinmux or a different register bit assignment.
The CVM PCM mapping remains a **reference hypothesis**.

The `P3_MODE`/`P3_DIR`/`P3_DATA` accesses are interesting for the analog ring
question because the CVM uses P3[7:5] for RINGp/RINGn/RINGING in analog mode.
The firmware writes those registers, but no SC14448 pin/pad proof exists.  Do
not assign the FRITZ!Box ring topology from this table.

### 3.2 `0xF600x`, `0xFF600x`, `0xF5402`

These are SC14448 firmware behaviors.  The PDF is a different chip and does
not provide a mapping for them.

- `0x000F6002` is a polled value in the bring-up path.
- `0x000F6006` is read in the polled path and in `dip_int`; its low byte is
  passed onward in `dip_int`.
- `0x00FF6006` is pulsed/read/written in a separate path.
- `0x000F5402` receives several different values (`0x100`, `0x400`, `0x2000`).
- `0x000F6400/6402` are written in the bring-up path.

The numeric relation of `0x000F6006`, `0x00FF6006` and `0x000F6002` is now
explained by abs20 expansion: the low form is the encoded field and the high
form is the effective address.  Q57 is resolved at the address-space level;
the physical SC14448 register identity remains a candidate.

## 4. Unresolved cross-reference items

1. Does SC14448 `P2_MODE_REG` use the CVM P2[2..5] PCM fields?  The current
   firmware write is not sufficient to say yes.
2. Does SC14448 `P3_MODE_REG` drive the same RINGp/RINGn/RINGING pins?  The
   address family matches, the pin map does not.
3. What are `0xFF4808`, `0xFF4810`, `0xFF4812` and `0xFF5804`?  Not found in
   the retrieved CVM pages.
4. Is `0x000F4858` an alias of `0x00FF4858`?  No proof; treat as **UNKNOWN**.
5. What is the meaning of `0xF6002`, `0xF6006`, `0xFF6006`, `0xF5402` and
   `0xF6400/6402` on SC14448?  External references do not answer this.

These are reference hints, not closures of Q16/Q17/Q54/Q75.  E3.2 closes the
Q57 address-space part; SC14448 physical identity is still open.
