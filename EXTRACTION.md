# Extracting the FRITZ!Box 7530 telephony/DECT submodules

This repository does not track AVM kernel modules, firmware blobs or extracted
vendor init scripts. They are reproduced from the vendor image into the local
paths that `SHA256SUMS`, `notes/` and `reports/` expect.

## Source image

The source used for this analysis:

```text
FRITZ.Box_7530-08.25.image
FRITZ!OS 08.25
vendor kernel 4.4.271
ARMv7 / IPQ4019
```

The `.image` file is a **GNU tar archive**, not a mountable filesystem. Inside
it, the rootfs is a separate SquashFS file:

```text
./var/tmp/filesystem.image   SquashFS (xz), root filesystem
./var/tmp/kernel.image       EVA/LZMA vendor kernel; contains the OEM DTBs
./var/install                AVM installer
./var/version                firmware version
```

Do not try to `mount` the outer `.image`; that was the original mistake.

## 1. Extract the outer tar

Set paths:

```bash
IMG="$HOME/Downloads/OpenWrt7530/reference/oem-08.25/installers/FRITZ.Box_7530-08.25.image"
WORK="$HOME/Downloads/OpenWrt7530/work/oem-08.25/extract"
REPO="$HOME/Downloads/OpenWrt7530/FRITZ.Box_7530-08.25-kernel-4.4.271-telephony-re"

mkdir -p "$WORK"
```

Inspect and extract:

```bash
file "$IMG"
tar -tf "$IMG" | head -30
tar -xf "$IMG" -C "$WORK"
```

Expected files:

```bash
ls -lh "$WORK/var/tmp"
```

```text
filesystem.image
kernel.image
```

Check the filesystem type:

```bash
file "$WORK/var/tmp/filesystem.image"
```

Expected:

```text
Squashfs filesystem, little endian, version 4.0, xz compressed
```

## 2. Extract the OEM HW236 DTB

The OEM DTB is embedded in the LZMA-compressed EVA `kernel.image`; direct
search for FDT magic in the compressed file will not find it. The complete,
verified extraction procedure is documented in:

```text
docs/runbook/fon-oem-dtb-extraction.md
```

For FRITZ!OS 08.25 the selected HW236 DTB is at decompressed-kernel offset
`0x98d038`, is 26,963 bytes long, and has SHA256:

```text
3083e2acedc800015fea5ee7e57fa6cc8da551e21ee792095cbd8a7224bb841f
```

Keep the extracted binary outside Git under `reference/oem-08.25/`.

## 3. Extract the SquashFS rootfs

No root and no loop mount are required:

```bash
ROOTFS_IMG="$WORK/var/tmp/filesystem.image"
ROOTFS="$WORK/rootfs"

unsquashfs -d "$ROOTFS" "$ROOTFS_IMG"
```

Check:

```bash
ls "$ROOTFS/lib/modules/4.4.271"
ls "$ROOTFS/lib/firmware" | grep dect
```

If you prefer a read-only mount instead:

```bash
sudo mkdir -p /mnt/fritz7530-rootfs
sudo mount -t squashfs -o loop,ro "$ROOTFS_IMG" /mnt/fritz7530-rootfs
```

`unsquashfs` is safer for inspection because it never writes to the image.

## 4. Copy the selected artifacts into this repository

The repository contains only the telephony/DECT dependency chain, not every
module from the firmware.

```bash
cd "$REPO"

copy_artifact() {
    src="$1"
    dst="$2"
    mkdir -p "$(dirname "$dst")"
    cp -p "$ROOTFS/$src" "$dst"
}
```

### Kernel modules

```bash
copy_artifact lib/modules/4.4.271/piglet_noemif/Piglet_noemif.ko \
              modules/piglet_noemif/Piglet_noemif.ko

copy_artifact lib/modules/4.4.271/ubik2/pcmlink.ko \
              modules/ubik2/pcmlink.ko

copy_artifact lib/modules/4.4.271/avm_dect/avm_dect.ko \
              modules/avm_dect/avm_dect.ko

copy_artifact lib/modules/4.4.271/dect_io/dect_io.ko \
              modules/dect_io/dect_io.ko

copy_artifact lib/modules/4.4.271/nlaudio/nlaudio.ko \
              modules/nlaudio/nlaudio.ko

copy_artifact lib/modules/4.4.271/nlaudio/ulpcmlink.ko \
              modules/nlaudio/ulpcmlink.ko

copy_artifact lib/modules/4.4.271/capi_codec/capi_codec.ko \
              modules/capi_codec/capi_codec.ko

copy_artifact lib/modules/4.4.271/isdn_fon5/isdn_fbox_fon5.ko \
              modules/isdn_fon5/isdn_fbox_fon5.ko

copy_artifact lib/modules/4.4.271/extra/rtp/krtp.ko \
              modules/extra/rtp/krtp.ko
```

### DECT firmware and model defaults

```bash
copy_artifact lib/firmware/dectfw_firstlevel_441_slow.hex \
              firmware/dectfw_firstlevel_441_slow.hex

copy_artifact lib/firmware/dectfw_secondlevel_441.hex \
              firmware/dectfw_secondlevel_441.hex

copy_artifact lib/firmware/dectfw_secondlevel_441p2test.hex \
              firmware/dectfw_secondlevel_441p2test.hex

copy_artifact etc/default.Fritz_Box_HW236/avm/dect_eeprom \
              firmware/dect_eeprom
```

### Vendor init scripts

```bash
copy_artifact etc/init.d/E41-capi \
              reference/init.d/E41-capi

copy_artifact etc/init.d/S11-piglet \
              reference/init.d/S11-piglet

copy_artifact etc/init.d/rc.voip \
              reference/init.d/rc.voip
```

### Result

```text
modules/
  piglet_noemif/Piglet_noemif.ko
  ubik2/pcmlink.ko
  avm_dect/avm_dect.ko
  dect_io/dect_io.ko
  nlaudio/nlaudio.ko
  nlaudio/ulpcmlink.ko
  capi_codec/capi_codec.ko
  isdn_fon5/isdn_fbox_fon5.ko
  extra/rtp/krtp.ko

firmware/
  dectfw_firstlevel_441_slow.hex
  dectfw_secondlevel_441.hex
  dectfw_secondlevel_441p2test.hex
  dect_eeprom

reference/init.d/
  E41-capi
  S11-piglet
  rc.voip
```

## 5. Verify hashes

From the repository root, for the legacy in-repo cache:

```bash
sha256sum -c SHA256SUMS
```

For the canonical external tree:

```bash
(cd ../reference/oem-08.25/extracted && sha256sum -c SHA256SUMS)
```

All selected artifacts should report `OK`. A mismatch usually means the
firmware version is different, or a file was copied from another prefix.

The hash manifest covers only this selected set. It is not a complete copy of
all vendor modules.

## 6. What each selected component is

Canonical extracted copies live outside Git in
`../reference/oem-08.25/extracted/{modules,firmware,init-scripts}/`. The
repository-local paths below are legacy caches kept for older commands.

| Repository path | Vendor path | Role | Depends on |
|---|---|---|---|
| `modules/piglet_noemif/Piglet_noemif.ko` | `lib/modules/4.4.271/piglet_noemif/Piglet_noemif.ko` | DECT UART reset, handshake and firmware loader; optional Piglet FPGA bitfile | none |
| `modules/ubik2/pcmlink.ko` | `lib/modules/4.4.271/ubik2/pcmlink.ko` | PCM/TDM routing, QCA TDM/DMA, PCM slots, G.722/audio | none; needs vendor `tdm_if_*` |
| `modules/avm_dect/avm_dect.ko` | `lib/modules/4.4.271/avm_dect/avm_dect.ko` | DECT stack, PCM mail transport, UOTA/audio bridge | `pcmlink` |
| `modules/dect_io/dect_io.ko` | `lib/modules/4.4.271/dect_io/dect_io.ko` | `/dev/dect_io` userspace/kernel ABI shim | `avm_dect` |
| `modules/nlaudio/nlaudio.ko` | `lib/modules/4.4.271/nlaudio/nlaudio.ko` | optional netlink audio bridge | `avm_dect`, `pcmlink` |
| `modules/nlaudio/ulpcmlink.ko` | `lib/modules/4.4.271/nlaudio/ulpcmlink.ko` | optional remote PCM transport | `pcmlink` |
| `modules/capi_codec/capi_codec.ko` | `lib/modules/4.4.271/capi_codec/capi_codec.ko` | CAPI codec/DSP layer | `pcmlink` |
| `modules/isdn_fon5/isdn_fbox_fon5.ko` | `lib/modules/4.4.271/isdn_fon5/isdn_fbox_fon5.ko` | CAPI, analog FON/ISDN, call routing | `pcmlink` |
| `modules/extra/rtp/krtp.ko` | `lib/modules/4.4.271/extra/rtp/krtp.ko` | optional RTP acceleration | `isdn_fbox_fon5`, `pcmlink` |

Firmware:

| Repository path | Vendor path | Purpose |
|---|---|---|
| `firmware/dectfw_firstlevel_441_slow.hex` | `lib/firmware/dectfw_firstlevel_441_slow.hex` | first-level DECT loader |
| `firmware/dectfw_secondlevel_441.hex` | `lib/firmware/dectfw_secondlevel_441.hex` | normal second-level DECT firmware |
| `firmware/dectfw_secondlevel_441p2test.hex` | `lib/firmware/dectfw_secondlevel_441p2test.hex` | p2 test firmware variant |
| `firmware/dect_eeprom` | `etc/default.Fritz_Box_HW236/avm/dect_eeprom` | model default DECT EEPROM image |

Reference scripts:

| Repository path | Vendor path | Purpose |
|---|---|---|
| `reference/init.d/E41-capi` | `etc/init.d/E41-capi` | module-load order and `/dev/dect_io` node |
| `reference/init.d/S11-piglet` | `etc/init.d/S11-piglet` | Piglet firmware parameters |
| `reference/init.d/rc.voip` | `etc/init.d/rc.voip` | `telefon` / `voipd` startup |

## 7. Userspace binaries (not copied here)

The rootfs also contains the userspace stack:

```text
usr/bin/dect_manager
usr/bin/telefon
bin/voipd
```

These are uClibc ARM binaries. They are not part of the selected kernel-module
set and are not copied into `modules/`. They can be extracted separately for
userspace/ABI work.

## 8. Important warnings

- These are ARM EABI5 modules for kernel `4.4.271`; do not load them on the
  OpenWrt `6.12` kernel.
- The vendor modules import AVM/QCOM APIs not present in OpenWrt: `tdm_if_*`,
  `dakota_gpio_*`, `avm_get_hw_config_table`, `msm_dectuart_*`, AVM FIQ helpers.
- `modules/`, `firmware/` and `reference/` are intentionally ignored by Git as
  legacy local caches. Canonical extracted copies live outside the repository
  in `../reference/oem-08.25/extracted/`. Keep all of them local unless you
  have made a licensing decision.
- The extraction commands are read-only with respect to the firmware image.

## 9. One-command check after extraction

```bash
cd "$REPO"
sha256sum -c SHA256SUMS
PYTHONPATH=src/mock python3 -m unittest discover -s src/mock/tests -v
```
