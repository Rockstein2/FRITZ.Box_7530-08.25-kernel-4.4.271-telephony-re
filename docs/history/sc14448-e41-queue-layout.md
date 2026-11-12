# E4.1 queue pointers, allocation and selected wrap

`[0xDA]` and `[0xDE]` are image-initialized to the same little-endian u32:
`0x2FD` normal / `0x25D` p2test. The allocator loads `[0xDA]`, adds
`payload_length+4`, writes `[0xDA]`, compares `[0xDE]`, checks a region
limit (`0xAFB` / `0xA5B`), and has paths resetting a pointer to the base.
Main reads both, compares equality, processes an item from `[0xDE]`, and
advances `[0xDE]` after the dispatch call on a selected path.

This supports **write/allocation cursor** versus **read/consumption cursor**
locally. 0x800 bytes is the base-to-next-buffer-span candidate; exact
full/overflow semantics, acceptable item lengths, and all interrupt
interleavings are unresolved. `di`/`ei` in both routines is synchronization
evidence, not a complete concurrency proof. See queue-layout JSON for raw
instruction bytes and exact sites in both images.
