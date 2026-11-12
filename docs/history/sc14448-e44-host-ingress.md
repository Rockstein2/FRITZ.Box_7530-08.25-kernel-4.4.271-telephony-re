# E4.4 register access, RX uncertainty, boot separation

`cr16-e44-rx-candidates.json` enumerates SHA256-verified effective
architectural register accesses with instruction raw bytes and widths.
Selected TX register writes and status reads are proven *instructions*;
physical UART function is a related-device hint. No resolved runtime read
from `0x00FF4902` to `[0xDA]/[0xDE]` or allocator was found in this
bounded address inventory. That does **not** exclude reads through
unresolved pairs, another register, DMA, shared RAM or software event.

Vectors numbered 20 and 21 are `nop; retx` in both second-level images;
their UART labels come from a related chip. The first-level `0x02→0x01`
handshake cannot be transferred to the second-level item format.
Neither bootloader nor physical host interface was executed or observed.
