# SC14448-E4.4 — bounded runtime transport and subsystem boundaries

Baseline: E4.3 `a9fb27909b2adb73e8463350c20420e0a6a6e41a`.
All results are static from SHA256-checked normal and p2test firmware, not
hardware execution. Seven reproducible JSON reports are generated with
`python3 tools/cr16_runtime_transport.py`. This stage does **not** turn the
unproved E4.2 tag-`0x23` parser path into a host protocol.

## Software queue and TX byte storage

| Image | queue base / comparison limit | TX byte base | candidate TX length | pump | bounded TX writer |
|---|---|---|---|---|---|
| normal | `0x2FD` / `0xAFB` | `0xAFD` | `[0xE8] = 0x7F0` image-initialized | `0x9F84` | **unresolved** (no proven resolved direct byte writer) |
| p2test | `0x25D` / `0xA5B` | `0xA5D` | `[0xE8] = 0x7F0` image-initialized | `0x9BC8` | `0x9C34` contains selected byte store `0x9C8C`; direct caller `0x9CA6` |

In both images `queue_base+0x800 == TX_base` and `TX_base−queue_limit == 2`.
Those two intervening addresses are **not proved unused**; the limit is a
comparison operand rather than a global allocation bound. The buffers have
different cursor cells (`[0xDA]/[0xDE]` versus `0x9376/78/7A` or
`0x94AE/B0/B2`) and base literals. They are separate **candidates** by
structure, with no all-path proof against oversized allocation, aliasing or
overlap. Bytes at the transition are recorded directly from the images in
`cr16-e44-buffer-layout.json`.

P2test's selected writer reads write index `0x94B0`, checks a flag and
candidate full conditions against read index `0x94AE` and index `0x94B2`,
writes `r2` at `0xA5D+index`, advances its index with wrap candidate, and
restores PSR after `di`. Its *own* producer input and startup reachability
remain unresolved. Normal `0x9F00` reads the TX buffer to build a **software
queue item**; it is **not** evidence of a TX buffer writer.

Both TX pumps read a byte at buffer+read cursor, zero-extend and issue
architectural `storw` at `0x00FF4902`, write `0x00FF4904` and test bit5 at
`0x00FF4900`. These are **REGISTER_ACCESS_PROVEN** (firmware instructions),
**UART_FUNCTION_RELATED_DEVICE** only as a naming analogy and
**PHYSICAL_UART_NOT_OBSERVED**. Neither physical wire activity nor response
framing/command echo is established. No case 7/9/10/13 → TX byte chain
has been proved.

## RX and subsystem links

The bounded resolved-read inventory finds status `0x00FF4900` in each
image, and other `0x00FF49xx` candidate reads, but **zero resolved reads of
`0x00FF4902`** feeding the software allocator. Stub vectors 20/21 do not
exclude polling at other registers, indirect reads, DMA, shared memory or
another IRQ. No hardware ingress to queue or host protocol is proven.
Bootloader handshake remains separate.

The verified *software* links are main→dispatcher→conditional parser and
main→TX pump. Independently observed DSP/DIP helper sites are recorded but
have **no proven producer-backed parser→DSP/DIP/PCM/GPIO edge**. Main copies
`item+3` to global state `0x93CB`/`0x9512`, which the allocator reads for
new item state: a genuine shared-RAM relation, **not** proof of external
transport or physical peripheral operation. Normal/p2test have different
queue/TX bases and case-9 table and case-10 bounds; short fingerprint
matches from E4 are not upgraded to whole-function equivalence.

The highest-priority unknown is still **the provenance of a parser-reachable
tag-`0x23` item**. Without it, the command graph remains conditional.
Q46/Q55/Q75 and K1/K2 NO-GO are unchanged; analog FON had no separate search.
