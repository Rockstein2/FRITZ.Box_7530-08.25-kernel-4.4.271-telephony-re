# E3.4 instruction-level writer evidence

`tools/reports/cr16-e34-dip-writers.json` lists raw bytes and direct callers
independently for normal and p2test. At normal `0x2604…0x2618` and p2test
`0x1EC0…0x1ED4`, the sequential `movd/movzw/ashud/addd` chain forms
`0x01000000 + 2*zero_extend16(r4)`; `movzb r2,r2; ashuw $8,r2;
movzb r3,r3; orw r2,r3; storw r3,...` produces the value formula.
This demonstrates CR16 word packing, not DIP instruction byte order.

The directly checked later caller at normal `0x25FCA…0x25FD4` / p2test
`0x26780…0x2678A` sets index 2, low byte `0xAA`, high byte `0x12`.
The helper therefore writes `0x12AA` at `0x01000004` on this path. Other
callers are enumerated, but calls and branches upstream prevent extrapolating
their inputs without further def-use work.

Normal `0x36CC` saves an indexed word at `0x2434`; `0x3704` restores it
to an indexed address. P2test equivalents are `0x341E` / `0x3456` and
`0x1C8A`. The index is returned through another helper and remains
runtime-dependent. Literal-base loads are listed separately, not treated
as automatic writes. Indirect aliases, block copies and DMA are not
exhaustively resolved. The physical mapping to DIP RAM is still unproved.
