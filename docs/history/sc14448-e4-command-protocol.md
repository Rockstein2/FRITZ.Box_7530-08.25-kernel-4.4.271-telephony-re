# E4 bounded command-item comparisons

On a selected main-loop queue path, `0x3ABE→0x39D6→0x9E68` normal;
`0x271DC→0x270E8→0x2746A` p2test. The last function checks the byte at
the selected item location against `0x23`, then compares a word with
`0x0167` and `0xFFF1`. The `0xFFF1` branch compares the byte at offset +2
to 7, 9, 10, 13. All four conditional branch destinations are independently
decoded and reported in `cr16-e4-command-dispatch.json`.

| Numeric case | normal target | p2test target | Bounded behavior |
|---:|---:|---:|---|
| 7 | `0x9ED0` | `0x274D2` | loads argument word/pointer; calls helper |
| 9 | `0x9EEA` | `0x274EC` | loads pointer; calls helper |
| 10 | `0x9EF6` | `0x274F8` | loads two bytes; calls helper |
| 13 | `0x9EDE` | `0x274E0` | loads pointer and word; stores through pointer |

No semantic command names, framing, CRC/checksum, length, timeout,
validation, sender identity or full TX response is claimed. For case 13,
input pointer provenance/authorization is **not established**; the observed
store cannot be assigned to any device or host protocol endpoint.
