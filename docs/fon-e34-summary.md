# FON-E3.4 — DIP writers and CR16 loop (offline)

No router access, firmware execution or hardware action. K1/K2 remain NO-GO.
Seven SHA256-checked, oracle-backed reports are `tools/reports/cr16-e34-*.json`;
`tools/cr16_dip_program.py` stages the full bundle, then promotes it with
rollback on write errors after successful analysis. `test_cr16_dip_program.py` replays all seven from an
empty temporary directory and checks fail-closed behavior.

## Main result

In **both** images, `0x2618` / `0x1ED4` write the 16-bit word
`((r2 & 0xff) << 8) | (r3 & 0xff)` to
`0x01000000 + 2*zero_extend16(r4)`; `r2` is the **high** input byte and
`r3` the **low** input byte of the stored CR16 word. The index and bytes
are caller-controlled. At one locally checked post-fill caller,
`r4=2`, `r2=0x12`, `r3=0xaa`, so the later word is **`0x12aa` at
`0x01000004` (word index 2)**. Other callers and save/restore functions
make final DIP RAM contents runtime/path dependent, not a single decoded
program. Whether the SC14448 physically maps this region as DIP RAM remains
a related-device hypothesis.

| Writer | normal / p2test | Source | Address | Scope |
|---|---|---|---|---|
| Fill | `0x25D0` / `0x1E8C` | `0x1001` on local call path | base + 2×counter | local indices 1…511 |
| Byte-packing | `0x2618` / `0x1ED4` | `r2` high, `r3` low; one caller sets `0x12`,`0xAA` | base + 2×`r4` | dynamic index; local index 2 |
| Restore | `0x3704` / `0x3456` | saved RAM word `0x2434` / `0x1C8A` | base + 2×helper result | dynamic index, order unresolved |

**Loop:** `r0` is loaded explicitly by caller from counter cell
`0x937C` / `0x94B6` at `0x25FA2` / `0x26758` after the helper; it is
not presumed to be a helper return value. The helper saves/restores `r7`,
increments the same cell, and caller `cmpw $0x200,r0; bhi` branches while
`0x200 > r0` unsigned under CR16 comparison semantics. This yields
`LOCAL_LOOP_COUNT=511` and addresses `0x01000002…0x010003FE` on the closed
local CFG path. `ALL_PATH_LOOP_COUNT=UNKNOWN`: external cell writers,
interrupt interleavings and indirect entries remain unexcluded. The ISA
evidence is National CR16B manual (CMPi/PSR.L/HI) plus GCC CR16 backend
mapping `LTU → hi`; neither constitutes an SC14448 hardware trace.

**Bring-up:** the direct fill-exit call and every fallthrough instruction
within the selected BMC/control routine are checked. BMC candidate writes,
then `0x80` and `0` at effective `0x00FF6006` occur in that local order,
assuming intervening calls return. No earlier stopped-DIP state or global
ordering is proven; SC14480 `URST` semantics remain a hypothesis.

**Events:** direct CFG targets of the DSP gate, both bit-test false exits and
both helper calls are checked in both images. The zero-`&0x0e` path ORs
`0x0c` into `r10` before bit tests; the nonzero path skips helpers. Normal
and p2test DIP dispatch targets are checked separately. Actual event names,
other paths and FON significance are unresolved.

**DIP instructions:** `0x1001` and local later `0x12aa` are raw CR16-stored
words, not confirmed decoded DIP instructions. SC14480 Table 10 gives
branch/M_CON/JMPF *candidates*; AN-D-140 was not found. Public SC14421
OsmocomDECT sources are related-device references only, not SC14448 proof.

Q46/Q55 are narrowed but open. Q57 is solved only for architectural abs20
extension, not physical register identity. Q75 remains open: no slot-5
source-to-sink consumer was established. FON-E4 not started.
