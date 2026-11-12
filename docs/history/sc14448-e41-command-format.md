# E4.1 selected item format and offset correction

Allocator header: `item+0: u16 payload_length`; `item+2: status byte from
RAM`; `item+3: caller byte`. Payload begins at `item+4`. Dispatcher writes
`0x23` to a **separate global state byte** (`0x93CB` / `0x9512`), not to
`item+3`. Parser takes `item+4`, then
subtracts 4 for its tag test. Its payload-relative `+0` word comparisons
are `0x0167` and `0xFFF1`; on `0xFFF1`, payload+2 carries a case selector.
For case 13, payload+3 is a 32-bit pointer, payload+7 is a 16-bit value.
Thus absolute offsets within an allocated item are +7 and +11, not +3/+7.

Little-endian here refers to CR16 typed `loadd`/`loadw` memory operation,
not an established serial protocol byte order. The payload length may be
runtime-dependent, and global minimum-length validation is unresolved.
