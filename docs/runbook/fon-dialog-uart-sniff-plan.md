# UART sniff plan (passive, nothing executed)

> **Status: operational document.**
> This is a runbook, not an evidence record.  Hardware facts are maintained in
> `../fon-known-facts.md`; unresolved items in `../fon-open-questions.md`.

Status: **plan only.**  No capture was taken; no byte was sent to any
device.  This document says what to look for and what each observation
would and would not show.

---

## 1. Why this is worth doing now

The upload format is known from two independent reconstructions:

```text
u32be address
u32be length
length bytes of data
XOR checksum
```

(`../history/fon-dialog-uart-boot-protocol.md`, `include/piglet_protocol.h`,
`fon_dialog_build_image()`, and the loader at `0x1019A`–`0x10234`).

So a capture can be **matched against the published block map** rather than
interpreted from scratch: a correct capture should contain the block
addresses and lengths listed in `cr16-boot-memory-map.json`.

## 2. What to record

| Signal | Direction | Why |
|---|---|---|
| the DECT UART TX line (SoC → SC14448) | host → device | the upstream bytes: headers, data, ACK |
| the DECT UART RX line (SC14448 → SoC) | device → host | the replies: `0x02`/`0x01` handshake, `0x06` ACK, `0x15` NAK, checksum echo |
| the DECT reset line | — | marks the start of the sequence |

Both directions must be captured with a shared time base; a single-ended
capture cannot tell an ACK from a request.

## 3. Before interpreting anything

| Check | How |
|---|---|
| baud rate | the loader programs no divisor, so the rate is set before it runs; measure the narrowest pulse and derive the rate, then confirm by framing a known byte |
| logic level / polarity | idle state should be the line's high level; a wrong polarity produces inverted frames |
| start bit alignment | decode a few bytes by hand first |
| sampling | at least 8× the bit rate, ideally 16× |

## 4. What to look for, in order

| Observation | Would confirm | Would not confirm |
|---|---|---|
| a byte `0x02` from the device followed by `0x01` from the host | the handshake described at `0x10100`–`0x10116` | that the firmware path continues |
| a 4-byte big-endian value equal to a known block address (e.g. `00 01 00 80` for the first-level image, `00 00 00 00` for the second) | the header format | which image is being sent |
| the 4-byte length matching `cr16-boot-memory-map.json` | the block map is real at run time | that the bytes land where the header says |
| the data bytes matching the Intel HEX bytes | the transfer is the same image | that execution starts |
| an XOR of the data equal to the checksum byte the device sends | the checksum rule | anything about execution |
| `0x06` after the checksum | the ACK path (`0x1024E`) | that the hand-off branch ran |
| `0x15` | the NAK/error path (`0x1028A`) | why it failed |
| **silence after the ACK** | nothing | — |
| **any bus or address activity after the ACK** | the hand-off may have happened | which instruction caused it |

**The gap this plan cannot close.**  Whether the CPU jumps into the loaded
code is a *control-flow* event, not a byte on the UART.  A capture can show
that the transfer completed and was acknowledged; it cannot show where the
PC went.  To see that, one still needs a bus address trace; the
`0x10284` hand-off branch itself is resolved statically in
`../history/fon-dialog-boot-handoff.md`.

## 5. Offline processing

1. Decode both directions to bytes with a simple UART decoder (8N1,
   measured rate).
2. Split the host stream at the `0x01` handshake byte.
3. Parse `u32be addr`, `u32be len`, `len` bytes; compare each block with the
   Intel HEX image that declares that address.
4. Compare the XOR of the data with the checksum byte sent by the device.
5. Record the ACK/NAK byte that follows.
6. Log any bytes after the ACK that are not part of the protocol.

All of steps 1–6 are offline and safe.

## 6. Explicit non-goals

* no transmission of any byte to the device;
* no change to GPIO40, reset or the FON driver;
* no claim about register meaning from a successful capture.
