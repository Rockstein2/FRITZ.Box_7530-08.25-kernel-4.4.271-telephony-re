# E3.3 DIP bring-up: observed local order

Normal `0x25F90…0x25FB6` and p2test `0x26746…0x2676C` initialise a counter,
load `0x1001`, call the indexed fill helper, compare/branch, then call
`0x2558` / `0x1E0C` and poll effective `0x00FF6002`. In the **called**
routine: BMC candidate writes (`0x00FF6400 ← 0`, `0x00FF6402 ← 0xF0`),
then `0x00FF6006 ← 0x80`, then a read and acknowledgement, then
`0x00FF6006 ← 0`. The instruction order is visible; global scheduling,
other callers and interrupt interleavings are not excluded.

SC14480 p. 172 says bit 7 (`URST`) set stops the related-device DIP, clear
starts it at RAM+1. This does **not** prove SC14448 register identity or
that DIP was stopped before the fill. Its actual RAM contents when reset is
released and the meaning of `0x00FF6002` poll remain unresolved.
