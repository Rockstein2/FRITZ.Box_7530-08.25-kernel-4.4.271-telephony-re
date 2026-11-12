# E4.3 case-9 register-pair indirect call

Normal `0x27FBA: movd $0x13C59,(r11,r10)` then first `jal` at `0x27FDA`;
p2test `0x3C78: movd $0x1B7E,(r11,r10)` then first `jal` at `0x3C98`.
Using **CR16B ISA** JAL register-pair word-address encoding, multiply the
20-bit pair value by two: `0x278B2` / `0x36FC`, both decoded case-10 helper
entries. CFG/instruction checks exclude register-pair writes and calls
between the load and first JAL, and reject unexpected direct entries to
that first JAL. These are **PROVEN_UNDER_LOCAL_CFG_MODEL, conditional on
CR16B/SC14448 semantic compatibility**.

Normal helper's data base is literal `0x11DDA`; p2test's is literal `0`.
Later JAL sites (`0x27FE2`, `0x2800A`, `0x28014` and p2test `0x3CA0`,
`0x3CC6`, `0x3CCE`) follow a prior indirect call. They remain
**UNRESOLVED_CLOBBER_AFTER_PRIOR_CALL** even though the same register pair
is named. No related-device function naming or target enumeration by
coincidental table bytes is used.
