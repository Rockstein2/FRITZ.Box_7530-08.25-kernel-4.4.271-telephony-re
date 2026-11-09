# FON-E3.3 — bounded DIP/DSP reconstruction (offline)

No FRITZ!Box access, firmware execution or hardware testing. K1/K2 NO-GO.
The two SHA256-verified firmware images were independently disassembled with
the local CR16 oracle. Six JSON reports and fresh-directory replay tests live
in `tools/reports/cr16-e33-*.json` and `tools/tests/`.

| Question | Result | Limit |
|---|---|---|
| 511 writes `0x01000002…0x010003FE`? | Local counter init=1, helper increments, `cmpw $0x200` and a backedge are visible in both images; address arithmetic is `0x01000000 + 2*zero_extend16(counter)` | **PARTIALLY_PROVEN**, not a global exact count: branch flag semantics, unknown entrants/writers and asynchronous interference not excluded |
| Every stored word `0x1001`? | `movw $0x1001,r2` immediately before direct helper call; helper stores `r2` without a local clobber | Only the bounded call path; no all-path proof |
| Meaning of `0x1001`? | SC14480 Table 10 allows BR or BR_B0 depending on byte order | Full encoding, displacement/bank/target and validity unproved; AN-D-140 and OsmocomDECT sources unavailable offline |
| Other DIP program writes? | Yes: separate indexed word writer at `0x2618` / `0x1ED4`, plus further base-load sites and a save/restore word at `0x3704` / `0x3456` | Complete contents/order of program unknown |
| DIP stop → init → start? | In the observed local path fill calls a routine that writes BMC candidates, then `0x0080` and later `0x0000` to `0x00FF6006`, then caller polls `0x00FF6002` | Stop **after** fill on this path, not proved stop-before-fill; actual hardware start semantics related-device only |
| `dip_int` events? | Normal masks bits 1–3 and updates indexed byte/bit state; p2test has explicit `0x0e` / `0x0f` dispatch | Downstream semantics, indirect targets and hardware source unresolved |
| DSP bits 2/3? | If low event bits `& 0x0E` are nonzero, CFG skips both helpers. Otherwise firmware first ORs `0x0C` into the event word, then tests bits 3/2 and calls `0x3B28`/`0x3B38` or `0x27744`/`0x27754` | Tests are **not** a direct decode of incoming bit 2/3 event meanings; FON relevance unproved |
| Runtime writers to `[0xD6]`? | No resolved direct writers in the bounded address-use report; static value `0x01027F80` | Indirect/copy/loader writers remain unknown |
| `0x01027FD8` above 24 bits? | `loadd 0xD6` loads a register pair; `addd $0x58` forms the 32-bit target, then pair-based load/store | SC14448 physical bus identity unknown |
| FON slot 5? | No source → transform → firmware consumer path in the bounded DIP/DSP IRQ paths | Negative result only in those paths; Q75 stays open |

Architectural `abs20` expansion remains proved (Q57 address-space part);
SC14448 register identities remain **CANDIDATE**. Q46/Q55 are narrowed but
not closed. No E4 or driver changes.
