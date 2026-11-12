# E4.4 TX RAM byte chain and queue adjacency

`cr16-e44-tx-producers.json` cites selected RAM byte loads at `0x9FA4` /
`0x9BE8`, index stores, wrap tests against `[0xE8]`, byte zero-extension,
`storw` at architectural `0x00FF4902` and `0x00FF4904`, and bit5 test
at `0x00FF4900`. Normal TX buffer writer remains unresolved; `0x9F00`
**reads** TX bytes to create a software queue item, not vice versa.

P2test writer `0x9C34` has selected `0x9C8C: storb r2,0(r4,r3)` after
forming `r4:r3=0xA5D+write_index`. It updates `0x94B0`, checks additional
indices and flags, and saves/restores interrupt status. Only `0x9CA6`
is a resolved direct caller. No caller input→response proof follows.

Queue base/limit/TX base: `0x2FD/0xAFB/0xAFD` normal and
`0x25D/0xA5B/0xA5D` p2test. The arithmetic separation is two bytes
between the **comparison limit** and TX base, not a validated non-overlap
guarantee. Overflow/interrupt aliases and full/wrap semantics remain open.
