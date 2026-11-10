# E4 function discovery and normal/p2test matches

`cr16-e4-function-map.json` uses direct-call targets, 31 vector entries and
the startup-linked main loop as seeds. A branch-only destination is **not**
a function seed. Local traversal follows CFG fallthrough and direct branches,
but skips callee edges; it stops at return, another candidate entry, an
indirect edge, or a 1200-instruction limit. A `push` prologue and closed local
paths yield `CONFIRMED_FUNCTION` **under this local CFG model**, not a global
claim that no indirect entry can reach the region. Overlaps remain explicit.

The 431/403 candidates include 141/146 such locally closed regions and
25/19 overlapping-code candidates. Entry, locally estimated end, callers,
callees, MMIO-address operations, interrupt vector context, memory sites,
indirect exits and uncertainty are per-function. The remaining candidates
have unknown boundaries. `cr16-e4-normal-p2test-matches.json` records 97
unique 12-instruction structural-prefix candidates. It does **not** promote
similar opcodes to semantic equivalence, especially across different calls.

Second-level start is `0x15AA` normal / `0x1026` p2test after the known
first-level `0x10284→0x8` handoff; p2test setup starts `0x102C`. Main entry
is `0x39F8` / `0x27112`. The bytes at `0x8` have overlapping linear decode;
see `fon-dialog-boot-handoff.md` for the isolated branch proof.
