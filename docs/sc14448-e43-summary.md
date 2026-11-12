# SC14448-E4.3 — conditional case effects and state boundaries

Baseline: E4.2 `932ed281b5d72ffc3aaf7db579121dd1eb8638f9`.
All effects below are **conditional on a parser input tag `0x23`**, whose
producer path E4.2 did not prove. Seven SHA256-checked reports in
`tools/reports/cr16-e43-*.json` distinguish instruction-level selected
effects from actual runtime reachability. Rebuild with
`python3 tools/cr16_command_effects.py` (offline).

| Case | normal / p2test | Conditional instruction-level effect | Runtime status |
|---:|---|---|---|
| 7 | `0x9ED0` / `0x274D2` | helper allocates item: tag `0x22`, state `0x23`, payload `0xFFF1`, subtype 8, pointer/length and copy | New item's next consumer not proved; same-parser recursion not proved |
| 9 | `0x9EEA` / `0x274EC` | first register-pair `jal`: word-address constant `0x13C59`/`0x1B7E` gives `0x278B2`/`0x36FC` under CR16B JAL semantics (case-10 helper) | **Only first indirect site resolved** under local CFG; later calls may clobber target registers |
| 10 | `0x9EF6` / `0x274F8` | compares two input bytes, calls lookup and possibly helper with indexed RAM store | Bounds differ (`0x12/0x17` vs `0x0C/0x11`); no whole-path equivalence or physical effect |
| 13 | `0x9EDE` / `0x274E0` | reads pointer32 at payload+3 and value16 at +7, `storw` through pointer | Upstream pointer range and any MMIO/DSP/DIP/PCM/GPIO destination unresolved |

Case-9 target conversion follows the **CR16B Programmer's Reference Manual,
§JAL**, which loads register-pair low16 into PC bits 1–16, high4 into bits
17–20 and clears bit0. The loaded pair has no writes/calls before the **first**
`jal`; subsequent `jal` sites follow an earlier call, so the generic clobber
model does not promote them. This is an explicitly conditional ISA
compatibility assumption for SC14448, **not a firmware-execution observation**.
Normal's table base in case 9 is `0x11DDA`; p2test uses `0x00000` in that
helper. Their data effects cannot be equated by matched call shape.

Case 10 reaches lookup `0x2773A` / `0x35DE` and a helper containing an
indexed RAM store `0x278AE` / `0x36F8`; its effective value and all-path
transition are not established. No case has a demonstrated producer-backed
runtime state transition, command→TX response or confirmed peripheral
effect. No case-13 reachable RAM or MMIO target is listed because no input
constraint was proved. Newly resolved indirect target **sites**: one per
image (two total), both point at the corresponding case-10 helper under the
local CR16B-compatible model. Direct conditional edge counts are not a
host-protocol command inventory.
