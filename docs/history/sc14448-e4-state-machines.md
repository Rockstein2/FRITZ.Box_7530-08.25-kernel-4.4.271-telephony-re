# E4 selected state variables, not a complete state machine

`cr16-e4-state-variables.json` lists read/write sites for normal
`0x9374`, `0x9376/78/7A`, `0x93CB`, and pointer slots `0xDA/DE`, with
p2test counterparts `0x94AC`, `0x94AE/B0/B2`, `0x9512`, `0xDA/DE`.
On a checked main-loop path, the two pointer slots are compared and an
item is processed before a pointer is advanced/cleared. TX counters and
status flags appear around the separate byte pump. The per-cell table
does not claim exhaustive initialization or interrupt-safe values; unknown
indirect writers and interleavings are explicit.

No confirmed UART→shared RAM→DSP or PCM state transition is included.
