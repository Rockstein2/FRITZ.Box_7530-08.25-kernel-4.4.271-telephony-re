# E4.1 case 7/9/10/13, bounded effects

`cr16-e41-command-cases.json` verifies each direct branch and call target.
Case 7 helper normal `0x9E10`, p2test `0x27412`, allocates a new queue item,
stores `0xFFF1` to its payload word, byte `8` at payload+2, source pointer
at +3 and length at +7. A helper copies payload bytes. This is an internal
queue event; it is not proved to be a UART response.

Case 9 calls `0x27FB4` / `0x3C72` after loading payload+3; these helpers
contain indirect calls whose targets/effects are not closed. Case 10 calls
`0x278B2` / `0x36FC` with payload+3/+4 byte arguments. Its local helper
comparison bounds differ across the two images (`0x12`/`0x17` versus
`0x0C`/`0x11`); claiming whole-function equivalence is unjustified.
Case 13 has a straight-line pointer32+value16→`storw` chain without a
selected-block range check. Producer input and target range remain unknown.
No case receives a semantic host-command name.
