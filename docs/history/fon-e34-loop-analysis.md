# E3.4 `cmpw`/`bhi` and the 511-store boundary

Independent instruction trace for each image:

1. Counter cell `0x937C` / `0x94B6` initialised to 1.
2. Helper loads the cell into `r3`, stores `r2` at `base+2*r3`, increments
   `r3`, and writes it back. It saves/restores `r7`, preserving caller's
   `r8:r7` cell pointer on the linear helper path.
3. After call returns, caller explicitly executes `loadw 0(r8,r7),r0`
   (`0x25FA2` / `0x26758`). No ABI-based return assumption is needed.
4. `cmpw $0x200:m,r0` is immediately followed by `bhi` to the payload
   definition: no flag-changing instruction intervenes.

The National CR16B Programmer’s Reference Manual (CMPi, PSR.L, BCond code
HI) describes `L=1` when unsigned *first/source* operand > second/destination;
GCC CR16 backend maps unsigned `LTU` to assembler `hi` precisely because
its compare operands are reversed. For `$0x200,r0`, `bhi` is taken while
`512 > r0`. From initial index 1, the body writes indices 1…511,
increments the last value to 512 and exits: **LOCAL_LOOP_COUNT=511**.
`ALL_PATH_LOOP_COUNT` remains `UNKNOWN` because unrelated writers and
interrupts/indirect entries are not excluded. CR16B/GCC CR16 evidence is an
ISA comparison, not a proof of SC14448 physical memory/register identity.

Sources retained outside Git under `../work/cr16/references/`:
CR16B manual SHA256 `3d6b25b5a0ab9949ebe4b540cdfc093d71f8fad91cf075d1d9b6306b09fb6a94`;
GCC CR16 source SHA256 `37aecb4c744cbf47be3143a1c7df85cad7ad91259bb6a947204d56e5985dcd4c`.
URLs and raw instruction bytes are in `cr16-e34-loop-proof.json`.
