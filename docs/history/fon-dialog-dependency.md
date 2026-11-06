# Dialog SC14448 dependency for the FRITZ!Box 7530 FON port

> **Status: historical analysis.**
> This document records the reasoning and evidence as of the date it was
> written.  Some of its `UNKNOWN` / `UNVERIFIED` markers have since been
> answered.
> - Current confirmed facts: `../fon-known-facts.md`
> - Current open questions: `../fon-open-questions.md`
> - This file is kept for the reasoning trail, not as a status report.

Status: **static analysis complete; no firmware was executed on the router**

> Boot-side detail is now in `fon-dialog-boot.md`.  The 7530 board table
> uses reset GPIO40 (not the fallback profile's GPIO18), and the DECT UART is
> the shared MSM UART at `0x078af000` (GPIO16/17).  The clean-room image
> parser in `src/fon-firmware/` was tested against the local images; the
> firmware itself was not uploaded.

This document answers whether the analog FON port can work without the
original Dialog SC14448 firmware, and what the minimum separate dependency
would be if it cannot.

The TDM hardware parameters are in `fon-tdm-hardware.md`.  The
`Piglet_noemif.ko` loader analysis is in `../../notes/piglet.md` and the raw
evidence in `../../reports/piglet*.txt`.

---

## 1. Stock boot chain

The stock system uses a chain of independent modules:

```text
S11-piglet:
  modprobe Piglet_noemif \
      dect_firstlevelfile=dectfw_firstlevel_441_slow.hex \
      dect_secondlevelfile=dectfw_secondlevel_441.hex \
      piglet_dectmode=0x105

E41-capi:
  modprobe pcmlink abmode=1
```

Later layers (`avm_dect.ko`, `dect_io.ko`, `isdn_fbox_fon5.ko`,
`capi_codec.ko`, `nlaudio.ko`, `ulpcmlink.ko`) implement the DECT stack,
CAPI, analog line policy, and PCM routing.  They are **not** part of the
minimal QCA ADSS/TDM transport.

The relevant split is:

```text
Piglet_noemif.ko
  - DECT reset GPIO and UART
  - first-level and second-level firmware upload
  - TDM clock-presence check
  - sends the piglet_ready event

pcmlink.ko
  - QCA ADSS/TDM/MBOX backend
  - PCM slot routing
  - registers the piglet_ready sink
  - waits for the event before normal control activity

SC14448
  - runs the uploaded firmware
  - TDM/PCM clock and frame master on the 7530
  - generates FSC/DCL/MCL and receives/sends the TDM stream
  - drives the external analog line/ring circuitry
```

Neither `Piglet_noemif.ko` nor the GPL QCA source contains a complete
SC14448 program.  The second-level firmware image is a separate binary
artifact.

---

## 2. What is uploaded

The local images are:

```text
firmware/dectfw_firstlevel_441_slow.hex
firmware/dectfw_secondlevel_441.hex
firmware/dectfw_secondlevel_441p2test.hex
```

Observed Intel-HEX contents:

| Image | Payload |
|---|---|
| first-level `_slow` | 618 bytes starting at address `0x00010080` |
| second-level 441 | about 54,047 bytes, nine address blocks, `0x00000000`–`0x00028dcd` |
| second-level 441p2test | about 49,736 bytes, eight blocks |

`Piglet_noemif.ko` converts Intel HEX blocks into its own upload format and
patches AVM tags (RFPI, DECT mode, stub version) before sending them over the
DECT UART.  It does not read `/var/flash/dect_eeprom` itself.

The UART path is separate from the QCA ADSS/TDM bus.  Firmware loading and
TDM/PCM data are not the same transport:

```text
firmware:  IPQ4019 UART -> SC14448 loader
FON data:  IPQ4019 MBOX0/MBOX3 <-> SC14448 PCM/TDM
```

---

## 3. Firmware-load handshake

The loader's own handshake is **not** the `0xfefe`/`0x5555` TDM header.

From `../../notes/piglet.md` and `../../reports/piglet.annotated.txt`:

```text
slow/normal path:
  wait for STX (0x02)
  send SOH (0x01)
  send length (2 bytes first-level, 4 bytes second-level, big-endian)
  wait for ACK (0x06)
  send image data and checksum
  NACK is 0x15

fast path:
  send "HELLO DCX81"
```

The stock init script uses `piglet_dectmode=0x105`.  The loader selects
`dectfw_firstlevel_441_slow.hex` and `dectfw_secondlevel_441.hex` on the normal
path; the `p2test` image is used only when a test flag is present.

This protocol is a **firmware-loader dependency**, not a QCA ADSS register or
PCM protocol.

---

## 4. TDM check and the `piglet_ready` gate

After `dect_file_process()` (both firmware images) the loader calls
`Check_TDMInterface()` unless `piglet_hostclkmaster` says the host CPU is the
clock master.

`Check_TDMInterface()`:

1. obtains the cycle counter;
2. looks up `gpio_avm_pcmlink_fsc` and `gpio_avm_pcmlink_dcl`;
3. samples both pins for roughly 100 ms;
4. prints:

   ```text
   [piglet]TDM: FS: %u Hz CLK: %u Hz
   ```

5. returns an error if either signal is missing or below its threshold.

On failure the loader prints:

```text
[piglet]bye bye - can't detect TDM-FS or TDM-CLK!
```

and does not reach the successful `piglet_ready` event.  On success it calls
`send_piglet_ready_event()`.

`pcmlink.ko` registers the sink `piglet_ready_sink`
(`avm_event_piglet_ready_cb`) and its control thread checks the readiness flag
before normal TDM/control processing.  The event is therefore a real startup
gate, not just a debug message.

Stock `S11-piglet` does not set `piglet_hostclkmaster`; the default path
expects the SC14448 to generate FSC/DCL.  This matches the QCA-side slave
configuration:

```text
tdm_dma+0x18 = 0 -> master=0 -> ADSS slave
```

and the board GPIO table, where FSC/DCL/MCL are inputs.

---

## 5. Can FON work without SC14448 firmware?

### 5.1 What can work without firmware

Read-only QCA-side operations can work independently of the SC14448:

- mapping ADSS/PCM/MBOX registers;
- reading `ADSS_GLB_TDM_CTRL_REG`, clock control, reset status;
- allocating DMA descriptors;
- running the offline frame encoding/decoding tests;
- observing whether the SC14448 is currently producing FSC/DCL.

This is why the diagnostic driver has a separate `dma_prepare` stage and no
automatic start.

### 5.2 What cannot be expected to work

Without a running SC14448 second-level firmware:

- the SC14448 normally supplies the FSC/BCLK/MCLK clocks (IPQ4019 is slave);
- no PCM/TDM stream is clocked, so the MBOX FIFO/DMA has no valid timing;
- no device responds to the 16-bit slot-5 control words;
- no hook/ADC status is produced on the RX TDM slot;
- no ring/line-feed command reaches the discrete LM324/BCP53-16 circuit.

Even if the QCA ADSS is reconfigured as clock master, the SC14448 still needs
a program to interpret the slot-5 control words and drive the line.  The
first-level image is a loader, not the application; the second-level firmware
is the part that contains the PCM/telephony behavior.

**Conclusion: FON control and audio are dependent on the SC14448 firmware.
The dependency is high-confidence from the stock boot flow but has not been
proven by a no-firmware hardware experiment.**  A no-firmware test would be
read-only (check for FSC/DCL and RX status), not a line/ring test.

---

## 6. Is a firmware handshake required before PCM?

There are two different handshakes:

| Handshake | Transport | Required before PCM? |
|---|---|---|
| STX/SOH/ACK (or `HELLO DCX81`) | DECT UART | Yes for the stock loader to upload firmware. |
| `piglet_ready` event | AVM event bus, IPQ4019 internal | Gate used by `pcmlink`; the standalone driver does not require the event, but the SC14448 must already be running. |
| `0xfefe` / `0x5555` | 16-bit TDM TX frame slots 1-4 | Not a UART handshake.  Exact SC14448 meaning is unknown. |
| Slot-5 control word | TDM/MBOX frame | Carries FON line control; no per-word ACK. |

The standalone transport must not try to perform the UART upload.  Firmware
loading remains a separate, optional dependency module.

---

## 7. What `0xfefe` and `0x5555` are not

`TxDMA` writes these values into 16-bit TDM words:

```text
slot 0: 0x0000
slot 1: 0xfefe
slot 2: 0xfefe
slot 3: 0xfefe
slot 4: 0x5555 (or 0x0000 when TDMPriv+0x808 != 0)
slot 5: FON control/status word
```

They are not:

- the UART firmware handshake (STX/SOH/ACK/HELLO);
- a shared-memory doorbell;
- a per-register sequence number or ACK.

The proven statement is only that `TxDMA` writes them as fixed TDM header/
idle words.  Their DECT/SC14448 semantic meaning (sync, idle code, channel
marker, or something else) is **unknown** and must not be guessed in driver
logic.  The diagnostic frame helper reproduces the Linux-side layout but does
not interpret these words.

---

## 8. Minimum startup sequence if firmware is used

A future integration that keeps the original SC14448 firmware would need:

1. Provide the DECT reset/UART and firmware files as a **separate** loader
   dependency.  Do not mix it into the ADSS/TDM driver.
2. Reset and upload first-level and second-level firmware using the UART
   protocol.
3. Wait until the SC14448 generates FSC/DCL (or use a documented
   `piglet_hostclkmaster` configuration if QCA is deliberately master).
4. Initialize QCA ADSS in slave mode:
   - `AUDIO_BLK_ARES` reset sequence;
   - 16-bit TDM, 8 slots, 8 kHz;
   - external pad clocks;
   - MBOX0 playback / MBOX3 capture;
   - 512-byte ping-pong buffers, 16 descriptors.
5. Start playback and capture in the correct order, then exchange slot-5
   control/status words.
6. Only after a separate high-voltage review, enable line feed/ring.

The current driver implements only step 1's DT/MMIO preparation and step 4's
descriptor preparation.  It does not upload firmware, start clocks, start
DMA, or touch the line.

## 9. Can SC14448 produce RX status without DECT userspace?

Probably yes at the firmware/hardware level: the second-level firmware runs
independently of the Linux DECT application stack, and `Check_TDMInterface`
does not require `avm_dect.ko` or userspace.  However, this is **not proven**:

- the stock boot order may require `avm_dect.ko` to configure DECT mode or
  PCM routing;
- the RX status bits may be gated by firmware state;
- no trace of the SC14448 without the AVM user-space stack was captured.

The conservative assumption is that firmware plus a minimal DECT control
channel may be needed, even if the full CAPI/SIP stack is not.

---

## 10. Recommended separation

Keep three layers separate:

```text
1. fon_tdm_drv.ko
   - QCA ADSS/PCM/MBOX transport
   - raw frame/control/status access
   - no Dialog firmware

2. sc14448_loader (separate)
   - DECT reset/UART
   - first/second-level firmware upload
   - readiness check
   - may be a userspace helper or a small kernel module

3. line/ring policy
   - only after the SC14448 interface is understood
   - high-voltage hardware review required
```

This avoids the original `pcmlink`/AVM event/`hw_config` stack and keeps the
firmware dependency explicit.  It also means the minimal TDM driver can be
compiled and tested without pretending that the FON line is operational.

---

## 11. Remaining unknowns

1. Whether the 7530 production SC14448 can generate FSC/DCL before a
   second-level upload (first-level-only experiment).
2. Whether `piglet_hostclkmaster` is ever set on production 7530 units.
3. Whether any stock `avm_dect.ko` initialization is required before the
   firmware accepts slot-5 line commands.
4. Exact SC14448 slot-5 bit semantics and the hook/ring/ADC/PWM mapping.
5. Exact firmware version compatibility with a standalone transport.
6. Whether a minimal firmware loader can legally and technically be
   distributed separately from the AVM DECT stack.

Until these are resolved, the status is **CONDITIONAL GO**: the QCA transport
is recoverable, but a fully independent FON driver is not yet proven.
