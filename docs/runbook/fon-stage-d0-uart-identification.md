# Stage D0 runbook: identifying the SC14448 UART and reset on the board

> **Status: operational document.**
> This is a runbook, not an evidence record.  Hardware facts are maintained in
> `../fon-known-facts.md`; unresolved items in `../fon-open-questions.md`.

Status: **plan only.**  Nothing in this runbook has been executed.  Every
step needs the owner's explicit go-ahead, and the active steps need a
separate one.

**Read §0 first.**  The source and compiled-DTB analysis
(`../history/fon-dialog-board-uart-identification.md`) shows that the AVM DECT
loader and the OpenWrt console use the **same known UART controller**
(`blsp_uart0` @ `0x78AF000` on `gpio16`/`gpio17`).  No independent second UART
path was found in this configuration.  That is **not** proof that the four
pads or those pins reach the SC14448, and it is **not** proof that no other
UART hardware exists on the board.

---

## 0. What is known, and what is not

| Assumption | Status |
|---|---|
| the DECT loader and the console share one UART controller | **confirmed for this DTS** (`msm_serial.c` fallback + DTB) |
| a second *enabled* UART exists in the HW236 DTB | **ruled out** (`serial@78b0000` `disable`) |
| a mux/buffer/level shifter sits between SoC and Dialog | **UNKNOWN** |
| the four console pads are the Dialog UART | **plausible but unproven** — the port *is* the console, the physical path is untraced, and the pads sit near the SC14448 |
| the voltage on the pads | **UNKNOWN — not measured** |
| the voltage on the SC14448 side | **UNKNOWN** |
| GPIO16/GPIO17 TX vs RX | **UNKNOWN** — not encoded in DT |
| GPIO40 electrical polarity at the chip | **UNKNOWN** |

Because the port may be shared, a capture on the pads will show **console
traffic and any Dialog traffic on the same pair of wires**.  Distinguishing
them is §4.

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
package, record it as UNKNOWN and stop.  Never use a continuity tester on a
powered board.

## 3. Powered: high-impedance only

Permitted equipment: an oscilloscope with a ×10 probe, or a logic analyser
that supports a **1.8 V** threshold (input range safe for both 1.8 V and
3.3 V signals).  Only one ground connection, to a **verified** ground on the
low-voltage side of the board.

**Not permitted at this stage:**

* connecting the TX output of a USB-UART adapter to any pad — **not even if
  the same adapter already works as a console**, because the pad's electrical
  role at the Dialog end is unknown;
* connecting the adapter's VCC;
* applying any external 1.8 V or 3.3 V;
* touching the FON/DSL side or the telephone line.

### Measurement table

| Point | What to measure | Expected variants | Conclusion |
|---|---|---|---|
| Console TX (as identified by §2 / owner) | idle voltage, scope ×10 | 1.8 V or 3.3 V steady-high | confirms the logic level of the console TX |
| Console RX | idle voltage, scope ×10 | 0 V / 1.8 V / 3.3 V; activity only while the host sends | preliminary identification of the RX pad |
| Suspected series resistor | resistance, board **unpowered** | direct (~0 Ω) or a series value | whether the pad is separated from the SoC |
| GPIO40 net (if located) | voltage only, scope ×10 | 0 V / 1.8 V / 3.3 V | level only — **not** reset polarity |
| Dialog-side UART (if a separate point is found) | level and activity | **UNKNOWN** | only after physical identification |

**Never** push a TX into an unknown pad.  A low/high idle reading alone is not
proof of "not UART": a line can be held low or be the receive side.

Do **not** toggle GPIO40 in this stage.

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
  schematic.  `OUT_ACTIVE_HIGH` in the AVM table is a software convention and
  must not be read as the electrical polarity.

## 6. GO / NO-GO

| Point | Decision | Condition |
|---|---|---|
| the four console pads, passive continuity | **GO** | board unpowered, multimeter only |
| the same pads, scope/logic analyser | **GO** | 1.8 V-capable analyser, single verified GND, high-impedance probe only |
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
