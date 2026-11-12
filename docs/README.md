# FON documentation — current, reference, runbooks, history

E3.2.1: `fon-e32-summary.md` records the unified memory-operand classifier,
strict E2 proof matching, staged fail-closed report publication and DIP fill
provenance. The offline CR16 binutils build resides outside Git at
`../work/cr16/build/binutils/objdump`; address-form replay compares all five
fresh JSON files with committed reports (no persistent replay directory).

This index is current. Documentation has four strict layers plus an external
bibliography:

1. `docs/` — current status and decisions;
2. `docs/reference/` — primary captured data that stays valid over time;
3. `docs/runbook/` — reproducible procedures;
4. `docs/history/` — detailed analysis and superseded reasoning.

Do not use a file under `history/` as the current project status. If current
files disagree with a runbook or historical report, the current files win. A
runbook controls procedure, not interpretation. A reference capture records
what the hardware actually emitted; it is evidence, not a summary.

The external workspace layout is documented locally in `../WORKSPACE.md`
(outside Git): `reference/`, `evidence/`, `restore/`, `backups/`, `work/`,
`builds/`. Small sanitized evidence stays in `docs/reference/` in Git.
Verify the canonical layout and all SHA256 manifests with
`sh tools/verify-workspace.sh`.

## Layer 1 — current truth (`docs/`)

| File | What it is |
|---|---|
| `fon-known-facts.md` | Every confirmed fact with its evidence class. **Start here.** |
| `fon-open-questions.md` | Every unresolved item and the stage that closes it. The only open-questions list. |
| `fon-go-no-go.md` | Which questions must be closed before each hardware stage. |
| `fon-d06-summary.md` | Current GPIO40/reset, PINMUX2/3, OEM-DTB and SC14448 startup result. |
| `fon-adss-clock-reset.md` | What gates ADSS register access: GCC audio clocks, the audio reset, and what AVM does. |
| `fon-dialog-minimal-loader.md` | Minimal SC14448 boot-firmware loader: design, UART sharing, blockers. |
| `fon-tdm-control-only-plan.md` | Control-only TDM plan; no DMA yet. |
| `fon-e0-summary.md` | E0 SC14448/PCMLINK slot-5 research summary and evidence boundary. |
| `fon-sc14448-pcmlink-protocol.md` | Reconstructed slot-5 TX/RX protocol, confidence and caveats. |
| `fon-e1-summary.md` | E1 cross-block dataflow, indirect search and DMA byte-order result. |
| `fon-e2-summary.md` | E2 interprocedural analysis, table consumers, IRQ callgraphs and slot-5 boundary. |
| `fon-e3-summary.md` | E3 proof audit, corrected table/IRQ reporting, dsp/dip traces and `0x01000000` boundary. |
| `fon-e32-summary.md` | E3.2 audit fixes, CR16 abs20 expansion, Q57 resolution and DIP payload evidence. |
| `fon-e33-summary.md` | E3.3 bounded DIP fill/bring-up and DIP/DSP IRQ traces, provenance and remaining limits. |
| `fon-e34-summary.md` | E3.4 DIP writer/value formulas, possible 512-word model, local CR16 loop count and checked CFG order. |
| `fon-e35-summary.md` | E3.5 PCM ingress register inventory, Linux control/status signatures and explicit Q75 source-to-sink boundary. |
| `sc14448-e4-summary.md` | E4 bounded function map, verified ISR vectors, runtime queue/command parser and UART TX with host RX boundary. |
| `sc14448-e41-summary.md` | E4.1 local software queue producer, item header/payload offsets, command13 pointer write and TX/host boundary. |
| `sc14448-e42-summary.md` | E4.2 allocator tag slicing, state/tag distinction and unresolved parser-branch reachability. |
| `sc14448-e43-summary.md` | E4.3 conditional case effects, first case-9 indirect target and version differences; no invented runtime command path. |
| `sc14448-e44-summary.md` | E4.4 TX-buffer adjacency, p2test byte writer, architectural register accesses and unresolved ingress/command links. |
| `sc14448-e5-summary.md` | E5 Gen2DSP/PCM+/CODEC audio path: guarded `[0xD6]` DSP window, embedded DSP program (`0x17300` → PC `0x7980`), PCM master/slave config, CODEC analog order, DIP-coupled timing and the standalone readiness inventory. |

### External reference registry (`references/`)

This is a bibliography/evidence index, not the primary OEM capture in
`reference/`.  It records external Dialog/CR16/DECT material without adding
third-party PDFs or source trees to Git.

| File | What it is |
|---|---|
| [`references/README.md`](references/README.md) | Policy, status labels and navigation |
| [`references/dialog-external-sources.md`](references/dialog-external-sources.md) | URL/revision/license registry for all external sources |
| [`references/dialog-register-cross-reference.md`](references/dialog-register-cross-reference.md) | SC14CVMDECT PDF registers vs SC14448 firmware accesses |
| [`references/dialog-pcm-comparison.md`](references/dialog-pcm-comparison.md) | PCM timing/mode comparison; no settings transfer |
| [`references/sc14480-memory-map.md`](references/sc14480-memory-map.md) | SC14480 memory map, DIP RAM, DSP_INT_REG and address-space cross-check |
| [`references/fon-e3-reference-opportunities.md`](references/fon-e3-reference-opportunities.md) | Ranked use of references for the next E3 work |

Evidence classes used by `fon-known-facts.md`:

| Class | Meaning |
|---|---|
| **GPL** | from the published GPL source tree |
| **DT** | from the board device tree in this repository |
| **OEM-DTB** | from the compiled HW236 tree extracted from FRITZ!OS 08.25 `kernel.image` |
| **OEM** | observed in `history/wiki-fritzos-oem-bootlog-reference.txt` |
| **OEM-CAPTURE** | observed in `reference/oem-08.25-boot/` — OEM FRITZ!OS 08.25 on this board, captured 2026-11-08 |
| **DISASM** | recovered from a proprietary AVM binary; file/function/address cited |
| **OFFLINE** | computed from an image or report without touching hardware |
| **EXT-REF** | external datasheet, tool or related-device source; the device is named on each row |
| **RUNTIME-RO** | observation through read-only interfaces: console, `/proc`, sysfs or debugfs; no module load and no intentional GPIO/MMIO writes. A debugfs read is not proof of zero hardware side effects |
| **HW-TEST** | controlled hardware execution: test-image boot, module load, clock/reset/MMIO writes, or a bench measurement requiring explicit authorisation |
| **CONFIRMED / INFERRED / UNKNOWN / DISPROVED** | truth status; source class and truth status are separate, and static evidence is never promoted to hardware proof |

## Layer 2 — primary reference (`reference/`)

Captured data. Never summarize it away; keep the original content.

| File | What it is |
|---|---|
| `reference/oem-08.25-boot/rx.log` | OEM FRITZ!OS 08.25 text RX capture; identifiers redacted and binary shared-UART blocks summarized |
| `reference/oem-08.25-boot/tx.log` | OEM shell TX command stream |
| `reference/oem-08.25-boot/SHA256SUMS` | Hashes of the repository copies |
| `reference/oem-08.25-boot/README.md` | Provenance, hashes, redaction policy and key OEM-side lines |

## Layer 3 — runbooks (`runbook/`)

Procedures and build records. Executable, dated, not arguments.

| File | What it is |
|---|---|
| `runbook/fon-first-hardware-test.md` | Stage A/B probe-only procedure |
| `runbook/fon-recovery-plan.md` | Recovery policy and stop conditions |
| `runbook/fon-recovery-ram-boot.md` | RAM-only TFTP boot (no NAND writes) |
| `runbook/fon-test-image-safety.md` | Rules for a test image |
| `runbook/fon-test-image-build.md` | Preparing the probe-only DTB/image |
| `runbook/fon-build-validation.md` | Build, test and artifact results |
| `runbook/fon-stage-c1.md` | Stage C1 ADSS MMIO read plan (currently NO-GO) |
| `runbook/fon-stage-d0-uart-identification.md` | Board UART identification procedure |
| `runbook/fon-stage-d05-pcm-net-identification.md` | Finding the PCM net and probing FSC/BCLK |
| `runbook/fon-stage-d06-readonly.md` | Read-only GPIO40/TLMM/OpenWrt state collection; no writes |
| `runbook/fon-oem-dtb-extraction.md` | Offline extraction of the compiled HW236 DTB from EVA/LZMA |
| `runbook/fon-dialog-hw-test-plan.md` | SC14448 bench plan (procedure form) |
| `runbook/fon-dialog-uart-sniff-plan.md` | UART boot-sniff plan |
| `runbook/fon-tdm-passive-test.md` | Passive FSC/BCLK measurement and pin candidates |
| `runbook/fon-stage-c0plus-software-clock-probe.md` | Read-only TLMM software TDM clock probe; prepared, never executed |
| `runbook/fon-stage-c0plus-kernel-probe.md` | K1 load/unload + K2 one-shot kernel TLMM probe; prepared, never loaded |

## Layer 4 — history (`history/`)

The reasoning trail. Many files still say `UNKNOWN` about questions that have
since been answered; each carries a historical banner. Read them for
provenance, never as status.

### D0.5 / D0.6 evidence

| File | Subject |
|---|---|
| `history/fon-d05-pcm-net-identification.md` | Physical PCM-net identification analysis |
| `history/fon-d06-dect-reset-path.md` | Instruction-level GPIO40 reset reconstruction |
| `history/fon-d06-pcm-pinmux.md` | PCMLINK pinmux and TLMM register derivation |
| `history/fon-d06-sc14448-startup-sequence.md` | Detailed SC14448 startup reconstruction |
| `history/fon-d06-inverter-hypotheses.md` | Explicitly unproven inverter alternatives |

### ADSS / TDM / SC14448

| File | Subject |
|---|---|
| `history/fon-adss-avm-init-sequence.md` | AVM's ADSS/TDM order and register table |
| `history/fon-adss-tdm-channel-map.md` | ADSS channel and port mapping |
| `history/fon-audio-ahb-clock-warning.md` | AHB clock warning on disable; what remains unproven |
| `history/fon-tdm-clock-software-check.md` | Corrected Piglet 100 ms boot algorithm and separate pcmlink diagnostic; C0+ probe design |
| `history/fon-c0plus-offline-validation.md` | C0+/R1 timing correction, gap tests, cross-build, kernel module and stock-image blocker |
| `history/fon-c0plus-kernel-safety-review.md` | Final offline safety review, K1/K2 readiness and hardware-unverified risks |
| `history/fon-c0plus-kernel-build-report.md` | Kernel 6.12.112 build identity, vermagic, module SHA256 and ABI caveats |
| `history/fon-c0plus-k1-hardware-result.md` | K1 preflight result; hardware load/unload BLOCKED / NOT RUN |
| `history/fon-tdm-hardware.md` | TDM/ADSS frame parameters and register map |
| `history/fon-pcmlink-register-path.md` | Recovered register path (slot 5, `TxDMA`/`PutRxDMA`) |
| `history/fon-e0-tx-control-reconstruction.md` | TX slot-5 formula, markers, command timing and EOR caveat |
| `history/fon-e0-rx-status-reconstruction.md` | RX slot-5 status-to-register-0x44 mapping |
| `history/fon-e0-analog-state-machine.md` | `slics_reset`, ring, hook, line-state dispatch |
| `history/fon-e0-sc14448-firmware-search.md` | Bounded search for a firmware slot-5 handler |
| `history/fon-e0-protocol-confidence.md` | E0 confidence matrix and Q16/Q17/Q30/Q74/Q75/Q76 |
| `history/fon-e1-cross-block-dataflow.md` | Conservative CFG dataflow, metrics and provenance |
| `history/fon-e1-indirect-dispatch.md` | Indirect edges, table candidates and vector limits |
| `history/fon-e1-pcm-handler-candidates.md` | PCM candidate regions and Q46/Q55 boundary |
| `history/fon-e1-normal-vs-p2test.md` | Normal/p2test topology and metrics comparison |
| `history/fon-e1-dma-byte-order.md` | EOR #2 raw DMA memory model and remaining wire-order unknown |
| `history/fon-e2-interprocedural-dataflow.md` | Call/return CFG, convergence and function summaries |
| `history/fon-e2-table-dispatch.md` | Table-consumer criterion and indirect dispatch results |
| `history/fon-e2-irq-callgraph.md` | 31-vector IRQ callgraph for both images |
| `history/fon-e2-firmware-handler-search.md` | Expanded slot-5 search and remaining paths |
| `history/fon-e2-loader-vs-pcm-buffer.md` | `0x01000000` loader/RAM-init versus PCM ambiguity |
| `history/fon-e3-dataflow-correctness.md` | Path-sensitive interprocedural soundness and E2 proof audit |
| `history/fon-e3-dsp-irq-reconstruction.md` | `dsp_int`, `0xD6` pointer and helper trace |
| `history/fon-e3-dip-pcm-reconstruction.md` | `dip_int`, `0xF6006`/`0xF5402` trace |
| `history/fon-e3-loader-runtime-boundary.md` | 511-iteration fill range, address space and runtime pointer boundary |
| `history/fon-e32-cr16-addressing.md` | abs20 encoding/expansion evidence, assembler and QEMU checks |
| `history/fon-e32-q57-investigation.md` | Q57 hypothesis table and address-space resolution |
| `history/fon-e32-dip-ram-fill.md` | DIP fill range and `0x1001` opcode candidates |
| `history/fon-e32-dsp-dip-irq-comparison.md` | canonical DSP/DIP IRQ addresses vs SC14480 |
| `history/fon-e32-proof-audit.md` | E3.1 audit fixes and fail-closed proof rules |

### Dialog SC14448 firmware and CR16

| File | Subject |
|---|---|
| `history/fon-dialog-boot.md` | Dialog firmware boot protocol |
| `history/fon-dialog-boot-handoff.md` | Boot handoff chain |
| `history/fon-dialog-boot-memory-map.md` | Firmware memory map |
| `history/fon-dialog-boot-branch-decoding.md` | Boot branch decoding |
| `history/fon-dialog-boot-disps25.md` | `disps25` decoding |
| `history/fon-dialog-address-alias-hypotheses.md` | `0x000Fxxxx` vs `0x00FFxxxx` alias hypotheses; E3.2 resolution banner |
| `history/fon-dialog-board-uart-identification.md` | Board UART identification analysis |
| `history/fon-dialog-copy-helper-28d56.md` | `0x28d56` copy helper |
| `history/fon-dialog-cr16-addressing.md` | CR16 addressing modes |
| `history/fon-dialog-cr16-branches.md` | CR16 branch encoding and validated examples |
| `history/fon-dialog-cr16-cfg.md` | Global CFG, entry points, PCM bring-up chain |
| `history/fon-dialog-cr16-disasm.md` | CR16 disassembly of the PCM function |
| `history/fon-dialog-cr16-register-effects.md` | CR16 register effects |
| `history/fon-dialog-cr16-system-registers.md` | CR16 system registers |
| `history/fon-dialog-cr16-vector-map.md` | CR16 vector map |
| `history/fon-dialog-external-register-map.md` | External register map |
| `history/fon-dialog-ff6006-callgraph.md` | Firmware map and `0xFF6006` function |
| `history/fon-dialog-firmware-pcm.md` | What the firmware programs; immediate decoder |
| `history/fon-dialog-firstlevel-cfg.md` | First-level CFG |
| `history/fon-dialog-init-dependencies.md` | Init dependency chain |
| `history/fon-dialog-low-memory-analysis.md` | Low-memory analysis |
| `history/fon-dialog-pcm-hypotheses.md` | PCM hypotheses |
| `history/fon-dialog-peripheral-init.md` | Peripheral init |
| `history/fon-dialog-peripheral-map.md` | Peripheral map |
| `history/fon-dialog-peripheral-xrefs.md` | Peripheral cross-references |
| `history/fon-dialog-uart-boot-comparison.md` | UART boot comparison |
| `history/fon-dialog-uart-boot-protocol.md` | UART boot protocol |

### Project-level analysis

| File | Subject |
|---|---|
| `history/fon-avm-analysis.md` | AVM kernel modules and call chains |
| `history/fon-feasibility.md` | Original standalone-driver feasibility study |
| `history/fon-hardware.md` | Hardware architecture, SLIC/PHY identification |
| `history/fon-control-path.md` | Dialog SC14448 control-path hypothesis |
| `history/fon-dialog-dependency.md` | Dialog dependency assessment |
| `history/fon-dialog-hardware-test-plan.md` | SC14448 bench plan (historical form) |
| `history/fon-linux612-port.md` | Porting notes for Linux 6.12 |
| `history/fon-resource-audit.md` | Probe-safety audit |
| `history/fon-oem-bootlog-crosscheck.md` | What the OEM boot log proves |
| `history/wiki-fritzos-oem-bootlog-reference.txt` | **Reference only**: OEM FRITZ!OS boot log |

### About the OEM boot log

`history/wiki-fritzos-oem-bootlog-reference.txt` is a boot log from **the
original AVM FRITZ!OS firmware**, published on the OpenWrt Wiki page for the
7530 (it is not from OpenWrt and not from this project's hardware). It is
kept purely as a reference for comparison: driver names, TDM clocks, GPIO
assignments and boot order.

Limits when using it:

- the log is from kernel **4.4.60**, not 4.4.271 and not 6.12;
- its FRITZ!OS build could not be confirmed as 08.25;
- it describes FRITZ!OS behaviour, not our driver;
- it must not be treated as evidence about our build;
- it contains the original reporter's MAC addresses, which are not ours.

Where it settles a question, the answer is copied into `fon-known-facts.md`
with the evidence class **OEM**. Nothing else in this repository should cite
the log directly.

## Regenerating structure and links

```sh
sh tools/docs-restructure.sh             # move files into layers (git mv), idempotent
sh tools/docs-rewrite-links.sh           # fix cross-document links, idempotent
sh tools/docs-add-historical-banner.sh    # refresh layer banners, idempotent
```
