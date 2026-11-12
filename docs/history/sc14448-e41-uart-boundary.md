# E4.1 candidate UART RX and alternative sources

Resolved second-level reads in the candidate `0x00FF49xx` address family
are listed with site, width and effective architectural address in
`cr16-e41-uart-rx-candidates.json`. No resolved second-level read at the
related-device UART data address `0x00FF4902` leads to the item allocator.
The two UART-named vectors point at `nop; retx` in both images. Neither
observation excludes UART polling via another address, DMA, shared RAM,
indirect register-pair reads or a different vector map.

The first-level loader's UART handshake `0x02→0x01` must not be assigned
to this queue-item protocol without its own source-to-sink evidence.
