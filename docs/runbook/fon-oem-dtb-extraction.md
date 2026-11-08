# D0.6 — extracting the OEM HW236 DTB

> **Offline runbook.** Current D0.6 conclusions are in
> `../fon-d06-summary.md`; this file only reproduces the extraction.

> **Status: CONFIRMED offline extraction.** No router access and no flash
> operation were used. The proprietary DTB and its decompiled DTS are kept
> outside Git under `/home/rck/Downloads/OpenWrt7530/.work/`.

## Result

The OEM HW236 DTB was extracted from the EVA/LZMA kernel in the original
FRITZ!OS 08.25 image:

| Item | Value |
|---|---|
| Outer image | `FRITZ.Box_7530-08.25.image` |
| Kernel member | `var/tmp/kernel.image` |
| Format | AVM EVA record containing an LZMA stream |
| Decompressed-kernel FDT offset | `0x98d038` |
| DTB size | `26963` bytes |
| Model | `AVM FRITZ!Box 7530` |
| Compatible | `qcom,ipq4019` |
| SHA256 | `3083e2acedc800015fea5ee7e57fa6cc8da551e21ee792095cbd8a7224bb841f` |
| Local DTB | `.work/fon-d06/oem-dtb/Fritz_Box_HW236-oem.dtb` |
| Local DTS | `.work/fon-d06/oem-dtb/Fritz_Box_HW236-oem.dts` |

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
mkdir -p .work/fon-d06/oem-dtb

python3 - <<'PY'
from pathlib import Path
import struct

src = Path("fritz7530/var/tmp/kernel.image").read_bytes()
magic, record_len, load_addr, image_type, compressed_size, \
    uncompressed_size, crc = struct.unpack_from("<7I", src, 0)

assert magic == 0xfeed1281
assert 36 + compressed_size <= len(src)

lzma_header = src[28:33] + struct.pack("<Q", uncompressed_size)
payload = src[36:36 + compressed_size]

Path(".work/fon-d06/oem-dtb/kernel.lzma").write_bytes(
    lzma_header + payload
)
PY

xz --format=lzma -dc \
  .work/fon-d06/oem-dtb/kernel.lzma \
  > .work/fon-d06/oem-dtb/kernel.dec
```

Extract every self-consistent FDT and print its provenance:

```bash
python3 - <<'PY'
from pathlib import Path
import hashlib
import struct

src = Path(".work/fon-d06/oem-dtb/kernel.dec").read_bytes()
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
        out = Path(f".work/fon-d06/oem-dtb/fdt-{index}-0x{pos:x}.dtb")
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

The second and third blobs are byte-identical. The first blob is the HW236
DTB used throughout this repository. Save and decompile it:

```bash
cp .work/fon-d06/oem-dtb/fdt-1-0x98d038.dtb \
   .work/fon-d06/oem-dtb/Fritz_Box_HW236-oem.dtb

dtc -I dtb -O dts \
  -o .work/fon-d06/oem-dtb/Fritz_Box_HW236-oem.dts \
  .work/fon-d06/oem-dtb/Fritz_Box_HW236-oem.dtb

sha256sum .work/fon-d06/oem-dtb/Fritz_Box_HW236-oem.dtb
fdtget .work/fon-d06/oem-dtb/Fritz_Box_HW236-oem.dtb / model
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
