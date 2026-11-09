# E3.3 bounded `dip_int` paths

Normal `0x28CD0…0x28CF2`, p2test `0x27C88…0x27CAA`: read effective
`0x00FF6006`, move low byte to `r2`, write `0x0400` to effective
`0x00FF5402`, direct-call `0x28732` / `0x25D74`. Normal tests `r9 & 0x0E`,
stores an event index at `0x9B85`, indexes state near `0x93D0`, tests and
clears selected bits, and calls `0x2858E` / `0x2862E` on some paths.
P2test first tests byte `0x953E` (zero → `0x26514`), then dispatches
`r9 == 0x0E → 0x25DBE`, `r9 == 0x0F → 0x25E2A`,
other values → `0x2658A`; downstream paths are not fully traced.

See `cr16-e33-dip-events.json` for raw bytes. Event names, hardware
register meaning, indirect targets and FON relevance remain unresolved.
