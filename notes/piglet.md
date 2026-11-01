# `Piglet_noemif.ko` — DECT UART loader and hardware bootstrap

Phase 2 static analysis. Source:

```text
modules/Piglet_noemif/Piglet_noemif.ko
SHA-256 verified by SHA256SUMS
ARM EABI5, kernel 4.4.271, not stripped
```

Addresses are section-relative for the module. No code was executed and no
router configuration was changed.

## 1. What the module does

`Piglet_noemif.ko` is the FRITZ!Box 7530 DECT bootstrap/firmware loader.
Despite its name it has two optional hardware paths:

```text
DECT UART path
  - GPIO reset of the DECT chip
  - msm_dectuart_init() / get_char() / put_char()
  - first-level and second-level firmware upload

Piglet FPGA bitfile path (not used on the default 7530 profile)
  - XBIT GPIO loader
  - optional /var/bitfile.bit or /var/bitfile_pots.bit
```

It does not provide the DECT application stack, CAPI, PCM routing, or audio.
Those remain in `avm_dect.ko`, `pcmlink.ko`, `isdn_fbox_fon5.ko`, and
`capi_codec.ko`.

### Init and exit

`init_module` / `piglet_init` (`.init.text 0x000`, 516 bytes):

```text
read kernel args and check:
  nopiglet
  pigletcalib
  pigletnopanic
get_profile()
piglet_requestinit()
avm_event_build_id_mask()
avm_event_source_register()
if async_loader:
    kthread_create_on_node(piglet_loader_thread)
else:
    piglet_loader_thread(0)       // synchronous during module init
dectuart_event_dim_led_status_init()
```

Failure paths call `lpiglet_cleanup` and log through the AVM panic/error
helpers. `piglet_cleanup` / `cleanup_module` (`.exit.text 0x000`, 36 bytes):

```text
clear piglet_ready/state flag
send_piglet_ready_event()
dectuart_event_dim_led_status_exit()
lpiglet_cleanup()
```

`piglet_requestinit()`/`piglet_requestrelease()` are stubs returning success;
the actual DECT request hooks are exported as `dect_requestinit()` and
`dect_requestrelease()`.

`dect_requestinit`:

```text
if gRequestDect_ok == 0:
    if pProfile->gpio_dect_tx != -1:
        dakota_gpio_ctrl(gpio, 1, 1)
    gRequestDect_ok = 1
return 0
```

`dect_requestrelease` calls `msm_dectuart_exit()` and clears the flag.

## 2. Profile and GPIO map

`get_profile()` (`0x2b08`, size `0xe64`) obtains the AVM hardware-config table
through `avm_get_hw_config_table()`, scans entries of 0x20 bytes by name, and
fills `profile_list` (`.data+0x0`, 60 bytes).

The recovered profile field map is:

```text
profile+0x00  char *name
profile+0x04  gpio_avm_piglet_noemif_data
profile+0x08  gpio_avm_piglet_noemif_done
profile+0x0c  gpio_avm_piglet_noemif_clk
profile+0x10  gpio_avm_piglet_noemif_prog
profile+0x14  gpio_avm_piglet_noemif_fpgaok
profile+0x18  gpio_avm_piglet_clockout
profile+0x24  piglet/dect mode (cached into .bss+0x12c)
profile+0x28  gpio_avm_dect_reset
profile+0x2c  gpio_avm_dect_rd
profile+0x30  gpio_avm_dect_tx
```

Fields at `+0x1c`, `+0x20`, `+0x34`, `+0x38` are not read by the paths
analyzed here; they are preserved as reserved/legacy fields.

The static fallback profile is named `"235"` (`.rodata.str1.1+0x109b`) and has
these exact `.data` initializers:

```text
+0x04  0xffffffff   // no Piglet data GPIO
+0x08  0xffffffff   // no Piglet done GPIO
+0x0c  0xffffffff   // no Piglet clock GPIO
+0x10  0xffffffff   // no Piglet program GPIO
+0x14  0xffffffff   // no FPGAOK GPIO
+0x18  0xffffffff   // no clockout GPIO
+0x1c  0
+0x20  0
+0x24  0x00000105   // default DECT mode
+0x28  0x00000012   // GPIO 18, DECT reset
+0x2c  0x00000010   // GPIO 16, DECT RD
+0x30  0xffffffff   // no DECT TX GPIO; UART is used
+0x34  0
+0x38  0xffffffff
```

This is the important 7530 result: the default profile has **no Piglet FPGA
GPIOs**, **DECT reset on GPIO 18**, **DECT RD on GPIO 16**, and **no DECT TX
GPIO**. The actual hardware-config table can override these values.

`get_profile()` also reads the `HWRevision` and `HWSubRevision` environment
variables; it prints either:

```text
[piglet]use default-settings (%d gpio%s from hw_config)
[piglet]use settings for %s(%d gpio%s from hw_config)
```

The physical GPIO numbers are therefore data, not constants in the `.text`.

## 3. DECT reset and UART initialization

`dect_loader()` (`0x9a8`, size `0xf88`) is the uploader/state machine. Its
arguments are:

```text
r0 = image buffer (first-level or second-level image from ihex2bin)
r1 = image size
r2 = mode/flags from dect_file_process
r3 = async-loading/debug flag
```

The state jump table at `0xa88` is:

```text
state 0 -> 0x0a9c   reset and UART setup
state 1 -> 0x0e14   handshake / wait for STX
state 2 -> 0x1194   wait for ACK/NACK
state 3 -> 0x1534   send image bytes and checksum
state 4 -> 0x14f4   fast-path length header
```

### Reset path

State 0 uses the profile entries:

```text
profile+0x28 = gpio_avm_dect_reset
profile+0x2c = gpio_avm_dect_rd
profile+0x30 = gpio_avm_dect_tx
```

Observed sequence:

```text
assert DECT reset low
dakota_gpio_ctrl(reset, 0, 1)
dakota_gpio_out_bit(reset, 0)
delay via arm_delay_ops
msm_dectuart_init(baud, ...)
release DECT reset high
dakota_gpio_out_bit(reset, 1)
delay
```

The 144xx path also drives `profile+0x2c` (DECT RD) in chip-specific branches.
`piglet_reset()` is a different, optional FPGA reset: it uses profile+0x10
(Piglet PROG) and returns immediately when that GPIO is `-1`, which is the
default on 7530.

### UART baud rates

The code uses these exact divisors passed to `msm_dectuart_init()`:

```text
0x2580   9600
0x4b00   19200
0x1c200  115200
0x38400  230400
0x70800  460800
```

The strings explicitly mention 115200, 230400, and 460800 baud. The boot mode
and chip type select the rate; `_slow`/`_fast` filename suffixes alter the
mode flags in `dect_file_process`.

### Shared UART with console

When mode bit `0x4` is set, `dect_file_process` calls `msm_console_stop()` and
prints the shared-UART markers; after upload it calls `msm_console_start()`.
This is the reason the loader is sensitive to console traffic during upload.

## 4. DECT UART handshake and upload protocol

### 4.1 Slow/normal path

For the normal path, the loader waits for STX (`0x02`) from the DECT chip.
After receiving STX it sends:

```text
SOH (0x01)
length header:
  first-level:  2 bytes, big-endian payload length
  second-level: 4 bytes, big-endian payload length
```

`dect_loader` logs:

```text
dect_loader144xx: STX received - send SOH and len 0x%02x%02x...
```

It then waits for an ACK (`0x06`) before sending data.

### 4.2 Fast/HELLO path

When the fast path is selected, the loader writes the 11-byte string:

```text
HELLO DCX81
```

It reads 11 characters back and compares them with that string. On a match it
sends the observed four bytes:

```text
0x11 0xba 0x5e 0xba
```

Then it enters state 4, which sends a four-byte length field:

```text
sl[0], sl[1], 0x00, 0x00
```

and resumes payload transmission from `sl[2]`. This is the observed
fast/HELLO path; the mode bits select it. The zero-padded length is the same
value as the 2-byte first-level length.

### 4.3 ACK/NACK and data

State 2 waits for:

```text
0x06  ACK   -> start sending payload
0x15  NACK  -> read four NACK/error bytes and resynchronize
0x02  STX   -> resynchronize/violation handling
```

State 3 sends payload bytes from the current offset. In the slow path it
checks the UART after data bytes:

```text
0x00  ignored, QCA UART workaround
0x15  NACK reported
other bytes -> error/reset
```

At the end of the image, the loader compares the last image byte (the XOR
checksum) with the byte returned by the DECT side:

```text
match    -> send ACK 0x06, log crc ok, msleep(10), success
mismatch -> send NACK 0x15, log crc failure
```

The fast first-level path logs `sending complete` without this checksum wait.

### 4.4 Timeouts and retries

Observed bounds:

```text
0x7e (126) character-poll iterations
0x0b (11) retries after a false answer
0x10 (16) first-level reset retry count
0x05 (5)  second-level reset retry count
10 ms     settle after a correct CRC
```

Polling calls `msm_dectuart_get_char()`, converts one jiffy with
`jiffies_to_msecs(1)`, and uses `arm_delay_ops` for hardware delays. These are
busy-wait bounds, not POSIX timeouts.

### 4.5 Observable protocol summary

```text
host                          DECT
  |                            |
  | reset low/high             |
  | UART init (baud)           |
  |                            |
  | <--- STX (0x02) -----------|
  | SOH + length header ------>|
  | <--- ACK (0x06) -----------|
  | payload bytes ------------>|
  | <--- byte/checksum --------|
  | ACK (0x06) / NACK (0x15) ->|
```

For the fast path the STX/ACK exchange is replaced by `HELLO DCX81` and the
four-byte `0x11 0xba 0x5e 0xba` reply.

## 5. Intel HEX conversion: `ihex2bin`

`ihex2bin()` (`0x1ee8`, size `0x878`) loads a firmware file through
`request_firmware()`, validates and parses Intel HEX, and produces the
firmware image consumed by `dect_loader`.

### 5.1 Accepted record types

```text
0x00  data
0x01  EOF
0x02  extended segment address (base = value << 4)
0x04  extended linear address  (base = value << 16)
```

Other record types are rejected as `unsupported rectype`.

The parser:

- verifies the Intel HEX checksum;
- rejects non-`:` lines;
- tracks the current upper address;
- groups contiguous data into blocks;
- inserts an 8-byte block header;
- checks the 0x30005-byte vmalloc buffer limit.

### 5.2 Block and image layout

Each block in the output is:

```text
u32be address
u32be data_length
u8    data[data_length]
```

The complete converted image is:

```text
first-level (ihex2bin mode 0):
    u16be payload_length
    blocks...
    u8    xor_checksum
    total = payload_length + 3

second-level (ihex2bin mode 1):
    u32be payload_length
    blocks...
    u8    xor_checksum
    total = payload_length + 5
```

`dect_file_process()` calls `ihex2bin(..., 0)` for the first-level file and
`ihex2bin(..., 1)` for the second-level file. The outer length field is what
`dect_loader` sends before the payload.

### 5.3 Decoded supplied firmware

The local analysis parser produced:

```text
dectfw_firstlevel_441_slow.hex
  618 data bytes, 1 block
  block: address 0x00010080, length 0x26a
  payload: 0x272 bytes
  outer header: u16be 0x0272
  total image: 0x275 bytes

dectfw_secondlevel_441.hex
  54047 data bytes, 9 blocks
  payload: 0xd367 bytes
  outer header: u32be 0x0000d367
  total image: 0xd36c bytes

dectfw_secondlevel_441p2test.hex
  49736 data bytes, 8 blocks
  payload: 0xc288 bytes
  outer header: u32be 0x0000c288
  total image: 0xc28d bytes
```

All three HEX files have valid Intel HEX checksums. The first-level file uses
extended linear address 0x0001 and starts at `0x00010080`; the second-level
files start at address 0.

## 6. Firmware patching: `patch_dectfw`

`patch_dectfw()` (`0x1954`, size `0x594`) applies AVM-specific patches to the
converted image before upload.

Inputs:

```text
r0 = converted image
r1 = dectmode (0 or value)
r2 = base/address descriptor
```

Observed behavior:

1. Calls `avm_prom_get_config(1, buf, 0x40)` to read up to 64 bytes of DECT
   configuration from the bootloader/prom environment.
2. If no config is available, uses the static default patch template
   `.rodata+0x4e`:

   ```text
   01 05 30 32 37 30 50     // tag 1, length 5, data "0270\x50"
   ```

3. Uses `get_bufaddr_from_dectaddr()` to map AVM block addresses to image
   offsets, and `replace_tag()` to replace matching TLV payloads.
4. Scans for the RFPI tag:

   ```text
   tag 1, length 5
   data[2..5] == "0270"
   ```

   The real RFPI is derived from the ASCII MAC environment variable `maca`
   via `get_mac_ziffer()` and written as 5 bytes. The code checks each MAC
   nibble, builds a 32-bit value, sets the AVM marker bytes to `0x02, 0x70`,
   and logs `patch RFPI to ...`.
5. Adds/updates the DECT mode tag:

   ```text
   tag 7, length 1, value = dectmode
   ```

   This is the `piglet_dectmode=0x105` value passed by the stock init script.
6. For tag 9 length 22, logs the stub-version record:
   `[piglet]%s: Stub version information tag found ...`.
7. Recomputes the XOR checksum and writes it into the image.

The tag nesting is AVM-specific; `replace_tag` and `get_bufaddr_from_dectaddr`
should be treated as a TLV-in-block format, not as a generic Intel HEX parser.

`Piglet_noemif.ko` does not read `/var/flash/dect_eeprom` directly. The
`/var/flash/dect_eeprom` string belongs to `avm_dect.ko`; Piglet gets its
configuration from `avm_prom_get_config()` and the `maca` environment. The
supplied `firmware/dect_eeprom` is a default/reference image for the AVM DECT
driver, not a Piglet input file.

## 7. TDM/PCM interface check

`Check_TDMInterface()` (`0x3f0c`, size `0x240`) is called from
`piglet_loader_thread` unless the Host CPU is configured as master.

It:

- reads `ipq40xx_get_cyclefreq()`;
- scans hw_config for `gpio_avm_pcmlink_fsc` and `gpio_avm_pcmlink_dcl`;
- obtains their register bases with `dakota_gpio_get_membase()`;
- measures FSC/DCL toggling with `ipq40xx_get_cycles()`;
- logs `[piglet]TDM: FS: %u Hz CLK: %u Hz`;
- returns failure flags if FSC/DCL are missing or below the measured threshold.

If `piglet_hostclkmaster`/Host-CPU-master is set, the loader skips the TDM
check. This is a separate dependency from the DECT UART: audio still needs
`pcmlink.ko` and the TDM/PCM hardware.

## 8. Optional Piglet FPGA bitfile path

`piglet_bitfile_process()` (`0x4e0`, size `0x164`) and the XBIT helpers load
an optional FPGA bitfile through `request_firmware()`:

```text
profile+0x04 = XBIT data
profile+0x08 = XBIT done (input)
profile+0x0c = XBIT clock
profile+0x10 = XBIT program
```

`XBIT_Init` configures PROG, DATA, CLK, and DONE; `XBIT_WriteData` clocks the
bitfile; `piglet_bitfile_process` checks the DONE pin. `piglet_reset` returns
immediately if PROG is `-1`.

The default 7530 profile has all these GPIOs `-1`, so this path is not used
for the 7530 DECT-only configuration. The optional module parameters are:

```text
piglet_bitfile
piglet_potsbitfile
piglet_bitfilemode
```

`Piglet_noemif` also contains a small UART sniffer netlink/socket interface
(`dectuart_sniffer_*`) used for debug capture; it is not required for the
loader protocol.

## 9. Dependencies to replace on Linux 6.12

| Original API | Purpose | Linux 6.12 replacement |
|---|---|---|
| `msm_dectuart_init/get_char/put_char/exit` | QCOM DECT UART | UART/serdev client, tty or serdev callbacks |
| `msm_console_stop/start` | share UART with console | serdev console arbitration / DT `linux,console` policy |
| `dakota_gpio_ctrl/out_bit/in_bit/get_membase` | GPIO and register access | `gpiod_*`, regmap, pinctrl |
| `avm_get_hw_config_table` | AVM board GPIO table | device tree, `nvmem`, board data |
| `avm_prom_get_config` | 64-byte DECT config | `nvmem`/DT firmware or board EEPROM |
| `PowerManagment*` | AVM power management | runtime PM, regulator, clock framework |
| `avm_event_*` | AVM event bus | notifier chain or uevent |
| `request_firmware` | load HEX/bitfile | `request_firmware()` (still available) |
| `vmalloc`/`vfree` | 0x30005 image buffer | `vmalloc` or `kvmalloc` |
| `arm_delay_ops` | hardware delays | `udelay`/`ndelay`/`fsleep` |
| `jiffies_to_msecs` busy polling | UART timeouts | completion/timeout APIs; do not busy-wait |

The important hardware abstraction is not the old kernel API alone: the
UART, reset GPIO, DECT RD pin, TDM FSC/DCL, and optional FPGA pins must be
described in device tree (or board data) instead of AVM's `hw_config` table.

## 10. Unresolved questions

1. Exact `HWRevision` matching for this 7530 image. The static fallback
   profile is `"235"`, but the runtime environment may select another profile.
2. Whether the 7530 production hardware uses GPIO 18/16 exactly as the
   fallback profile states. These are table values, not hardcoded physical
   facts.
3. Exact slow/fast mode bit-to-baud mapping for every chip variant; only the
   constants and observed branches are proven.
4. The exact semantic of the last image checksum byte in the fast path; the
   slow path clearly compares it with a DECT response.
5. Whether `Check_TDMInterface` is skipped on the 7530 stock configuration
   because of `piglet_hostclkmaster`, or whether FSC/DCL are present.
6. The complete TLV nesting used by `patch_dectfw`; RFPI, dectmode, and stub
   version tags are proven, but not every possible tag.
7. Whether the optional Piglet FPGA path is ever enabled on 7530 variants.

## 11. Confidence

| Conclusion | Confidence | Basis |
|---|---|---|
| profile field offsets and default GPIO values | high | `.data`, `get_profile` disassembly |
| DECT reset/UART path | high | `dect_loader` state 0 |
| baud constants | high | immediates in `dect_loader` |
| STX/SOH/ACK/NACK/HELLO bytes | high | strings and control flow |
| state machine order | high | jump table and block structure |
| timeout/retry bounds | medium | constants and polling loops |
| Intel HEX block format | high | `ihex2bin` writes |
| outer first/second length and checksum | high | `ihex2bin` finalization |
| RFPI/dectmode/stub tags | high | `patch_dectfw` comparisons |
| exact checksum exchange semantics | medium | control flow, no runtime trace |
| TDM check behavior | medium | static control flow |
| optional FPGA path unused on 7530 | medium | default profile all `-1` |

## Evidence files

```text
reports/piglet.annotated.txt
reports/piglet.init-exit.disasm.txt
reports/piglet.disasm.txt
reports/piglet-callgraph.txt
reports/piglet-firmware-layout.txt
src/tools/hex_inspect.py
```
