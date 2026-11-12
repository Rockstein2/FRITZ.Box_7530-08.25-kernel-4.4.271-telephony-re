# Analysis tools

| Script | Purpose |
|---|---|
| `pcmlink_regs.py` | ELF/register analysis for `pcmlink.ko` (read-only) |
| `cr16_dataflow.py` | Conservative cross-block CR16 register dataflow and reports |
| `cr16_interproc.py` | Interprocedural summaries, table-consumer candidates and IRQ callgraphs |
| `cr16_e3.py` | E3 proof audit, focused dsp/dip traces and handler boundary reports |
| `cr16_address_spaces.py` | E3.2 address forms, abs20 expansion, Q57 conflict and DIP-fill reports |
| `fon-tlmm-clock-probe/` | Read-only TLMM input probe (userspace + one-shot kernel module); offline-only until approved |
| `tests/test_cr16_address_spaces.py` | abs20/abs24 forms, extension rule, Q57 and DIP-fill reports |
| `tests/test_oem_tdm_timing.py` | Numerical proof of the Piglet 100 ms and PCMLINK 195 ms windows |
| `fon-slot5-protocol/` | Offline slot-5 control encoder/status decoder and golden vectors |
| `build-fon-openwrt.sh` | Clean package rebuild in the target SDK |
| `build-fon-dts-test.sh` | Compile the standalone FON DTS |
| `prepare-fon-openwrt-tree.sh` | Install the package and apply DT patches 900/901 |
| `prepare-fon-image.sh` | Prepare a tree and compile the board DTB (no image) |
| `record-fon-artifact.sh` | Record `.ko`/`.apk` hashes into the bench kit |
| `docs-restructure.sh` | Move `docs/` into known-facts / runbook / history |
| `docs-rewrite-links.sh` | Fix cross-document links after a move |
| `docs-add-historical-banner.sh` | Add layer banners to documents |

All scripts are idempotent unless stated otherwise, and none of them touches a
router.

`pcmlink_regs.py` is an analysis-only ELF helper. It never loads or executes a
kernel module. It prints symbols, relocations, PC-relative literals and ARM
instructions for `modules/ubik2/pcmlink.ko`.

Setup:

```sh
python3 -m venv .venv-analysis
.venv-analysis/bin/pip install -r tools/requirements.txt
```

Examples:

```sh
.venv-analysis/bin/python tools/pcmlink_regs.py \
  --module modules/ubik2/pcmlink.ko --list 'pcmlink_ul'

.venv-analysis/bin/python tools/pcmlink_regs.py \
  --module modules/ubik2/pcmlink.ko --disasm lpcmlink_ul_writeregister

.venv-analysis/bin/python tools/pcmlink_regs.py \
  --module modules/ubik2/pcmlink.ko --disasm TxDMA --length 0x400

.venv-analysis/bin/python tools/pcmlink_regs.py \
  --module modules/ubik2/pcmlink.ko --metadata

.venv-analysis/bin/python tools/pcmlink_regs.py \
  --module modules/ubik2/pcmlink.ko --xrefs FPGALink_SharedMemory
```

See `../docs/history/fon-pcmlink-register-path.md` for the recovered call graph and the
confidence labels.
# FON-E3.4 offline analysis

SC14448-E4: `python3 tools/cr16_architecture.py` regenerates nine
`reports/cr16-e4-*.json` from SHA-checked firmware, verified vector bytes,
the converged cross-block dataflow and bounded CFG traversal. Function
ends/matches are local candidates; the queue-item parser is **not** claimed
to receive UART bytes. Run `python3 tools/tests/test_cr16_architecture.py`
for fresh replay and fail-closed preservation, and the function-map,
UART-runtime, and state-graph fixture scripts. No firmware execution.

SC14448-E4.1: `python3 tools/cr16_queue_trace.py` regenerates ten staged
`reports/cr16-e41-*.json` from verified firmware/oracle. The analysis
finds a local software queue allocator and distinguishes 4-byte item
headers from parser payload-relative offsets. `test_cr16_queue_trace.py`
checks fresh replay and fail-closed preservation; command/TX tests protect
against unsupported pointer-range, host-ingress and response claims.

SC14448-E4.2: `python3 tools/cr16_queue_provenance.py` regenerates six
`reports/cr16-e42-*.json`; `python3 tools/tests/test_cr16_queue_provenance.py`
tests synthetic tag sources, call clobbers and fresh replay/rollback.
`TAG_23_EXCLUDED_UNDER_MODEL` applies only at a direct allocator call,
**not** to the parser after unknown header aliases or queue wrap.

SC14448-E4.3: `python3 tools/cr16_command_effects.py` regenerates seven
`reports/cr16-e43-*.json`, gated by E4.2's unresolved parser provenance.
`test_cr16_command_effects.py` tests first indirect JAL and clobbers; the
state-transition test keeps conditional edges separate from runtime proof.

FON-E3.5: `python3 tools/cr16_pcm_ingress.py` regenerates the seven
`reports/cr16-e35-*.json` candidate/proof-boundary inventories from both
SHA-checked images. `cr16_fon_ctrl_trace.py` shares the same fail-closed
bundle. The tool does not execute firmware; related-device register names
are hypotheses. `python3 tools/tests/test_cr16_pcm_ingress.py` checks
fresh-directory replay and preservation on missing inputs/NON_CONVERGED.
`test_cr16_fon_ctrl_trace.py` exercises Linux bit formulas and proof gates.
Neither tool establishes a FON slot-5 consumer.

`cr16_dip_program.py` reads both SHA256-checked firmware images through the
local CR16 objdump and produces seven staged, fail-closed reports:
`reports/cr16-e34-*.json`. It never executes firmware or contacts hardware.
Run `python3 tools/tests/test_cr16_dip_program.py` for synthetic boundaries,
NON_CONVERGED rejection and fresh-directory JSON replay. External CR16B,
GCC and OsmocomDECT references remain under `../work/cr16/references/`,
outside Git. The analysis proves only a local 511-store model; unknown
writers/interrupts prevent an all-path or final-program claim.
