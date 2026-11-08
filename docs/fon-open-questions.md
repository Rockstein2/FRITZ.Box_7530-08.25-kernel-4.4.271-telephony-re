# FON: open questions

Status: **the only list of unresolved items for this project**

Each item states what the question is, what would close it, and in which
stage.  When an item is closed, move the answer into `fon-known-facts.md`
and delete it here.

Stage names follow `runbook/fon-first-hardware-test.md`:

- **A** — passive collection (no module, no mapping, no IRQ, no DMA)
- **B** — probe-only module load (`probe_only=1`)
- **C** — full MMIO read path (separate approval)
- **D0** — GPIO/reset ownership review (no toggling)
- **E** — DMA / firmware / line (separate project stages)

---

## 1. Runtime facts on *our* kernel

These are things the OEM log or GPL source suggest but which our 6.12/OpenWrt
build must confirm.

| # | Question | Closes with | Stage |
|---|---|---|---|
| Q2 | Which virq is assigned to INTID 188 and 191 on our kernel? | `/proc/interrupts` | A |
| Q3 | Is the DT trigger `IRQ_TYPE_LEVEL_HIGH` what the GIC actually reports? | `/sys/kernel/irq/*/trigger` or `debugfs` | A |
| Q4 | Is the TDM frame sync (8 kHz) actually present when the SC14448 runs under OpenWrt? | read-only TLMM software probe under a `CONFIG_DEVMEM=y` test kernel (C0+), or passive scope/logic analyser; the software probe observes only the IPQ4019 input path | A / bench |
| Q5 | Is the bit clock really ~1.025 MHz on this board under OpenWrt? | read-only TLMM software probe with a sample rate comfortably above 4.1 MS/s (C0+), or scope; a low-rate `DETECTED` result is not a frequency | bench |
| Q8 | Do the six register blocks map without conflict? | Stage C | C |

Stage A/B already closed the resource-claim, probe-bind and probe-only IRQ
checks; those results are in `fon-known-facts.md` §9c/§9d.

## 2. Driver and DT correctness

| # | Question | Closes with | Stage |
|---|---|---|---|
| Q9 | Is `qcom,tdm-slots = <8>` the correct frame width for AVM? | GPL says 8 physical slots and the driver uses 8; still unproven under our TDM code. Compare against a full-TDM test | C/E |
| Q10 | Do we need the PCMLINK pinctrl state (FSC/DCL/MCL/DI/DO) for anything beyond probe? | deliberate pinctrl addition + scope | C/E |
| Q11 | Is a normal threaded IRQ adequate, or is FIQ mandatory for mbox3? | C test with IRQ counting | C |
| Q12 | Does the MBOX DMA descriptor layout match `struct _mbox_desc` (156 bytes)? | port review + Stage E | E |

## 3. Reset and GPIO

| # | Question | Closes with | Stage |
|---|---|---|---|
| Q13 | Which net does GPIO40 drive, and what is the polarity at the SC14448 reset pin? OEM 08.25 shows GPIO40 `OUT func=0 val=1`; OpenWrt shows input 0. Direct connection vs inverter is still unknown. | schematic, continuity, or scope on the reset pin | D0 / bench |
| Q15 | Does a GPIO40 reset leave the SC14448 in a state where it will still accept firmware? | D0 plan + measurement | D0 |
| Q77 | How exactly do `dakota_gpio_out_bit()` and `dakota_gpio_pinconfig()` transform their arguments? OEM live readback shows `func` 2/3 for GPIO21/22/23/25/26/27, but GPIO20/24 are `func=0` despite profile values 2/3; MCL handling and the OpenWrt path remain unknown. | recover the function bodies or compare read-only OpenWrt TLMM state with OEM | research / read-only |
| Q81 | What exactly does `dakota_gpio_ctrl(gpio, 0, 0)` change on the pad, and can the AVM `Check_TDMInterface()` sequence be replayed without altering hardware state? | recover the function body or prove the side effects with a reviewed read-only test | research / read-only |

`AVM_DEF_HW_PARAM_GPIO_OUT_ACTIVE_HIGH` is a software convention and does
**not** answer Q13.

## 4. SC14448 behaviour

| # | Question | Closes with | Stage |
|---|---|---|---|
| Q16 | What exactly does the slot-5 control word mean to the SC14448 firmware? | **Linux-side formula fully recovered** (reg48 bits 4-11, reg2c bits 17/18, 0x4000/0x8000 markers, special path reg 0x30). SC14448 semantics still **open**; E0/E1/E2 found no firmware handler, but indirect/IRQ paths remain | E2 / future trace |
| Q17 | What does the slot-5 status word contain besides hook (bit 3)? | **Linux-side mapping recovered**: status 0-3 -> reg44 4-7; 5-8 -> reg44 8-11; 0x8000 no update; 0x4000 updates; zero -> 0xbad00000. Physical meaning of most bits **open**; E2 found no proven status producer | E2 / future trace |
| Q18 | Is the SC14448 firmware required for FON, or only for DECT? | E test with/without firmware | E |
| Q19 | Which SC14448 pins drive the discrete line interface? | schematic / probing | E |

## 5. Line hardware

| # | Question | Closes with | Stage |
|---|---|---|---|
| Q20 | Exact LM324/BCP53-16 topology and component values | schematic | E |
| Q21 | Where is ring voltage generated and how is its cadence controlled? | schematic + measurement | E |
| Q22 | What are the safe limits for any line test? | dedicated high-voltage test plan | E |

## 6. Build and delivery

| # | Question | Closes with | Stage |
|---|---|---|---|
| Q23 | Does a self-built stock initramfs boot on the bench unit? | TFTP boot, `runbook/fon-recovery-ram-boot.md` | bench |
| Q25 | Is the FIT DTB inside the image byte-identical to our prepared probe DTB? | offline FIT extraction + hash | offline |

### Stage C questions (opened 2026-11-07)

| # | Question | How to answer | Stage |
|---|---|---|---|
| Q27 | Does the SC14448 currently emit FSC/BCLK, i.e. is it running? | read-only TLMM software probe (C0+) under a `CONFIG_DEVMEM=y` test kernel, then scope on an identified net. C0 only showed that Linux has no mux owner; it did not read back hardware `FUNC_SEL` and did not prove the line inactive | probe |
| Q28 | Is `GCC_AUDIO_AHB_CLK` required to read the ADSS registers? | C1 with clock enabled, then a controlled negated run | C1 |
| Q34 | Does the audio AHB gate actually close when disabled? | one post-disable `readl()` of `0x181b010` (bit 31 + FSM bits) | C2.2 |
| Q76 | Is `fs_per_dma = 32` correct for the FON `tdm_if_adss_dma_init()` call site? | **still open**: E0 did not recover the closed board table or a runtime value. Do not use 32 as a confirmed OEM value. Needs the 7530 board table or an offline module/board-table reconstruction | E0 / C4 |
| Q74 | Does our dry-run TX frame (`0xfefe` sync words + `0x5555` at slot 4 + control at slot 5) match what `pcmlink.ko` actually sends byte-for-byte? | **partially**: E1 resolved `EOR #2` as a halfword-pair swap; E2 confirmed the same pair swap in `generic_slotinterleave` for audio. Raw DMA memory matches the logical frame; physical wire order and audio sample order/endianness are still unknown | E2 / future trace |
| Q75 | Is the SC14448 genuinely the consumer of the slot-5 control word? | **still open**: E2 added call-continuation, interprocedural, table-consumer and full IRQ analysis but found no proven slot-5 handler; indirect/indexed/stack paths remain | E2 / future trace |
| Q36 | Which SC14448 revision is on HW236 (A or B), and how many audio codecs does it have? | die/package marking, or the exact-variant datasheet | research |
| Q37 | Can FSC/BCLK be measured with a passive GPIO read (no pinmux change)? | **partly answered**: direct read-only TLMM polling avoids the slow shell/sysfs path and needs no pinmux change. The userspace tool is prepared, but stock OpenWrt has `CONFIG_DEVMEM` disabled; the kernel module is the preferred path, with strict one-trigger-per-insmod state, built offline but not loaded. A hardware run has not been done | C0+ / C0+-K |
| Q38 | What does the still-undecoded SC14448 access to `0x00FF600E` configure? (`0x00FF6006` is already known to be pulsed as a trigger.) | decode the `0x00FF600E` writers or obtain the register map | research |
| Q57 | Do `0x000Fxxxx` and `0x00FFxxxx` map to different hardware, or is there an address decode that aliases them? | **still open**: E2 found no new alias proof; `0xFF4000` call propagation is not evidence for `0xFF6006` aliasing | E2 / research |
| Q40 | Which dispatch key reaches the `0x2558` arm? | data-flow across blocks; no symbol table in the image | research |
| Q43 | What does `BIT(7)` of `0x00FF6006` do on the SC14448? | dynamic test once firmware runs (note: the `0x000F6006` writers `0x1348`/`0x145C` are a separate register) | D |
| Q44 | How does the encoded 20-bit absolute field translate into the effective bus address that the SC14448 actually uses? The field encoding is known; the hardware translation and possible `0x000Fxxxx`/`0x00FFxxxx` alias are not (see Q57). | a SC14448 bus/memory map, a bus trace, or a controlled read-back | research |
| Q53 | What do the 11 230 decoded instructions not reached from `0x1602` contain — code reachable only through an unfound dispatch, or data decoded as code? | **still open**: E2 restored call continuations and cross-call summaries, but indirect/indexed paths and data/code ambiguity remain | E2 / offline |
| Q54 | Does an indirect dispatch exist that no site currently reveals (table built at run time, or read from RAM initialised by the loader)? | **still open**: E2 examined 382/396 indirect sites and 87/78 consumer candidates, but proved no table base/index/consumer chain and no PCM dispatcher | E2 / offline |
| Q55 | Can the address written at `0x25D0` (`0x01000000 + 2·index`) be resolved far enough to decide whether any other instruction reads the same area? | **still open**: E2 found no resolved reader or cross-call base propagation; the region is a loader/RAM-init candidate, not a named PCM buffer | E2 / offline |
| Q56 | Is `0x000F6006` bit 7 a start strobe, and does `0x000F6002` go to 1 because of it? | **restated**: `0x2558` pulses `0x00FF6006`, not `0x000F6006`, and the two are not proven to alias. Hardware observation only (see `runbook/fon-dialog-hw-test-plan.md`) | D |
| Q52 | Is `0x000F6002` a status register whose value 1 means "ready", and which event sets it? | no L5 observation; the loop at `0x25FAE` has no timeout | D |
| Q46 | Is `0x01000000` the PCM buffer, and what does `0x1001` mean? | **still open**: E2 kept 511 indexed writes with no resolved reader and classified the region as loader/RAM-init candidate. Do not call it a PCM buffer | E2 / research |
| Q50 | The CR16A manual puts `cc` in bits 8..5 and `d1..d4` in bits 4..0, binutils uses bits 7..4 and 3..0. Which does the SC14448 core use? | **evidence for binutils**: assembler round trip (condition changes never move the displacement), 7 807 firmware matches over both images, the reachable set from `0x1602` is coherent; the CR16C/B manuals could not be read offline | offline |
| Q47 | Does the hardware reset sequence fetch its entry from the exception table at `INTBASE = 0x24`, or jump directly to a fixed address? The table itself is found (31 entries); its runtime use is not proven. | reset-vector documentation, a bus trace, or a controlled capture | research |
| Q39 | What electrical level reaches the SC14448 reset pin under OpenWrt, and is it asserted? OEM shows GPIO40 high/out; OpenWrt shows input 0. The pad state is known on both sides, the SC14448-side level is not. | establish the net/polarity first, then passive simultaneous observation; no toggle without separate approval | D / bench |
| Q29 | What is the real trailer format of the AVM firmware images? | analysis of `firmware/*.hex` blocks after the last payload | D0 |
| Q30 | Is the analog FON usable without the AVM DECT userspace? | **still open**: E0 found no UART/SPI/I2C/GPIO alternate FON control path; the only recovered path is PCMLINK/TDM slot 5. A future firmware/hardware experiment is required | E0 / future bench |
| Q31 | Which physical PCM group is wired to the SC14448, and what will the TLMM `FUNC_SEL` be under OpenWrt? OEM live readback shows a mixed group: GPIO21/22=2, GPIO23/25/26/27=3, GPIO20/24=0. PCB connectivity and the OpenWrt state remain unknown. | read-only TLMM readback plus software edge observation (C0+) narrows the live group, but continuity to an identified net or passive waveform evidence is still needed for the physical answer | probe |
| Q32 | Does the console UART tolerate a userspace uploader without corrupting the stream? | C-controlled test with `quiet loglevel=0` | D |
| Q33 | What are the SC14448 boot reply timings on this unit? | measurement during a controlled handshake | D |

### OEM DTB, UART and pad provenance (opened 2026-11-08)

| # | Question | How to answer | Stage |
|---|---|---|---|
| Q79 | How are the console and `msm_dectuart_*` arbitrated on the shared `blsp_uart0` controller, and can a Dialog upload coexist with console traffic? | review `msm_serial.c`/loader ownership, then a controlled test | D0 / bench |
| Q80 | Which of the three HW236 DTBs in `kernel.image` does the OEM bootloader select? The board subrevision is now known to be `2` from the OEM 08.25 capture, and the first blob matches it; bootloader selection itself is still not observed. | bootloader selection code or a capture of the chosen DTB | research |

## 7. Explicitly out of scope

DECT, ISDN, CAPI, DSL.  Not needed for one FXS port; recorded in
`history/fon-feasibility.md`.

---

## How this list interacts with the other documents

- `fon-known-facts.md` — answers that are settled.
- `fon-go-no-go.md` — which of the above must be closed before a given
  hardware stage is allowed.
- The remaining `docs/fon-*.md` files — historical analysis, marked as such.
  They may still contain `UNVERIFIED` markers for things already answered
  here; **this file wins**.

## 8. Opened by PERIPH-2.1 (2026-11-07)

| # | Question | Closes with | Stage |
|---|---|---|---|
| Q58 | Do the two `RESOLVED` rows flagged "outside the known internal ranges" (`0x173A4`, `0x17D80` in normal) sit in a region that is data rather than code? | classify instruction blocks as code/data by reachability and entry evidence; the flag is already in the report note | offline |
| Q59 | Is there a cross-block dataflow that would let a base loaded in one block be used in the next (currently always `UNKNOWN`)? | merge-on-all-predecessors analysis over the CFG, with the same conservative default | offline |
| Q60 | Should `pop`/`popret` (and `push`, for SP) count as writes to their register list? Today they report no written registers. | decode the register list in the operand and add it to `written_registers`; harmless today because blocks never carry state across a `pop`, but needed before any inter-block analysis | offline |
| Q62 | What does `CFG` bit 8 control? The first-level image clears it early and sets it before a hand-over wait; the second-level image sets it at start-up. | a CR16C `CFG` description; it must **not** be assumed to control address decoding | research |
| Q63 | What are the contents of the dispatch table at `INTBASE = 0x24` when the firmware runs, and where does the copy at `0x15F6` put them? | resolve `(r3,r2)` at `0x15F6`, or read the table on hardware | offline / D |
| Q64 | Is `0x15AA`/`0x102C` the reset entry? | the reset vector in the first-level image or a vector-table read | research |
| Q67 | Is `0x10080` RAM that survives, or does the second-level image run in a different memory? | memory map of the device; no offline source | research |
| Q68 | **narrowed**: `normal` clears `[0x936C, 0x9C5E)`, ending exactly at the next block; `p2test` clears `[0x94A4, 0x9B43)`, one byte short of the next block at `0x9B44` (all blocks start even).  Classic `.bss`, no memory map to confirm it | a SC14448 map | research |
| Q70 | Which SC14448 sources raise vectors 24, 26 and 29?  The SC14441 names (tim1/dip/dsp) do not fit three `0x5402` pending bits | a SC14448 interrupt chapter, or a capture of the pending bits | research |
| Q71 | Is `CFG` bit 8 really "32-bit exception table format"?  The reference says so; no SC14448 document confirms it | a CR16C `CFG` description | research |
| Q72 | Does the second-level start-up program a PLL?  `0x00FF4010` (`CLK_PLL_CTRL_REG`) is read-modify-written at `0x1896` | a clock-tree description, or a measurement of the resulting clock | research |
| Q69 | Is `0x10080` the CPU execution entry, or only the image load address? | ROM boot description or the loader's entry mechanism | research |
| Q61 | What exactly do `loadm`/`loadmp`/`storm`/`stormp` address (base register, register list semantics, post-increment)? | CR16B/C manual, or an assembler round trip for the register-list operand form; until then they stay `MEMORY_UNSUPPORTED` (16 + 2 instructions) | offline |
