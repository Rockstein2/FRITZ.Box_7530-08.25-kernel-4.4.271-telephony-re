# E4 selected RAM and queue boundary

`cr16-e4-shared-memory.json` records specific RAM accesses at `[0xDA]`,
`[0xDE]` and the RX/TX-related *candidate* state cells from both images.
The main loop compares pointer values, invokes an item dispatcher and then
advances/clears pointers on a selected path. This supports a software
queue-like **local model**. It does not establish a hardware mailbox,
external host producer, exact ring format or whole-firmware writer coverage.

The `[0xD6] = 0x01027F80` DSP pointer, DIP RAM index writes and addresses
above 24 bits remain separately documented in E3.x. Pointer arithmetic
must not be reduced to abs20 or to an SC14480 physical bank identity.
