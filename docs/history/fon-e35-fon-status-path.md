# E3.5 status direction and limits

Linux `PutRxDMA` receives logical RX slot 5; with bit15 clear it computes
`reg44=0x00020008|((status<<3)&0xF00)|((status<<4)&0xFF)`.
RX bits 0…3 reach reg44 bits 4…7; bits 5…8 reach 8…11. Bit4 and
bits 9…14 do not enter this mapping. Bit15 suppresses the update.
`slic_get_hook_state` polls reg44 bit7 (status bit3). This proves the
Linux-side software interpretation, not the firmware producer's semantics.

`cr16-e35-fon-status-producers.json` leaves SC14448 status source and
outbound interface unresolved. Periodic status, line hooks, fault or ring
feedback are hypotheses, not labels for individual firmware bits.
See `history/fon-e0-rx-status-reconstruction.md` for OEM instruction sites.
