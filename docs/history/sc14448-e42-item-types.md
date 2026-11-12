# E4.2 payload type / nested item boundary

Case-7 helper constructs a new item with allocator tag `0x22`, state byte
`0x23` at `item+2` (via `payload−2`), payload `0xFFF1`, subtype `8`, source
pointer and length; then copies bytes into that item on the selected path.
This is not a header-tag rewrite. The parser's `0x0167` and `0xFFF1`
comparisons occur **only after `item+3 == 0x23`**. No proof connects the
case-7-generated item (tag `0x22`) to either comparison after dequeue.
Subtype 8 does not select parser cases 7/9/10/13; its eventual consumer
and the provenance of any parser-reachable `0x0167`/`0xFFF1` payload remain
unknown. No serial framing or TX response is inferred.
