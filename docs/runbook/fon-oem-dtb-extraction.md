# D0.6 — extracting the OEM HW236 DTB

> **Offline runbook.** Current D0.6 conclusions are in
> `../fon-d06-summary.md`; this file only reproduces the extraction.

> **Status: CONFIRMED offline extraction.** No router access and no flash
> operation were used. The proprietary DTB and its decompiled DTS are kept
> outside Git under `/home/rck/Downloads/OpenWrt7530/reference/oem-08.25/`.

## Result

A HW236 DTB was extracted from the EVA/LZMA kernel in the original FRITZ!OS
08.25 image; the kernel contains three HW236 variants (see below):

| Item | Value |
|---|---|
| Outer image | `reference/oem-08.25/installers/FRITZ.Box_7530-08.25.image` |
| Kernel member | `var/tmp/kernel.image` |
| Format | AVM EVA record containing an LZMA stream |
| Decompressed-kernel FDT offset | `0x98d038` |
| DTB size | `26963` bytes |
| Model | `AVM FRITZ!Box 7530` |
| Compatible | `qcom,ipq4019` |
| SHA256 | `3083e2acedc800015fea5ee7e57fa6cc8da551e21ee792095cbd8a7224bb841f` |
| Local DTB | `reference/oem-08.25/dtb/HW236-subrev2.dtb` |
| Local DTS | `reference/oem-08.25/dtb/HW236-subrev2.dts` |

The SHA256 is identical to the value previously recorded in
`../history/fon-dialog-board-uart-identification.md` and
`../history/fon-adss-tdm-channel-map.md`. This is the same compiled OEM tree, not an
OpenWrt reconstruction.

## Why direct scanning of `kernel.image` fails

`kernel.image` starts with the little-endian EVA magic `0xfeed1281`. Its
kernel payload is LZMA-compressed, so FDT magic `d00dfeed` does not occur in
the container. The EVA record stores a modified LZMA header:

| EVA offset | Field |
|---:|---|
| `0x00` | magic `0xfeed1281` |
| `0x04` | record length |
| `0x08` | load address |
| `0x0c` | image type |
| `0x10` | compressed size |
| `0x14` | uncompressed size (32 bit) |
| `0x18` | payload CRC |
| `0x1c` | LZMA properties + dictionary size |
| `0x24` | compressed payload |

To obtain a standard LZMA-alone stream, combine the five bytes at
`0x1c..0x20`, the uncompressed size expanded to a little-endian 64-bit value,
and the compressed payload beginning at `0x24`.

## Reproducible extraction

Run from `/home/rck/Downloads/OpenWrt7530` after extracting the outer tar:

```bash
mkdir -p reference/oem-08.25/dtb

python3 - <<'PY'
from pathlib import Path
import struct

src = Path("reference/oem-08.25/extracted/kernel.image").read_bytes()
magic, record_len, load_addr, image_type, compressed_size, \
    uncompressed_size, crc = struct.unpack_from("<7I", src, 0)

assert magic == 0xfeed1281
assert 36 + compressed_size <= len(src)

lzma_header = src[28:33] + struct.pack("<Q", uncompressed_size)
payload = src[36:36 + compressed_size]

Path("reference/oem-08.25/dtb/kernel.lzma").write_bytes(
    lzma_header + payload
)
PY

xz --format=lzma -dc \
  reference/oem-08.25/dtb/kernel.lzma \
  > reference/oem-08.25/dtb/kernel.dec
```

Extract every self-consistent FDT and print its provenance:

```bash
python3 - <<'PY'
from pathlib import Path
import hashlib
import struct

src = Path("reference/oem-08.25/dtb/kernel.dec").read_bytes()
magic = b"\xd0\x0d\xfe\xed"
pos = 0
index = 0

while True:
    pos = src.find(magic, pos)
    if pos < 0:
        break
    totalsize = struct.unpack_from(">I", src, pos + 4)[0]
    if 40 <= totalsize <= len(src) - pos:
        index += 1
        blob = src[pos:pos + totalsize]
        out = Path(f"reference/oem-08.25/dtb/fdt-{index}-0x{pos:x}.dtb")
        out.write_bytes(blob)
        print(hex(pos), totalsize, hashlib.sha256(blob).hexdigest(), out)
    pos += 4
PY
```

The output for FRITZ!OS 08.25 is:

```text
0x98d038 26963 3083e2acedc800015fea5ee7e57fa6cc8da551e21ee792095cbd8a7224bb841f
0x993990 26963 497fe05825d104c7d781729ce37e2f9cb101cccb85bdcbdab67be1eb1aedb4f4
0x99a2e8 26963 497fe05825d104c7d781729ce37e2f9cb101cccb85bdcbdab67be1eb1aedb4f4
```

The second and third blobs are byte-identical. All three are HW236 trees;
the repository uses the first blob for analysis. This is a documented choice,
not proof that the OEM bootloader selects it.

## What distinguishes the three blobs

An offline decompile and comparison shows:

| Property | First blob (`0x98d038`) | Second/third (`0x993990`/`0x99a2e8`) |
|---|---|---|
| `model` | `AVM FRITZ!Box 7530` | `AVM FRITZ!Box 7530` |
| `compatible` | `qcom,ipq4019` | `qcom,ipq4019` |
| HW revision | `236` | `236` |
| `avm-hw-revision/subrevision` | `2` | `0` |
| GPIO / UART / TDM properties | identical | identical |
| SHA256 | `3083e2ac…b841f` | `497fe058…b4f4` |

The full decompiled-device-tree diff between the first and second blob is only
the `subrevision` property. Therefore:

- the D0.6 GPIO40, UART and PINMUX facts do not depend on which of the three
  blobs is selected — those properties are identical;
- the OEM 08.25 runtime capture reports `HWS(2)`
  (`reference/oem-08.25-boot/`), so this board is **subrevision 2** and the
  first blob matches it;
- **which blob the OEM bootloader actually chooses remains UNKNOWN (Q80)**;
- the `model` string alone is not evidence of bootloader selection.

Save and decompile the first blob:

```bash
cp reference/oem-08.25/dtb/fdt-1-0x98d038.dtb \
   reference/oem-08.25/dtb/HW236-subrev2.dtb

dtc -I dtb -O dts \
  -o reference/oem-08.25/dtb/HW236-subrev2.dts \
  reference/oem-08.25/dtb/HW236-subrev2.dtb

sha256sum reference/oem-08.25/dtb/HW236-subrev2.dtb
fdtget reference/oem-08.25/dtb/HW236-subrev2.dtb / model
```

## D0.6 evidence from the compiled DTB

The compiled `avm_gpio` node contains:

| AVM name | GPIO | `param` | `function` | Status |
|---|---:|---:|---:|---|
| `gpio_avm_dect_reset` | 40 | `0x0b` | absent | **CONFIRMED** |
| `gpio_avm_pcmlink_mcl` | 20 | `0x0c` | **2** | **CONFIRMED** |
| `gpio_avm_pcmlink_dcl` | 21 | `0x0c` | **2** | **CONFIRMED** |
| `gpio_avm_pcmlink_fsc` | 22 | `0x0c` | **2** | **CONFIRMED** |
| `gpio_avm_pcmlink_di` | 23 | `0x0c` | **3** | **CONFIRMED** |
| `gpio_avm_pcmlink_mcl_2` | 24 | `0x0c` | **3** | **CONFIRMED** |
| `gpio_avm_pcmlink_dcl_2` | 25 | `0x0c` | **3** | **CONFIRMED** |
| `gpio_avm_pcmlink_fsc_2` | 26 | `0x0c` | **3** | **CONFIRMED** |
| `gpio_avm_pcmlink_do` | 27 | `0x0a` | **3** | **CONFIRMED** |

Therefore `AVM_DEF_HW_FUNCTION_PINMUX2 = 2` and
`AVM_DEF_HW_FUNCTION_PINMUX3 = 3` are no longer inferred from names: their
compiled property values are **CONFIRMED**. The separate question of whether
`dakota_gpio_pinconfig()` passes those values to TLMM without transformation
remains **UNKNOWN** until that function is recovered.

## Repository policy

Do not add the extracted `.dtb`, decompiled `.dts`, kernel payload or other
AVM proprietary artifacts to Git. Only the extraction method, hashes and
small factual excerpts are tracked.
