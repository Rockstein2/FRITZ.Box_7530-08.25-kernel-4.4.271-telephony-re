# Local mocks

Clean-room, userspace-only test harnesses. They do not load kernel modules and
do not touch the router.

## `dect_io_mock.py`

Models the `/dev/dect_io` ABI documented in `notes/dect_io.md`:

- single open, `O_APPEND` rejection;
- write framing and the `avm_dect_if_tx` byte layout;
- DECT-to-user 5-byte prefix and partial reads;
- `ppos` reset after a complete message;
- poll masks `0x104`/`0x145`;
- ioctl 1 `{jiffies, 250}` and ioctl 2 debug print.

## `avm_dect_mock.py`

Models the observed `avm_dect.ko` boundary:

- `avm_dect_if_init/deinit/tx` and the `[channel][primitive][payload]` input;
- the `0x2fba` special-primitive path;
- `UicpSendMailToHost` and the DECT-to-user callback;
- the 0x1000-byte `RxTxCallback` control buffer;
- PCM mail framing, the 0xfc limit, activity notification and checksum;
- UOTA slot open/close through the pcmlink mock.

## `pcmlink_mock.py`

Models the small part of the `pcmlink` upper boundary used by `avm_dect`:

- DECT-control register/config/release and the observed status probes;
- audio-slot open/close with the 7-channel link-mask limit;
- `pcmlink_ul_activity`;
- DECT-control and audio-slot data delivery callbacks.

## `dect_stack.py`

Wires `DectIoMock -> AvmDectMock -> PcmlinkMock` into one userspace model. It
does not emulate QCA TDM/DMA hardware.

## `piglet_uart_mock.py`

Models the documented DECT upload handshake (`STX`, `SOH`, length, `ACK`,
data, checksum, `ACK`/`NACK`, and the HELLO path). It is a protocol model, not
a cycle-accurate DECT-chip emulator.

## `piglet_image.py`

Parses Intel HEX and builds the first/second-level image framing documented in
`include/piglet_protocol.h`:

```text
block = u32be address + u32be length + data
image = u16be/u32be payload_length + blocks + xor checksum
```

## Run tests

From the analysis root:

```bash
PYTHONPATH=src/mock python3 -m unittest discover -s src/mock/tests -v
```

The tests cover:

- write forwarding, length validation and transport errors;
- read header/body and partial reads;
- poll, ioctl, single-open and O_APPEND behavior;
- first-level, second-level and p2test firmware framing;
- slow/fast UART upload and checksum/NACK behavior;
- avm_dect TX/RX, special primitive, control buffer and PCM mail rules;
- pcmlink DECT-control registration, slot masks and UOTA callbacks;
- the wired `dect_io -> avm_dect -> pcmlink` chain.
