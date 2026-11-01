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
- slow/fast UART upload and checksum/NACK behavior.
