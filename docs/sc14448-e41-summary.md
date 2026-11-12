# SC14448-E4.1 — bounded runtime queue / command / TX reconstruction

All findings are offline instruction-level static analysis. Ten SHA256-checked,
oracle-backed reports in `tools/reports/cr16-e41-*.json` regenerate through
`tools/cr16_queue_trace.py`. No firmware execution or router access.

## The queue is produced in software

The two 32-bit little-endian image-initialized cells are **not interchangeable**:

| Image | `[0xDA]` / `[0xDE]` initial value | allocator | local role |
|---|---:|---:|---|
| normal | `0x000002FD` / `0x000002FD` | `0x386A` | `[0xDA]` write/allocation cursor; `[0xDE]` read/consumer cursor |
| p2test | `0x0000025D` / `0x0000025D` | `0x26F7C` | same local role |

The allocator moves `[0xDA]` by `payload_length+4`, checks `[0xDE]`, handles
a selected wrap at comparison limit `0xAFB` / `0xA5B` (a candidate 0x800-byte
span), and writes a 4-byte header (`u16 length`, byte from status RAM, byte
from caller), then returns `item+4`. It uses `di`/`ei` locally; the precise
full/overflow semantics and all-path interrupt safety are **unresolved**.
Normal has **22**, p2test **19** resolved direct callers of the allocator.
An observed wrapper `0x3934` / `0x27046` copies bytes into the allocated
payload via a direct helper; other callers include software event paths.
The hardware or external source of their input data is not established.

The main loop compares the two cursor values. On its selected nonempty path
it passes `item+4` to `0x39D6` / `0x270E8`, which can call parser `0x9E68` /
`0x2746A`, then advances `[0xDE]` by the item's length plus four. This is a
**local producer→queue→consumer proof**, not an externally sourced UART
packet proof. The parser compares the caller-supplied `item+3` tag with
`0x23`. The dispatcher separately writes `0x23` into global RAM
`0x93CB` / `0x9512` before calling it; it does **not** overwrite the item.
Neither observation makes the tag a proven UART sync byte.
Among the 22/19 direct allocator callers, the immediately preceding
constant-tag sites supply values such as `0x14`, `0x22`, `0x05`, `0x03` or
`0x29`, **not `0x23`**. One normal and six p2test caller inputs are not
resolved by this adjacent-instruction check. Thus reachability of the
`0x23` parser branch from a particular producer remains unproved.

## Command-item formats and effects

Parser offsets 0/2/3/7 are relative to **payload = item+4**, not to the
4-byte queue header. On the `0xFFF1` branch, payload+2 is compared with
7/9/10/13. The `0x0167` comparison has another selected call path; neither
word has a proven external protocol meaning. Field availability/length for
all paths is not established.

| Case | Bounded effect | Unresolved boundary |
|---:|---|---|
| 7 | helper calls allocator and constructs another software item carrying `0xFFF1`, subtype `8`, pointer and length | whether this becomes a TX response |
| 9 | loads pointer from payload+3; direct helper call | indirect effects inside callee |
| 10 | passes bytes from payload+3/+4 to helper | different helper input comparisons normal/p2test; complete effects |
| 13 | `load[d]` pointer from payload+3; `loadw` value from payload+7; `storw` to pointer | no selected-block range check; pointer/target provenance unknown |

Case 13 pointer is 32-bit and value 16-bit; it is **POINTER_FROM_QUEUE_ITEM**,
not a proved externally controlled arbitrary MMIO write. No target in RAM,
`0x00FFxxxx`, `0x01000000` or `0x01027Fxx` is proved reachable. The selected
block has no range check, but earlier producer validation is unexcluded.

## TX and host boundary

The existing TX pump reads indexed RAM bytes at `0xAFD` / `0xA5D` candidate
buffer bases and writes effective `0x00FF4902`, strobes `0x00FF4904`, tests
bit5 of `0x00FF4900`. P2test has a directly checked local byte producer
at `0x9C8C`; corresponding normal producers and a command→TX response chain
are not established. The TX cursor cells are `0x9376/78/7A` or
`0x94AE/B0/B2`, but complete ring/full/response framing remains unknown.
Second-level UART-numbered ISR vectors are still stubs; no resolved read of
effective `0x00FF4902` proves a runtime UART RX producer. Bootloader UART
handshake is separate.

Q46/Q55/Q75 are unchanged. The primary blocker has narrowed from an unknown
queue producer to **unknown provenance of its callers' input data** and
unknown physical host ingress. No new indirect target is proven. Analog FON
was not separately prioritized. K1/K2 remain NO-GO.
