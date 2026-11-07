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
| Q1 | Does anyone already claim `0x07700000`-`0x077fffff` in `/proc/iomem`? | Stage A snapshot | A |
| Q2 | Which virq is assigned to INTID 188 and 191 on our kernel? | `/proc/interrupts` | A |
| Q3 | Is the DT trigger `IRQ_TYPE_LEVEL_HIGH` what the GIC actually reports? | `/sys/kernel/irq/*/trigger` or `debugfs` | A |
| Q4 | Is the TDM frame sync (8 kHz) actually present when the SC14448 runs under OpenWrt? | passive scope/logic analyser | A / bench |
| Q5 | Is the bit clock really ~1.025 MHz on this board under OpenWrt? | scope | bench |
| Q6 | Does the FON DT node bind with `stage=0x23` and `mode=probe-only`? | Stage B | B |
| Q7 | Does our driver stay at `irq=-1` in probe-only on real hardware? | Stage B diagnostics | B |
| Q8 | Do the six register blocks map without conflict? | Stage C | C |

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
| Q13 | Which net does GPIO40 actually drive, and with what polarity? | schematic or scope on the reset pin | D0 / bench |
| Q14 | Is GPIO40 claimed by any driver in our DT? | Stage A `pinctrl`/`gpio` dump + review | D0 |
| Q15 | Does a GPIO40 reset leave the SC14448 in a state where it will still accept firmware? | D0 plan + measurement | D0 |

`AVM_DEF_HW_PARAM_GPIO_OUT_ACTIVE_HIGH` is a software convention and does
**not** answer Q13.

## 4. SC14448 behaviour

| # | Question | Closes with | Stage |
|---|---|---|---|
| Q16 | What exactly does the slot-5 control word mean to the SC14448 firmware? | firmware analysis / trace | E |
| Q17 | What does the slot-5 status word contain besides hook (bit 3)? | trace | E |
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
| Q24 | Does our probe-only initramfs boot and reach a shell? | same | **answered: yes, 2026-11-07** |
| Q25 | Is the FIT DTB inside the image byte-identical to our prepared probe DTB? | offline FIT extraction + hash | offline |
| Q26 | Is `FRITZ7530.bin` the file name this bootloader expects (vs `FRITZ7520.bin`)? | bench observation | **answered: yes, 2026-11-07** |

### Stage C questions (opened 2026-11-07)

| # | Question | How to answer | Stage |
|---|---|---|---|
| Q27 | Does the SC14448 currently emit FSC/BCLK, i.e. is it running? | scope measurement, `fon-tdm-passive-test.md`; C0 already proved the ADSS pads are not muxed, so Linux cannot see them | probe |
| Q28 | Is `GCC_AUDIO_AHB_CLK` required to read the ADSS registers? | C1 with clock enabled, then a controlled negated run | C1 |
| Q34 | Does the audio AHB gate actually close when disabled? | one post-disable `readl()` of `0x181b010` (bit 31 + FSM bits) | C2.2 |
| Q35 | Which TX/RX port pairing does the FON need (AVM uses 3 for TX, our node uses 0)? | C3 comparison against `pcmlink.ko` | C3 |
| Q36 | Which SC14448 revision is on HW236 (A or B), and how many audio codecs does it have? | die/package marking, or the exact-variant datasheet | research |
| Q37 | Can FSC/BCLK be measured with a passive GPIO read (no pinmux change)? | **the shell method is too slow** (process per sample, GPIO subsystem); a kernel edge counter validated against a known signal is required | C0+ |
| Q38 | Do the SC14448 firmware PCM accesses (0xFF6006/0xFF600E) reveal the slave clock format? | **answered for 0xFF6006**: the function at `0x2558` writes `0x80` and then clears it to `0`, so it is a trigger, not a format; `0xFF600E` not decoded | research |
| Q40 | Which dispatch key reaches the `0x2558` arm? | data-flow across blocks; no symbol table in the image | research |
| Q39 | Is the SC14448 currently held in reset (GPIO40 = 0, pad is input)? | release GPIO40 under explicit approval and re-run the pin probe | D |
| Q29 | What is the real trailer format of the AVM firmware images? | analysis of `firmware/*.hex` blocks after the last payload | D0 |
| Q30 | Is the analog FON usable without the AVM DECT userspace? | run boot firmware, then speak slot 5 | E |
| Q31 | Which mux group is live on HW236, PINMUX2 or PINMUX3? | **partly answered**: C0 shows every PCM pin unclaimed by Linux, so neither group is driven by software; the board wiring itself is still unknown | probe |
| Q32 | Does the console UART tolerate a userspace uploader without corrupting the stream? | C-controlled test with `quiet loglevel=0` | D |
| Q33 | What are the SC14448 boot reply timings on this unit? | measurement during a controlled handshake | D |

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
