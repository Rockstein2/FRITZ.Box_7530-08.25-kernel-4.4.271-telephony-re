# Stage D0 runbook: identifying the SC14448 UART and reset on the board

Status: **plan only.**  Nothing in this runbook has been executed.  Every
step needs the owner's explicit go-ahead, and the active steps need a
separate one.

**Read §0 first.**  The most important finding of the source analysis is that
there is probably **no separate SC14448 UART to find**: the DECT loader uses
the same `blsp_uart0` as the OpenWrt console (`docs/fon-dialog-board-uart-identification.md`).

---

## 0. What this changes

| Assumption | Status |
|---|---|
| there is a second UART for the Dialog | **not supported** by the sources: `serial@78b0000` is disabled and the DECT driver attaches to the first probed port |
| the four console pads are the Dialog UART | **plausible** — the port *is* the console — but the physical path from the pads to the SoC and to the Dialog is untraced |
| the Dialog side is 1.8 V | **UNKNOWN** |
| GPIO40 is active-low at the chip | **UNKNOWN** — `OUT_ACTIVE_HIGH` is a software convention |

If the pads are the shared port, a capture there will show **console traffic
and any Dialog traffic on the same pair of wires**.  Distinguishing them is
§4.

## 1. Before touching anything

| # | Check | How |
|---|---|---|
| 1 | Identify the four pads | photo of the pad row with the board revision visible |
| 2 | Identify GND among them | continuity to a known ground **with the board unpowered** |
| 3 | Locate GPIO40's net | board photo or a labelled test point; do **not** probe a BGA ball |
| 4 | Confirm the board model | 7530, not 7530 AX |

## 2. Unpowered: passive continuity only

All of this with the board **disconnected** from power and from USB.

| # | Measurement | What it answers |
|---|---|---|
| 1 | pad ↔ pad resistance | which pads are the signal pair and which is GND |
| 2 | pad ↔ nearest series resistor | whether the pad goes through a resistor |
| 3 | resistor ↔ the SoC-side net (if reachable) | whether there is a series element before the SoC |
| 4 | pad ↔ any level-shifter package pin | whether a shifter exists at all |

**Never** probe a BGA ball directly.  If a net can only be reached under the
package, record it as UNKNOWN and stop.

## 3. Powered: high-impedance only

Permitted equipment: an oscilloscope with a ×10 probe, or a logic analyser
that supports a **1.8 V** threshold.  Only one ground connection, to a
verified board ground.

**Not permitted at this stage:**

* connecting the TX output of a USB-UART adapter to any unknown pad;
* connecting the adapter's VCC;
* applying any external 1.8 V or 3.3 V;
* touching the FON/DSL side or the telephone line.

| # | Measurement | Expected if the pad is the console TX | Do not conclude from |
|---|---|---|---|
| 1 | idle level on each pad | a steady high (UART idle) | a low level does not prove "not UART" — it may be held low or be RX |
| 2 | waveform during boot | 115200 8N1 console text | absence during a quiet period |
| 3 | the other pad | the RX line: idle high, brief activity only while the host sends | |
| 4 | any third pad | possibly GND or a boot strap | |
| 5 | GPIO40 level | a steady level, most likely low | this does **not** prove reset is asserted — a pull resistor could hold it |

## 4. Capturing, and telling console from loader traffic

Parameters:

| Item | Value |
|---|---|
| channels | two, one per pad, shared time base |
| sample rate | ≥ 10× the bit rate; 1 Msa/s is enough for 115200, 10 Msa/s for margins |
| decoding | try 115200 8N1 first, then 9600 |
| storage | raw samples, not only decoded text |

| Observation | Console | Dialog / loader |
|---|---|---|
| text that looks like a kernel log | yes | no |
| text at 115200 with no `\n` framing | unlikely | possible (binary protocol) |
| byte pattern `0x02` then `0x01`/`0x06`/`0x15` | no | matches the ROM handshake in `piglet_protocol.h` |
| blocks starting with a 4-byte big-endian address | no | matches the AVM first-level format |
| a 4-byte big-endian length followed by that many bytes | no | same |
| activity that stops and never returns | possible (boot finished) | possible (loader waited for input and timed out) |

**A key limitation.**  The console and the loader share one port.  If the
Dialog never powers up, the capture will contain **only** console traffic,
and that is **not** evidence that the Dialog is absent — only that this port
carried nothing else during the window.

## 5. Reset line

* Read the GPIO40 level only; **do not toggle it** in this stage.
* Record the level at boot and after the system settles.
* A steady low level is consistent with "reset asserted" but also with a
  pull-down and an inactive chip; the two cannot be separated without the
  schematic.

## 6. GO / NO-GO

| Point | Decision | Condition |
|---|---|---|
| the four console pads, passive continuity | **GO** | board unpowered, multimeter only |
| the same pads, scope/logic analyser | **GO** | 1.8 V-capable analyser, single verified GND, probe only |
| GPIO40 test point, voltage only | **GO if the net is identified** | otherwise NO-GO |
| Dialog BGA balls | **NO-GO** | no probing under the package |
| any TX injection into the UART | **NO-GO at Stage D0** | requires a later stage and separate approval |
| GPIO40 toggle / reset pulse | **NO-GO at Stage D0** | separate approval |
| firmware upload | **NO-GO** | separate project stage |

## 7. What the owner should photograph

1. the pad row at macro distance, with the board revision visible;
2. the SC14448 package and the area around it;
3. any small SOT/SOIC package between the SoC and the Dialog;
4. the GPIO40 net if a labelled resistor or via is visible.
