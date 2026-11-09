# E3.3 DIP fill: local instruction/CFG proof and boundaries

`tools/cr16_dip_trace.py` checks oracle-decoded instructions and direct
branch/call targets separately for both images. Normal:
`0x25F98` stores 1 at counter cell `0x937C`; `0x25F9A` loads `0x1001` into
`r2`; `0x25F9E` calls `0x25BA`. The helper loads the counter, constructs
`r5:r4 = 0x01000000 + 2*zero_extend16(r3)` at `0x25C4…0x25CE`, stores `r2`
at `0x25D0`, increments the counter and stores it back. At `0x25FA4` the
caller compares the counter to `0x200`; `0x25FA8` branches to `0x25F9A`.

P2test independently shows `0x2674E`, `0x26750`, `0x26754 → 0x1E76`,
`0x1E80…0x1E8C`, `0x1E8E…0x1E90`, `0x2675A…0x2675E`. The local path
contains no `r2` redefinition before the store. A 1…511 index gives the
historical `0x01000002…0x010003FE` range **conditionally**. No proof excludes
unknown counter writers, indirect entries, exceptional paths or interrupt
effects; CR16 `cmpw`/`bhi` flag orientation has not been independently
verified. The global count and all-path value therefore remain
`PARTIALLY_PROVEN`, not `PROVEN_UNDER_CFG_MODEL`.

Direct-edge CFG traversal from the selected caller reaches the store in 12
hops in each image and reaches the compare/branch. The store's only decoded
direct predecessor is the adjacent `addd` (`0x25CE` / `0x1E8A`). This does
not rule out indirect entry: the full decoded images contain 382 / 396
unknown indirect edges, respectively, and call-return effects are not a
complete interprocedural proof.

Other loads of the literal base `0x01000000` occur at normal `0x2604`,
`0x2E72`, `0x2F98`, `0x36BA`, `0x36EC`; p2test `0x1EC0`, `0x2A0E`,
`0x2B32`, `0x340C`, `0x343E`. `0x2604/0x1EC0` write indexed words from
two input bytes; `0x3704/0x3456` write another indexed word. Thus the
constant fill is **not** the only firmware writer. Whole-program ordering
and physical DIP RAM identity remain unknown.
