# E4.1 software producer found; ingress not found

Normal `0x386A`, p2test `0x26F7C` allocate records, update `[0xDA]` via
register-pair indirection and write the 4-byte header. There are 22/19
direct resolved callers. Wrappers `0x3934`/`0x27046` allocate and pass a
source pointer plus stack argument to byte-copy helpers (`0x28CF4` /
`0x27C64`) for the payload. Selected TX-buffer activity can also call the
allocator (`0x9F3A` / `0x9B7E`). This is a **software producer**, not an
external-ingress proof.

The adjacent-instruction caller scan finds no literal `r2=0x23` among
resolved constant-tag callers. It leaves one normal and six p2test callers
without a locally adjacent constant, and does not exclude longer def-use,
indirect entries or later item modification. Therefore it is not a global
proof that the parser's `0x23` branch cannot be reached.

The scan covers literal pointer bases, selected pair stores, direct callers
and one stack-passed copy count. It does **not** close input provenance for
all callers or rule out indirect aliases, DMA, memory copy elsewhere and
interrupt writers. Direct-only memory cross-references at `[0xDA]` miss
the `stord` through `(r13)`; absence of a resolved absolute store is not a
negative producer result.
