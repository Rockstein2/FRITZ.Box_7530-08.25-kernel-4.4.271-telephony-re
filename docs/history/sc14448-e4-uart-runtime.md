# E4 UART runtime versus loader UART

The first-level loader's `0x02→0x01` handshake and UART RX polling at
`0x102A8…0x102BE` are **boot**, not runtime protocol evidence.

In both second-level images, vectors 20 and 21 have identical raw target
values, pointing at `nop; retx` (`0x28DCA` / `0x9FFC`). Their UART names
are *reference-chip* vector-number labels only. The bytes are independently
checked against the firmware by `cr16_architecture.py`.

A separate TX queue pump at `0x9F84` / `0x9BC8` reads an indexed byte from
RAM, advances a counter, zero-extends it, stores to effective
`0x00FF4902`, strobes `0x00FF4904` and checks bit5 of `0x00FF4900` before
another byte. Main calls it at `0x3A62` / `0x27180`. Physical UART identity
is supported by related-device register layout and first-level behavior,
but this second-level path proves the accesses rather than a specific
external peer. RX interrupt path is stubbed; no UART RX→runtime parser proof.

Other `0x00FF4960/66` accesses have not been promoted to UART command RX:
address-family proximity cannot establish the receiver or packet framing.
