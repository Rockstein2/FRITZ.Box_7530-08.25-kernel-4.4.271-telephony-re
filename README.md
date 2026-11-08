# FRITZ!Box 7530 telephony/DECT reverse-engineering set

Source firmware: FRITZ!OS 08.25, kernel 4.4.271, ARMv7.
Target router: OpenWrt 25.12.6, kernel 6.12.112, ARMv7.

The modules are preserved unchanged. `SHA256SUMS` records their hashes.

## Dependency chain

```text
Piglet_noemif.ko + DECT firmware
        |
        +-- initializes the DECT chip over AVM/QCOM UART and GPIO

pcmlink.ko
        +-- avm_dect.ko
        |       +-- dect_io.ko -> /dev/dect_io -> dect_manager
        |       +-- nlaudio.ko (optional audio/netlink interface)
        |
        +-- isdn_fbox_fon5.ko -> /dev/capi20 / CAPI
        +-- capi_codec.ko
        +-- krtp.ko (optional RTP acceleration)
        +-- ulpcmlink.ko (optional remote PCM transport)
```

## Recommended reverse-engineering order

1. **Piglet_noemif.ko** — 51 KB, 32 exported symbols. Hardware/firmware loader. It exposes the DECT UART/GPIO protocol and loads the included first/second-level firmware. High priority, moderate complexity.
2. **dect_io.ko** — 14 KB, 16 exported symbols. Small character-device adapter between `dect_manager` and `avm_dect`. Best first module to decompile and document, but it cannot operate alone.
3. **pcmlink.ko boundary** — 251 KB, 560 exports. Document its public API and QCOM TDM/DMA calls before attempting a reimplementation. This is the main hardware/audio blocker.
4. **avm_dect.ko** — 285 KB, 625 exports. Contains the DECT stack and talks to `pcmlink`; large but symbol-rich and not stripped.
5. **isdn_fbox_fon5.ko** — 647 KB, 1410 exports. CAPI, analog FON and call-routing core. Very high complexity.
6. **capi_codec.ko** — 299 KB, 519 exports. Codec/DSP layer; defer until signaling and device access work.

The following are not required for the first DECT-control experiment:

- `krtp.ko`: kernel RTP acceleration; userspace RTP may replace it.
- `ulpcmlink.ko`: remote PCM transport.
- `nlaudio.ko`: auxiliary netlink audio bridge.

## Analysis status

Phase 1 (`dect_io`) and Phase 2 (Piglet loader) are complete. The boundary
analysis now also covers `avm_dect`, `pcmlink` and the host-side `gPcmroute`
layout:

```text
notes/dect_io.md                  /dev/dect_io ABI and queue behavior
notes/piglet.md                   DECT UART loader, HEX framing, firmware patch
notes/avm_dect.md                 DECT/PCM/control boundary
notes/pcmlink.md                  QCA TDM/DMA and slot boundary
notes/pcmlink-sharedmem.md        gPcmroute and DSP-descriptor map
include/*.h                       reconstructed ABI/layout headers
src/mock/                         userspace-only mocks (40 tests)
reports/pcmlink-sharedmem.txt     raw shared-memory evidence
```

The remaining blockers are the vendor `tdm_if_*` implementation/DMA
descriptor format, the full DSP shared-memory semantics, the PCM primitive
map, and the real 7530 hardware configuration.

## FON standalone-driver track

The `feature/fon-standalone-driver` branch investigates a minimal independent
FXS driver for the 7530 analog port.

The local workspace layout is documented in `../WORKSPACE.md` (outside Git):
`reference/`, `evidence/`, `restore/`, `backups/`, `work/`, `builds/`.

Documentation is split into four layers (see `docs/README.md`):

```text
docs/fon-known-facts.md          confirmed facts, each with its evidence class
docs/fon-open-questions.md       every unresolved item and what closes it
docs/fon-go-no-go.md             gates for each hardware stage
docs/fon-d06-summary.md          current reset/pinmux/startup reconstruction
docs/reference/                  primary captured data (OEM boot logs)
docs/runbook/                    procedures and build records
docs/history/                    analysis trail (historical, kept for provenance)
```

Current conclusion: **GO only for documented passive/read-only stages; NO-GO
for reset, firmware upload, TLMM writes, DMA/C4 and analog line activity.**
The QCA ADSS TDM/MBOX path and FRITZ!OS GPIO40/pinmux software paths are
recovered. Electrical reset polarity, physical PCM wiring, initial safe
slot-5 command, OEM `fs_per_dma`, and clock-gate cleanup remain unresolved.

## Critical missing vendor-kernel APIs

The modules are not merely tied to kernel 4.4 APIs. They import AVM/QCOM functions that OpenWrt 6.12 does not provide, including:

```text
msm_dectuart_init / msm_dectuart_put_char / msm_dectuart_get_char
dakota_gpio_ctrl / dakota_gpio_get_membase
tdm_if_config_init / tdm_if_dma_init / tdm_if_dma_start
avm_get_hw_config_table / avm_current_hw_config
firq_trigger_linux_ipi
PowerManagmentRegister
```

These APIs must be replaced with normal Linux GPIO, UART, DMA/TDM and device-tree interfaces. Changing module `vermagic` is not sufficient.

## Proprietary artifacts are not published

This public repository intentionally contains **no AVM kernel modules, no DECT
firmware, no extracted rootfs and no vendor init scripts**. Those files are
proprietary and remain local only:

```text
modules/      selected AVM .ko files
firmware/     DECT firmware and model EEPROM data
reference/    extracted vendor init scripts
```

They are excluded by `.gitignore`. `SHA256SUMS` records their expected hashes
so a local extraction can be verified without publishing the binaries.

## Local extraction set

The exact files needed for the analysis are extracted from:

```text
reference/oem-08.25/installers/FRITZ.Box_7530-08.25.image
  -> var/tmp/filesystem.image   (SquashFS rootfs)
  -> var/tmp/kernel.image       (EVA/LZMA kernel containing OEM HW236 DTBs)
```

**Canonical extracted copies live outside Git** in
`../reference/oem-08.25/extracted/`:

```text
extracted/kernel.image
extracted/filesystem.image
extracted/rootfs/
extracted/modules/
extracted/firmware/
extracted/init-scripts/
```

The in-repo `modules/`, `firmware/` and `reference/init.d/` trees below are
**legacy local caches** used by older analysis commands. They remain ignored
by Git; they are not the canonical reference location.

### Kernel modules

| Local path | Vendor path |
|---|---|
| `modules/piglet_noemif/Piglet_noemif.ko` | `lib/modules/4.4.271/piglet_noemif/Piglet_noemif.ko` |
| `modules/ubik2/pcmlink.ko` | `lib/modules/4.4.271/ubik2/pcmlink.ko` |
| `modules/avm_dect/avm_dect.ko` | `lib/modules/4.4.271/avm_dect/avm_dect.ko` |
| `modules/dect_io/dect_io.ko` | `lib/modules/4.4.271/dect_io/dect_io.ko` |
| `modules/nlaudio/nlaudio.ko` | `lib/modules/4.4.271/nlaudio/nlaudio.ko` |
| `modules/nlaudio/ulpcmlink.ko` | `lib/modules/4.4.271/nlaudio/ulpcmlink.ko` |
| `modules/capi_codec/capi_codec.ko` | `lib/modules/4.4.271/capi_codec/capi_codec.ko` |
| `modules/isdn_fon5/isdn_fbox_fon5.ko` | `lib/modules/4.4.271/isdn_fon5/isdn_fbox_fon5.ko` |
| `modules/extra/rtp/krtp.ko` | `lib/modules/4.4.271/extra/rtp/krtp.ko` |

### DECT firmware

| Local path | Vendor path |
|---|---|
| `firmware/dectfw_firstlevel_441_slow.hex` | `lib/firmware/dectfw_firstlevel_441_slow.hex` |
| `firmware/dectfw_secondlevel_441.hex` | `lib/firmware/dectfw_secondlevel_441.hex` |
| `firmware/dectfw_secondlevel_441p2test.hex` | `lib/firmware/dectfw_secondlevel_441p2test.hex` |
| `firmware/dect_eeprom` | `etc/default.Fritz_Box_HW236/avm/dect_eeprom` |

### Vendor init scripts

| Local path | Vendor path |
|---|---|
| `reference/init.d/E41-capi` | `etc/init.d/E41-capi` |
| `reference/init.d/S11-piglet` | `etc/init.d/S11-piglet` |
| `reference/init.d/rc.voip` | `etc/init.d/rc.voip` |

### Optional userspace binaries

These are present in the rootfs but are **not** required for the kernel-module
analysis and are not covered by `SHA256SUMS`:

```text
usr/bin/dect_manager
usr/bin/telefon
bin/voipd
```

## Extraction

The vendor `.image` is a tar archive. Its rootfs is a separate SquashFS file:

```bash
WORK="$HOME/fritz7530-extract"
ROOTFS="$WORK/rootfs"

tar -xf reference/oem-08.25/installers/FRITZ.Box_7530-08.25.image -C "$WORK"
unsquashfs -d "$ROOTFS" "$WORK/var/tmp/filesystem.image"
```

See [EXTRACTION.md](EXTRACTION.md) for the full command sequence, exact copy
commands and verification.

After copying the selected files into `modules/`, `firmware/` and `reference/`:

```bash
sha256sum -c SHA256SUMS
```

The mocks and tests do not require any AVM binaries:

```bash
PYTHONPATH=src/mock python3 -m unittest discover -s src/mock/tests -v
```

## Directory contents

- `modules/`: **local only after extraction**, selected AVM kernel modules.
- `firmware/`: **local only after extraction**, DECT firmware and EEPROM data.
- `reference/init.d/`: **local only after extraction**, vendor init scripts.
- `include/`: reconstructed ABI, protocol and shared-memory layout headers.
- `docs/`: FON hardware, AVM module and feasibility analyses.
- `notes/`: per-module static analysis, including `notes/pcmlink-sharedmem.md`.
- `src/mock/`: userspace-only models and tests; no kernel modules are loaded.
- `src/tools/`: disassembly, xref and HEX inspection helpers.
- `reports/imports/`: undefined symbols required by each module.
- `reports/exports/`: symbols retained in each unstripped module.
- `reports/symbols/`: complete address-sorted symbol tables.
- `reports/functions/`: named text symbols, suitable as a Ghidra function map.
- `reports/source-paths/`: source paths embedded by AVM builds.
- `reports/*.modinfo.txt`: original metadata and parameters.
- `reports/pcmlink-sharedmem.txt`: shared-memory evidence and region map.

Do not load these original `.ko` files on the OpenWrt 6.12 kernel.
