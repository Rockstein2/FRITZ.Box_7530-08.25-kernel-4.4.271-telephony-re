# Analysis tools

| Script | Purpose |
|---|---|
| `pcmlink_regs.py` | ELF/register analysis for `pcmlink.ko` (read-only) |
| `fon-tlmm-clock-probe/` | Read-only TLMM input probe (userspace + one-shot kernel module); offline-only until approved |
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
