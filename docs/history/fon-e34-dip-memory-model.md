# E3.4 possible DIP RAM contents, not a final image

`cr16-e34-dip-memory-model.json` has **512 entries per firmware image**.
Each entry carries its address, index, possible symbolic values, writer
instruction IDs and an unset final value unless a last writer on all paths
is proven. Index 0 was not included in the local fill; indices 1…511 have
`0x1001` on the local closed loop. Index 2 additionally has `0x12AA` on
the checked post-fill call path; runtime word packing, restore and unknown
indirect writes can supersede it. Other cells similarly retain symbolic
runtime-dependent writer values. `UNKNOWN` is retained for all unmodelled
aliases, not a statement that an unknown write definitely occurred.

No single final 512-word program is justified. The fill, local static
replacement and runtime writers have separate path/order provenance.
