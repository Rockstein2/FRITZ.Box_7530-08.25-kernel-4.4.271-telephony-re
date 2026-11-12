# E4.1 verified links, unverified destinations

Verified *local* edges: direct calls into allocator, register-pair write of
`[0xDA]`, main loop's read of `[0xDA]/[0xDE]`, dispatcher→parser, case13's
payload pointer→`storw`, case7 helper→allocator. Missing are an external
source to these callers, resolved case9 indirect callee effects, case10
whole-path semantics, command→TX output, and any parser→DSP/DIP/PCM/GPIO
or analog FON source-to-sink chain. No SC14480 register identity or
arbitrary MMIO write is inferred from the symbolic pointer alone.
