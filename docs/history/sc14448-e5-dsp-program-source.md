# E5-B — DSP program source

> **Status: historical analysis; current summary is `../sc14448-e5-summary.md`.**
> Static, offline. Report: `tools/reports/cr16-e5-dsp-program-source.json`.

## The firmware derives the DSP start address from its own image

Both images contain, at `0x1370`/`0x0DE6`:

```
movd $0x17300:l,(r3,r2)     ; flash address of the DSP block
lshd $-1:s,(r3,r2)          ; >> 1   (word addressing)
addw $0xc000:m,r2           ; + 0xC000 program-space base
storw r2,0x54:m(r1,r0)      ; [0xD6]+0x54 = DSP_PC_START_REG
```

`((0x17300 >> 1) + 0xC000) & 0xFFFF = 0x7980` in **both** images.
The transform is exact firmware arithmetic; the hardware mapping behind it
is unproven.

## The DSP program is embedded in the firmware image

The second-level images carry a dedicated contiguous block at `0x17300`
(referenced by the firmware, not proven to be executed):

| Image | Run | Bytes | 16-bit words | Block SHA256 | First bytes |
|---|---|---|---|---|---|
| normal | `0x17300–0x17E79` | `0xB7A` (2938) | 1469 | `0c791f2d…` | `97 f3 80 39 3f bf 84 bf` |
| p2test | `0x17300–0x179F9` | `0x6FA` (1786) | 893 | `51a99f5d…` | `97 f3 80 39 3f bf 84 bf` |

Both have an additional small run `0x17FE0–0x17FF7` (24 bytes). The two
images embed **different-sized** DSP blocks; the reason is unknown.

## Classification (E5.1-audited)

`DSP_PROGRAM_CANDIDATE_REFERENCED_BY_PC_START` for both images. The
only firmware-proven link between the block and the DSP is the
`DSP_PC_START` derivation; block content, executability and the
execution mechanism are unproven:

* a real scan for absolute stores/loads into the SC14480 microcode
  windows (`0x0103xxxx`/`0x0104xxxx`) found none
  (`NONE_FOUND_BY_THIS_SCAN` — absence recorded, not proof);
* the only `0x0104xxxx` literal is normal's `0x23F28 movd
  $0x1044d:l,(r13)` — an odd data pointer, not a ROM-window reference;
* the microcode itself is not disassembled (no DSP disassembler, no
  SC14448 DSP documentation offline).

## SC14480 Table 63 conflict (E5.1)

The firmware transform `(addr>>1)+0xC000 (mod 2^16)` is identical to
the SC14480 Table 63 linear rule `DSP = (CR16>>1) − 0x4000 (mod 2^16)`.
Under Table 63, CR16 `0x17300` lies in the row **«Gen2DSP Micro code
RAM (Reserved)»** (`0x0001.4000–0x0001.7FFF → 0x6000–0x7FFF`), not in
the active shared-RAM row (`0x0001.0000–0x0001.3FFF → 0x4000–0x5FFF`).
This is a significant SC14448-vs-SC14480 difference to resolve (Q82):
the proven fact is the written value `0x7980`; its hardware meaning is
open.

## The companion data-space transform

Both images also compute `(addr >> 1) + 0x8000` for building DSP-visible
structures (normal `0x5BA/0x5C8/0x620` and `0x2772E/0x2775A/0x2797A`;
p2test `0xBB2/0xBBA/0xBC4/0xBCE/0xBD8/0xC04/0xC26/0x35D2/0x360A/0x37CE`).
This is a **candidate** DSP data-address mapping (CR16 shared-RAM
`0x10000+` → DSP `0x0000+` under the arithmetic), recorded as such, not
as a proven bus alias.

## Boundary

If the SC14448 executes the embedded block directly, the CR16 firmware
carries the complete DSP audio program and a future standalone driver
would not need a separate DSP upload. That remains **unproven**; the next
required facts are a SC14448 memory/system-controller document (or an
unavailable-in-this-project runtime observation) that ties DSP PC `0x7980`
to flash `0x17300`.
