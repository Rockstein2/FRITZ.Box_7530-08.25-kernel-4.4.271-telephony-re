# E4.2 queue header provenance and identity boundary

On a local selected path the allocator publishes an item (writes `[0xDA]`,
then header), main loads the cursors `[0xDA]`/`[0xDE]`, reads `item+3`, copies
that tag to a separate global, passes payload `item+4` to dispatcher, which
calls parser. Parser reads `item+3` itself and compares with `0x23`.

Direct parser calls: normal `0x39F2` and p2test `0x2710C`. Other *direct*
entries were not found; indirect calls/entry from unmodelled software remain
open. The queue supports wraparound and reuse, so the same numeric address
is not evidence that the written and consumed item are the same generation.
Header-overlap stores, memcpy, IRQ and DMA also prevent an all-path identity
claim. The alias report deliberately lists offset-2/3 candidate stores as
**candidates** rather than silently equating their pointer pairs to items.
