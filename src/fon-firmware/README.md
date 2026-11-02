# Dialog/Piglet firmware parser

This directory contains a clean-room userspace parser for the firmware format
consumed by AVM `Piglet_noemif.ko`:

```text
fon_dialog_fw.c/.h    Intel-HEX -> Piglet upload image
tests/                synthetic and real-image offline tests
```

It is deliberately **not** a kernel module and does **not** upload firmware.
The parser was checked against the local AVM firmware files:

```text
dectfw_firstlevel_441_slow.hex      629-byte image, 1 block
dectfw_secondlevel_441.hex        54124-byte image, 9 blocks
dectfw_secondlevel_441p2test.hex  49805-byte image, 8 blocks
```

No firmware is added to Git.  The parser has no black-box fallback and no
success output when an image is malformed.

## Build/run

```sh
make -C src/fon-firmware/tests run
```

Set `FON_FIRMWARE_DIR` to use a different local firmware directory.

## Scope

Implemented:

- Intel-HEX record types 0x00, 0x01, 0x02 and 0x04;
- checksum and duplicate/overlap checks;
- contiguous-block grouping;
- u16/u32 outer payload lengths;
- XOR checksum;
- SOH/length and `HELLO DCX81` boot helpers;
- validation of the observed fast-path reply.

Not implemented:

- opening a UART;
- asserting the SC14448 reset GPIO;
- stopping/restarting the shared console UART;
- automatic firmware upload.

Those operations require a separate, explicitly invoked loader after the
reset and UART ownership rules are validated.  See `docs/fon-dialog-boot.md`.
