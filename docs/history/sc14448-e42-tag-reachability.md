# E4.2 bounded register slice (r2 → allocator)

The allocator copies `r2` into `r11` at `0x386E` / `0x26F80` then stores its
low byte at item+3 (`0x392A` / `0x2703C`). All 22/19 resolved direct call
sites are in `cr16-e42-allocator-callers.json`. A backward walk covers
direct CFG predecessors, previous blocks, byte register copies and literal
definitions. It stops at unresolved memory loads, unknown calls, unmodelled
arithmetic, non-closed entries and cycles. A checked leaf call `0x2327A`
sets `r2=0x14` before a `jump(ra)`; no generic callee preservation is
assumed. Branch predicates have **not** been solved.

Normal 21, p2test 18 direct sites have all resolved path definitions unequal
to `0x23` **at entry**; the remaining wrapper call per image gets `r2` from
its own caller and stays `TAG_SOURCE_UNKNOWN`. This excludes neither
indirect callers nor later tag writes, and cannot be promoted to a parser
branch impossibility or a physical runtime observation.
