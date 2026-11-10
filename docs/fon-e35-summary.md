# FON-E3.5 — offline PCM ingress / FON proof boundary

**Result: no instruction-level Linux slot-5 → SC14448 consumer proof.**
Seven reports in `tools/reports/cr16-e35-*.json` reproduce independently
from SHA-checked normal and p2test images via `tools/cr16_pcm_ingress.py`.
No router access or hardware tests. K1/K2 remain NO-GO; E4 was not started.

| Link | Status | Evidence |
|---|---|---|
| Linux `build_slic_ctrl()` → logical slot 5 | `PROVEN_BY_LINUX_OEM` | existing pcmlink protocol and slot5 fixture |
| Logical slot → raw DMA memory | `PROVEN_BY_LINUX_OEM` for EOR-2 transform | raw index 4 is **not** physical slot 4 |
| PCM wire order / SC14448 peripheral input | `UNKNOWN` | no board-level or peripheral source proof |
| SC14448 input → decoded control → analog output | `UNRESOLVED` | no connected def-use/call chain |
| SC14448 status → Linux RX | `UNRESOLVED` on firmware side | Linux bit mapping is known |

The analyzer inventories **188** resolved `0x00FFxxxx`/`0x01027Fxx`
reads in normal and **141** in p2test (including unrelated regions); it
counts 3232/2855 memory accesses with unknown/indexed addresses. No resolved
read at the related SC14480 `DSP_PCM_IN0…3` addresses `0x01027FAE/B0/B2/B4`
was found. This is a **scoped negative**, not an absent-PCM claim: pointer
aliases, DMA, FIFO and hardware-supplied RAM are not ruled out.

The Linux normal word is `0x4000 | reg48[4..7] | reg48[8..11] | reg2c[17,18]`
with the exact shifts/masks in `fon-sc14448-pcmlink-protocol.md`. The special
path is `special_field | 0x8000` **without masking `special_field`**: bit14
may also be set. Firmware immediates `0x4000` or `0x8000` are indexed but
not promoted to consumers. Linux RX bit3 maps to virtual reg44 bit7, read by
`slic_get_hook_state`; the producer in SC14448 remains unknown.

There is a separately checked local RAM-bit/GPIO-RMW path at normal
`0x2801E…0x2804E` and p2test `0x3CD8…0x3CFE`: it reads RAM bits and
conditionally changes bits of architectural `0x00FF4860` and a RAM state
bit. SC14CVMDECT calls that address `P3_DATA_REG`, but no SC14448 pin
identity, Linux control-word input or FON meaning is established.

The 10/14 directly resolved callers of the indexed DIP writer are enumerated;
the selected `0x12AA` path is retained, other runtime bytes and DECT/DSP/PCM
classification remain `UNKNOWN`. Indirect calls near peripheral reads are
triaged as **proximity only**, not target-producer proofs. Do not spend a
further stage decoding DIP radio instructions without a new FON link.

**Q75 remains open.** The first missing transition is physical/logical slot
5 → a specifically identified SC14448 ingress register or RAM location;
subsequent decode/side-effect and reverse status transitions are also missing.
Q46/Q55 and Q57 are unchanged.
