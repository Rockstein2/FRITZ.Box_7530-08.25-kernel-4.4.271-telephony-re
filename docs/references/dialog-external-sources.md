# Dialog / CR16 / DECT external source registry

> **Status: external references, verified offline on 2026-11-09.**
> The project repository is not a substitute for a device datasheet or a
> hardware measurement.

## 1. Registry

### R1 — reDECTed wiki

| Field | Value |
|---|---|
| Name | reDECTed wiki |
| URL | <https://wiki.redected.org/> |
| Revision | live wiki, no Git revision; checked 2026-11-09 |
| License | not stated on the retrieved page; reference only |
| Target | DECT hobbyist/hardware knowledge, SC14CVMDECT module |
| Relevant sections | SC14CVMDECT module, devboard, DECT projects, Linux CR16C, QEMU CR16C |
| Verified facts | page links to the SC14CVMDECT devboard, `regrettableDectable`, `linux-cr16` and `qemu-cr16`; it describes `linux-cr16` and `qemu-cr16` as WIP |
| Transferable | discovery index, not a device fact |
| Limitations | no SC14448 register proof; no AVM firmware proof |
| Related questions | Q16, Q17, Q54, Q75 |
| Priority | P3 — discovery only |

### R2 — Linux CR16C port

| Field | Value |
|---|---|
| Name | CompactCall `linux-cr16` |
| URL | <https://codeberg.org/CompactCall/linux-cr16> |
| Revision | branch `cr16-wip`, commit `902254883f702e9533e6591eb457a97ca6ace257` (2025-08-21) |
| License | `GPL-2.0 WITH Linux-syscall-note` (repository `COPYING`) |
| Target | experimental Linux port for CR16C; platforms `SC14450`, `SC14452` |
| Relevant files | `arch/cr16/kernel/irq.c`; `arch/cr16/include/asm/irq.h`; `arch/cr16/include/asm/processor.h`; `arch/cr16/include/asm/switch_to.h`; `arch/cr16/include/uapi/asm/ptrace.h`; `arch/cr16/kernel/traps.c` |
| Verified facts | 31-entry `struct cr16_interrupt_vector`; `struct pt_regs` has pair slots r0/r1 through r10/r11, plus r12, r13, ra, psr, pc and usp; `PT_SP` is declared as a UAPI index but the retrieved struct does not show a separate `sp` field, so verify that offset before use; CR16 context code uses `ra`/`sp`; IRQ vector setup uses `INTBASE`/`CR16_IRV_ADDR` and `v[n + 0x10]` for normal interrupts; the tree is explicitly WIP |
| Transferable | a second implementation of CR16C register/exception conventions; useful cross-check for `ra`/`sp`/pair and vector handling |
| Limitations | Linux on SC14450/SC14452, not SC14448; a board port is not AVM firmware; do not copy ABI into SC14448 as proof |
| Related questions | Q16, Q17, Q54, Q57, Q75 |
| Priority | P1 — CR16 ABI/IRQ cross-check |

The exact code is not copied into this repository.  It is referenced by commit
and path so it can be checked independently.

### R3 — QEMU CR16C target

| Field | Value |
|---|---|
| Name | CompactCall `qemu-cr16` |
| URL | <https://codeberg.org/CompactCall/qemu-cr16> |
| Revision | branch `cr16-wip`, commit `4f9e07e0ffdc4d16026e7d66f5a270b84aa12e77` (2026-08-10) |
| License | `GPL-2.0` (repository `COPYING`, QEMU) |
| Target | experimental CR16C CPU/board emulation |
| Relevant files | `target/cr16c/translate.c`, `target/cr16c/insn.decode`, `target/cr16c/cpu.h`, `target/cr16c/helper.c`, `target/cr16c/machine.c` |
| Verified facts | decode includes `MOV`, `MOVD_reg`, `ADDD`, `LOAD`, `STOR`, `LOADM`, `STORM`, `BRCOND`, `JCOND`, `EXCP`, bit operations and arithmetic; `cpu.h` explicitly says interrupts are still TODO; `helper_raise_illegal_instruction` and `helper_raise_unimplemented_instruction` exist; `LOADM`/`STORM` are implemented |
| Not found in decode | `JAL`, `JALR`, `RETX`, `LOADMP`, `STORMP` (the exact missing status must be rechecked if the commit changes) |
| Transferable | independent instruction/ABI oracle for a **small** implemented sequence; useful for checking pair arithmetic and `loadm`/`storm` semantics |
| Limitations | not a complete firmware emulator; no verified interrupt/vector execution; missing control-transfer forms; not proof for SC14448 |
| Related questions | Q16, Q54, Q75 |
| Priority | P2 — instruction-level cross-check only |

The repository is much too large to vendor.  Use the commit above and
`target/cr16c` only.

### R4 — regrettableDectable

| Field | Value |
|---|---|
| Name | Mimoja `regrettableDectable` |
| URL | <https://github.com/Mimoja/regrettableDectable> |
| Revision | `main`, commit `98734603701c5c5bc886854a66264747029b5d8f` |
| License | GPL-3.0 |
| Target | Python host client for a working Dialog DECT module using the Phoenix API |
| Relevant files | `MailProtocol.py`, `Dect.py`, `Api/AUDIO.py`, `Api/HAL.py`, `Api/Commands.py`, `Api/Api.py`, `APIParser.py`, `EepromDefinitions.py` |
| Verified facts | mailbox transport uses start byte `0x10`, SABM/RR/REJ/RNR supervision, 3-bit sequence numbers and a header+payload byte checksum; HAL memory types are `AHA_MEMORY=0x00`, `AHA_REGISTER=0x01`, `AHA_NVS=0x02`, `AHA_DSP=0x03`, `AHA_FPGA=0x04`, `AHA_SEQUENCER=0x05`; audio enum has FSC 8/16/32 kHz and PCM clocks 1.152/1.536/2.304/4.608 MHz; PCM fields include master/slave, FSC length, clock edge, channel delay and open-drain; commands include `API_FP_RESET_REQ`, `API_FP_INIT_PCM_REQ`, HAL read/write |
| Transferable | reference for Phoenix API shape, UART mailbox framing, HAL area IDs and PCM option names |
| Limitations | Phoenix API is a **running DECT firmware** API; it is not the SC14448 ROM bootloader and not the PCMLINK slot-5 protocol.  No evidence that AVM firmware exposes Phoenix primitives.  `MailProtocol.py`, `Api/HAL.py`, `Api/AUDIO.py` and `Api/Commands.py` were fetched; the other listed files were seen in the repository tree but not all individually inspected |
| Related questions | Q16, Q17, Q38, Q75 |
| Priority | P1 — API vocabulary only; never run `main.py` |

`main.py` contains active reset/NVS/mode commands.  It was not executed.  The
source is not vendored.

### R5 — SC14CVMDECT SF datasheet

| Field | Value |
|---|---|
| Name | SC14CVMDECT SF datasheet |
| File | `reference/hardware/SC14CVMDECT.PDF` (workspace-relative, outside Git) |
| Manufacturer / revision | Dialog Semiconductor, revision 3.0, 28-Jul-2015, 57 pages |
| SHA256 | `01be0fced7d4a0ad2c8fb72b6463d3e955072b6d1e219d96806ae6d8859ac5bf` |
| License | Dialog datasheet, `FINAL`; reference only, not public-licensed content |
| Target | SC14CVMDECT SF cordless voice module, **not SC14448** |
| Relevant pages | 4–7 pinout/UART/PCM/RSTn; 8–9 CR16/DSP/PCM architecture; 11 FP support; 22–27 PCM timing; 29–34 GPIO/PAD/MODE registers; 35–37 electrical limits |
| Verified register facts | `PAD_CTRL_REG=0xFF481E`; `P0_DATA_REG=0xFF4830`; `P1_DATA_REG=0xFF4840`; `P2_DATA_REG=0xFF4850`; `P3_DATA_REG=0xFF4860`; `P2_DIR_REG=0xFF4856`; `P2_MODE_REG=0xFF4858`; the family also has P0/P1/P2/P3 `_DIR`, `_MODE`, `_SET`, `_RESET` at the addresses listed on pages 30–34 |
| Verified PCM facts | FSC 8/16 kHz; master BCLK 1.152, 1.536, 2.304 or 4.608 MHz; FSC pulse length 1/8/16/32 bits; PCM supports master/slave and edge settings |
| Verified pinmux facts | for this chip, `P2[2] -> PCM_CLK`, `P2[3] -> PCM_DI`, `P2[4] -> PCM_DO`, `P2[5] -> PCM_FSC` when the corresponding mode is `01` |
| Verified electrical facts | `Vdig_max` for digital pins other than backdrive-protected P0/P2 is 2.0 V; `RSTn` is active-low input with Schmitt trigger; table 21 gives `Vil_rst=0.2*VDD`, `Vih_rst=0.8*VDD` at VDD=1.8 V |
| Verified PSTN fact | table 4, page 11: standard FP API does **not** provide a PSTN line interface |
| Transferable | family register names, PCM option ranges and pin-function encodings for comparison |
| Limitations | the datasheet is for a different module; no SC14448 register map, no FRITZ!Box schematic, no proof that SC14448 P2[2..5] are the same pins |
| Related questions | Q16, Q17, Q30, Q31, Q46, Q57, Q74, Q75 |
| Priority | P1 — PCM/register analogy; never a direct setting transfer |

The PDF is not added to Git.  Its checksum and page references are recorded
here instead.

### R6 — OsmocomDECT

| Field | Value |
|---|---|
| Name | OsmocomDECT project |
| URL | <https://projects.osmocom.org/projects/dect>; wiki <https://osmocom.org/projects/dect/wiki> |
| Revision | **NOT VERIFIED** — the site returned the Anubis anti-bot challenge on 2026-11-09 |
| License | source patch files are GPL-2.0; project pages not verified |
| Target | Sitel SC14421/SC14424 DECT baseband and com-on-air hardware |
| Relevant source names | `sc1442x.c`, `sc1442x_firmware.asm`, `dip_opcodes.h`, `com_on_air.h` |
| Verified artifact | the OpenWrt mailing-list message `000225` is live and its inline RFC patch lists those files, including a 1020-line `sc1442x.c`, a 389-line `sc1442x_firmware.asm`, a 157-line `dip_opcodes.h` and a 99-line `com_on_air.h` |
| Verified facts from the patch | DIP has specialized firmware/opcodes; the driver separates code/data memory and DIP banks; IRQ groups cover DECT RF slots 0–5, 6–11, 12–17, 18–23; the code is GPL-2.0 |
| Transferable | DIP interrupt/bank model and the distinction between DECT RF slots and memory/PCM slots |
| Limitations | SC14421/14424 driver, not SC14448; DIP instructions are not ordinary CR16C machine code; project repository and wiki content are not verified in this run |
| Related questions | Q16, Q17, Q54, Q75 |
| Priority | P2 — DIP analogy only |

The OpenWrt message is:

<https://lists.openwrt.org/pipermail/openwrt-devel/2014-June/000225.html>

The message itself says the `git://dect.osmocom.org/linux-2.6.git` tree was
empty at the time and points to older patch material.  No new source tree was
assumed.

### R7 — OsmocomDECT / Asterisk page

| Field | Value |
|---|---|
| Name | OsmocomDECT Asterisk integration page |
| URL | <https://projects.osmocom.org/projects/dect/wiki/Asterisk> |
| Revision | **NOT VERIFIED** — Anubis challenge on 2026-11-09 |
| License | not verified |
| Target | historical DECT/Asterisk integration |
| Reported architecture | `Asterisk -> chan_dect -> libdect -> Linux DECT subsystem -> SC1442x driver` (project description; not independently verified here) |
| Transferable | conceptual separation of call control, audio channels and driver events only |
| Limitations | no analog FXS path; `chan_dect` is not a FON driver; page not retrieved |
| Related questions | Q30, Q75 |
| Priority | P3 — background only |

This is recorded as an unverified external claim.  No OsmocomDECT or Asterisk
porting work was started.

### R8a — openD

| Field | Value |
|---|---|
| Name | openD framework |
| URL | <https://github.com/opend-connect/openD> |
| Revision | `master`, commit `686fc01b7bc925d744d6efdeee73348f3ced8375`; repository archived 2025-10-31 |
| License | Apache-2.0 or GPL-2.0 |
| Target | DECT ULE fixed/portable framework, Dialog and DSPG hardware |
| Relevant sections | `README.md`, `src/opend`, `doc`, Phoenix/HAN-FUN demo applications |
| Verified facts | framework defines a unified API for DECT/ULE fixed and portable devices; supports Dialog fixed-part/portable-part demo boards and legacy call/audio examples |
| Transferable | Phoenix API vocabulary and fixed-part/portable-part integration concepts |
| Limitations | not a SC14448 register source; not an analog FXS implementation; archived |
| Related questions | Q16, Q30, Q75 |
| Priority | P3 — API context |

### R8b — SC14CVMDECT devboard

| Field | Value |
|---|---|
| Name | SC14CVMDECT devboard |
| URL | <https://github.com/funkeleinhorn/sc14cvmdect-devboard> |
| Revision | `main`, commit `1e5ffbd8f1b2c45f256a95375aff201b5552f03a` |
| License | CERN-OHL-S-2.0 |
| Target | open-hardware KiCad devboard for the SC14CVMDECT module |
| Relevant files | KiCad schematic/PCB, audio header, `README.md` |
| Verified facts | open-hardware devboard for the SC14CVMDECT module from Renesas/Dialog; has an audio header; links to reDECTed documentation |
| Transferable | related-module hardware reference and connector/audio-header ideas |
| Limitations | different module and different board; not a FRITZ!Box 7530 schematic; no SC14448 pin proof |
| Related questions | Q30, Q31 |
| Priority | P3 — hardware analogy only |

### R8c — GCC CR16 backend

| Field | Value |
|---|---|
| Name | GNU Compiler Collection CR16 backend |
| Source | <https://sources.debian.org/src/gcc-arm-none-eabi/15%3A8-2019-q3-1/gcc/config/cr16/>; files `cr16.h`, `cr16.md`, `cr16.c`; modern `gcc-mirror/gcc` master did not contain `gcc/config/cr16` at `a74179d08523b1028479752dba7d321bcdb01d81` |
| Revision | GCC 8 source package (not a single Git commit); record package version with any local copy |
| License | GPL-3.0-or-later (GCC source headers) |
| Target | CompactRISC CR16 compiler backend |
| Verified ABI facts | return value in `r0`; argument registers `r2`…`r6`; calls clobber `r0`–`r6`, `ra`, `sp`; `r7`–`r13` are callee-saved; stack grows down; frame pointer `r13`, argument pointer `r12`, return address `ra=r14`, stack pointer `sp=r15`; parameters are pushed/stacked when register slots are exhausted |
| Transferable | ABI cross-check for E3 callsite and callee-clobber reasoning; strong warning that E3's “any pair is an argument” model is not the GCC ABI |
| Limitations | GCC ABI is not proof of AVM firmware convention; the proprietary firmware may use a custom convention; backend is absent from modern GCC master |
| Related questions | Q16, Q17, Q54, Q75 |
| Priority | P1 — E3 soundness cross-check |

### R8d — SC14480A5M / SC14480A2M6 datasheet

| Field | Value |
|---|---|
| Name | SC14480A5M / SC14480A2M6 datasheet |
| File | `reference/hardware/SC14480.pdf` (workspace-relative, outside Git) |
| Manufacturer / revision | SiTel Semiconductor, revision 1.0, 2009-01-21, 259 pages |
| SHA256 | `a0b0300cc0dc50ac98bff4c9021dcbb86ba7b063554f406ac8f65c84a51782d0` |
| License | SiTel datasheet; reference only, not public-licensed content |
| Target | SC14480A5M/A2M6, **not SC14448** |
| Relevant pages | printed p33–34 DIP sequencer/URST; p64 PCM; p131–132 memory map; p171–172 DIP registers; p177 DSP_INT_REG; p196–197 RESET_INT_PENDING_REG |
| Verified facts | DIP RAM `0x01000000–0x010003FF` 512×16, first instruction `0x01000002`; Gen2DSP registers `0x01027F80–0x01027FFF`; `DSP_INT_REG=0x01027FD8`; `0x00FF5402` reset-pending bit 10 DIP / bit 13 DSP; `0x00FF6002` DIP_PC; `0x00FF6006` DIP_CTRL with URST bit 7; `0x00FF6400/6402` BMC_CTRL; PCM is 4×16-bit |
| Transferable | strong structural/functional hypotheses for E3's DIP-RAM fill, `DSP_INT_REG`, `0x80→0` DIP stop/start and the `0x400`/`0x2000` acknowledgements |
| Limitations | SC14480 is a different device; `0x000Fxxxx` vs `0x00FFxxxx` mapping does not transfer; the 511-word payload `0x1001` is not decoded; 4-channel PCM is not the AVM 8-slot frame; no SC14448 proof |
| Related questions | Q16, Q17, Q46, Q54, Q55, Q57, Q74, Q75 |
| Priority | P0 — highest-value related-device reference |

The detailed cross-check is in `sc14480-memory-map.md`.  Printed page
numbers are used there; the physical PDF page is normally one greater.

### R8e — OpenWrt OsmocomDECT patch

| Field | Value |
|---|---|
| Name | `[PATCH] RFC: OSMOCOM DECT stack on OpenWrt` |
| URL | <https://lists.openwrt.org/pipermail/openwrt-devel/2014-June/000225.html> |
| Revision | mailing-list message 000225, 2014-06-26 |
| License | GPL-2.0 in the included driver files |
| Target | OpenWrt kernel 3.10–3.14, com-on-air/SC1442x hardware |
| Verified facts | the message and inline patch are live; the patch adds DECT stack, `sc1442x.c`, firmware assembler source, `dip_opcodes.h` and `com_on_air.h`; it explicitly says the old `dect.osmocom.org` Git tree was empty |
| Transferable | historical DIP/SC1442x implementation and build integration |
| Limitations | not SC14448; not current; no AVM firmware; do not apply to this kernel tree |
| Related questions | Q16, Q54, Q75 |
| Priority | P3 — historical context |

## 2. Source status summary

| Source | Status on 2026-11-09 |
|---|---|
| reDECTed wiki | live; no revision/license stated |
| linux-cr16 | live, commit `9022548…` |
| qemu-cr16 | live, commit `4f9e07e…` |
| regrettableDectable | live, commit `9873460…` |
| SC14CVMDECT PDF | local file, SHA256 recorded |
| OsmocomDECT project/wiki | **NOT VERIFIED** (Anubis) |
| OsmocomDECT OpenWrt patch | live message `000225` |
| OsmocomDECT/Asterisk | **NOT VERIFIED** (Anubis) |
| openD | archived, commit `686fc01…` |
| devboard | live, commit `1e5ffbd…` |
| GCC CR16 | verified via Debian GCC 8 source; not in current GCC master |
| SC14480 datasheet | local file, SHA256 `a0b0300…51782d0`; 259 pages |

When a source changes, update the revision/hash and the corresponding row in
the register/PCM documents; do not silently rewrite the old evidence.
