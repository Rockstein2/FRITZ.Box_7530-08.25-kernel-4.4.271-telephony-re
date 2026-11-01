# Analysis tools

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

See `docs/fon-pcmlink-register-path.md` for the recovered call graph and the
confidence labels.
