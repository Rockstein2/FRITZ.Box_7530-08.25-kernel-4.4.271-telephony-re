# E4.4 software edges and peripheral proof limits

Direct edges selected in both images: main→dispatcher (queue item),
dispatcher→parser (conditional), main→TX byte pump (separate call).
Global state `0x93CB`/`0x9512` is read for a *new* item's state by allocator;
main copies a *consumed* item's tag there and dispatcher may also write
`0x23`. These are distinct fields and generations, not an implicit
tag rewrite. Firmware has independent DSP/DIP helper instructions as
recorded in E4; their *presence* is not a parser→subsystem path.

No producer→tag-0x23 parser→DSP/DIP/PCM/GPIO, command→TX response, or
external RX→queue chain is closed. The reports retain candidate sites
separately from proven direct edges and unsupported physical claims.
