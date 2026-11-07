# fon-loader

Dry-run planner for the Dialog SC14448 boot firmware transfer.

**It never opens a device.**  There is no code path here that touches a serial
port, a GPIO, a clock, a reset line or the chip.  Everything is arithmetic on
images already parsed from Intel-HEX, plus an abstract transport that the
tests drive with a script.

Design background: `../../docs/fon-dialog-minimal-loader.md`.

## Build and test

```sh
make -C src/fon-loader/tests run
```

## Usage

```sh
cc -O2 -Isrc/fon-loader -Isrc/fon-firmware \
   src/fon-loader/fon_loader.c src/fon-firmware/fon_dialog_fw.c \
   src/fon-loader/main.c -o /tmp/opencode/fon-loader

/tmp/opencode/fon-loader plan    firmware/dectfw_secondlevel_441.hex 1
/tmp/opencode/fon-loader dry-run firmware/dectfw_secondlevel_441.hex 1
/tmp/opencode/fon-loader mock    firmware/dectfw_secondlevel_441.hex 1
```

| Mode | What it does |
|---|---|
| `plan` | parses, splits into blocks, reports sizes; sends nothing |
| `dry-run` | same plus the exact host sequence and byte counts |
| `mock` | runs the transfer against a scripted transport that answers ACK |

`LEVEL` is `0` for the first-level image and `1` for the second-level image.

## Verified against the real images

```text
level 0: 629-byte image,   1 block,  trailer 1 B
  block 0: addr 0x00010080 len 618

level 1: 54124-byte image, 9 blocks, trailer 1 B
  block 0: addr 0x00000000 len 213
  block 1: addr 0x000000d6 len 477
  block 2: addr 0x000002b4 len 6138
  block 3: addr 0x000024f8 len 6150
  block 4: addr 0x00009000 len 875
  block 5: addr 0x00009c5e len 930
  block 6: addr 0x00017300 len 2938
  block 7: addr 0x00017fe0 len 24
  block 8: addr 0x00020000 len 36302
```

The last block starting at `0x00020000` with 36302 bytes is consistent with a
`FON_DIALOG_MAX_IMAGE` of `0x30005` (198 149) being a hard cap, not the image
size.

## Checksum caveat — read before trusting the checker

The local parser appends one XOR byte over the image payload.  On the real
AVM images the trailing byte does **not** equal the XOR of all preceding
bytes (`dectfw_secondlevel_441.hex`: computed `0x73`, stored `0xc7`).

Conclusion: **the trailer format of real images is not yet understood.**  The
planner therefore:

- accepts an image whose trailer it cannot model;
- reports `trailer N B` and `checksum_verified` separately;
- only claims `verified` when the local parser's rule holds.

An unproven checksum rule must never be used to reject real firmware, and it
must never be presented as validation either.

## What is still missing

- the real trailer layout (blocks after the last one, or a per-image footer);
- the exact reply timing, which sets the timeouts;
- the first-level versus fast-path choice for this unit;
- a transport that talks to a real tty (deliberately absent).

These are blockers for Stage D and are listed in the design document.
