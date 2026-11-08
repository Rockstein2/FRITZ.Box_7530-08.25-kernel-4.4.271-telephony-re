# SC14448 UART boot protocol

> **Status: historical analysis.**
> This document records the reasoning and evidence as of the date it was
> written.  Some of its `UNKNOWN` / `UNVERIFIED` markers have since been
> answered.
> - Current confirmed facts: `../fon-known-facts.md`
> - Current open questions: `../fon-open-questions.md`
> - This file is kept for the reasoning trail, not as a status report.

Status: **offline reconstruction.**  L4 at best: the host side is known from
the AVM drops present in this repository (`include/piglet_protocol.h`,
`src/fon-firmware/fon_dialog_fw.c`), the device side from the first-level
disassembly (`fon-dialog-firstlevel-cfg.md`).  **No bytes were sent to
any device.**

---

## 1. What the two sides say

| Side | Source | What it establishes |
|---|---|---|
| host | `include/piglet_protocol.h` (recovered from `Piglet_noemif.ko`) | control bytes, framing, retry bounds, baud rates |
| host | `src/fon-firmware/fon_dialog_fw.c` (`fon_dialog_build_image`) | the exact upload payload: blocks of `u32be address, u32be length, data` |
| device | first-level disassembly | what the loader reads, checks and does with each byte |

The payload builder is convergent with the loader, which is the strongest
statement available offline: two independent reconstructions agree on the
format.

## 2. Framing

```text
level 0 (first-level):  u16be payload_len | blocks | xor_checksum
level 1 (second-level): u32be payload_len | blocks | xor_checksum
block:                  u32be address | u32be length | length bytes
```

| Image | blocks | payload | outer header | total |
|---|---|---|---|---|
| first-level | 1 (`0x00010080`, `0x26a`) | 626 | `02 72` | 629 |
| second-level (`normal`) | 9 | 54 119 | `00 00 d3 67` | 54 124 |

These numbers are produced by `tools/cr16_boot_memory_map.py` and stored in
`tools/reports/cr16-boot-memory-map.json`.

## 3. Byte-level exchange

| # | Host sends | Device (first-level) expects | Memory effect | Acknowledgement | Evidence |
|---|---|---|---|---|---|
| 1 | `0x02` (`STX`, trigger) | — | — | — | host header only; the loader does not test for `0x02` explicitly |
| 2 | `SOH` + length | the first received byte is compared with `2` (`0x10100`, `0x1010E`) | — | loader sends `2` first, then waits | L2 `0x10100`–`0x10116` |
| 3 | — | loader sends `2`, host replies `1` | — | — | L2 `0x10102`–`0x10112` |
| 4 | 4 bytes | big-endian 32-bit value into `(r13)` (`0x1011E`–`0x1014C`) | — | — | L2 |
| 5 | if `(r13) == 0`: nothing | loader sends `0x15` then four zero bytes | — | — | L2 `0x10150`–`0x10178` |
| 6 | if `(r13) != 0`: blocks | loader sends `0x06` (`ACK`) | — | `0x06` | L2 `0x10180` |
| 7a | 4 bytes | address, built big-endian into `(r12)` by `movb r2,r12` / `ashud $8,(r12)` at `0x1019A`–`0x101C4` | `(r12)` becomes the write pointer | — | L2 |
| 7b | 4 bytes | length, built big-endian into `(r8,r7)` at `0x101E2`–`0x10218` | loop bound | — | L2 |
| 7c | length bytes | each byte stored by **`storb r2,0x0:s(r12)`** (`0x1022C`), pointer advanced by `addd $1,(r12)` (`0x10234`), byte XORed into the checksum `r11` | the byte lands at `(r12)` | — | L2 |
| 8 | — | loader sends the checksum (`0x10240`) | — | — | L2 |
| 9 | host replies | loader requires `0x06`; otherwise restarts the exchange (`0x1024E`) | — | `0x06` | L2 |
| 10 | — | I/O handshake (`0x10254`–`0x10274`) | writes `0xf4836`, `0xf4838`, `0xf4900` | — | L2 |
| 11 | — | `CFG` bit 8 set (`0x10278`–`0x10280`) | — | — | L2 |
| 12 | — | branch to low memory (`0x10284`) | UNKNOWN | — | **UNKNOWN** (Q51) |

## 4. What is *not* established

| Question | Status |
|---|---|
| how data bytes reach memory | **known**: a 4-byte big-endian address goes into `(r12)`, a 4-byte big-endian length into `(r8,r7)`, then `storb r2,0x0:s(r12)` writes each byte and `(r12)` advances by one |
| the initial `SOH` value confirmation | the loader compares the first byte with `2`, not with `0x01`; the `SOH` constant comes from the host side only |
| the exact header/length handshake order | partially known; the loader sends `2` and expects `1`, which matches the "slow path" in `piglet_protocol.h` |
| the checksum algorithm | XOR over data bytes, direction and coverage **UNKNOWN** beyond "accumulated with `xorb r2,r11`" |
| the hand-off target | **UNKNOWN** (Q51) |
| baud rate | **UNKNOWN** — the loader never programs a divisor; it is set by the SoC or by a previous stage |

**What is proven.**  The transfer format on the wire is a block header
(`u32be address`, `u32be length`) followed by that many data bytes, and the
loader writes each byte at the address the header names (`0x1022C`,
pointer `(r12)` advanced at `0x10234`).  This matches the host-side block
format in `include/piglet_protocol.h` and `fon_dialog_build_image()`
exactly — two independent reconstructions agree.

**What this means for the second-level image.**  Because the second-level
payload declares its own block addresses (`0x0`, `0xd6`, `0x2b4`, …,
`0x20000`), the loader places it at exactly those addresses.  So the
second-level image is *not* relocated: it runs where its Intel HEX records
say it does, from `0x0` up to `0x28DCD`.

**What is still not proven.**  The *hand-off branch* at `0x1017C` and
`0x10298` (`0x18` form) is not decoded (Q51), so the instruction that enters
the loaded code is not identified.  The destination addresses are proven;
the control transfer is not.

## 5. Safety

No uploader was implemented or run.  Everything here is a parser and a
disassembly.
