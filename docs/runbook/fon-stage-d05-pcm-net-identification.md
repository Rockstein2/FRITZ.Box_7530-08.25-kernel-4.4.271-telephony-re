# Stage D0.5 runbook — finding the PCM net and probing FSC/BCLK

> **Status: instructions only.  Nothing here has been executed.**
> Owner's bench, owner's go-ahead.  No GPIO, reset, DMA or firmware action.

The analysis behind this is in `../fon-d05-pcm-net-identification.md`.
**Read the warning in §0 first: no test point is known yet.**

---

## 0. What is true before any measurement

| Statement | Status |
|---|---|
| GPIO20–GPIO27 are AVM's documented PCMLINK candidates on HW236 | board table |
| Their physical connection to the SC14448 and the active pinmux | **UNKNOWN** |
| The I2S function is also reachable on other GPIOs in the SoC | `pinctrl-ipq4019.c` |
| A specific GPIO is FSC or BCLK | **UNKNOWN** — only MUX2/MUX3 name groups |
| A board pad anywhere carries FSC/BCLK | **UNKNOWN** |
| Groups A/B are PCM | **UNKNOWN** — not established by anything |
| The console pads are PCM | **no** — they are UART (`VCC RX TX GND`) |
| Linux can see the clocks via GPIO | **no** — too slow, C0 already showed this |

So the runbook starts with **finding the net**, not with connecting a scope.

## 1. Stage 1 — unpowered continuity search

Board **disconnected** from mains and USB.

### 1.1 What to look for

| # | From | To | What it tells you |
|---|---|---|---|
| 1 | `GND` console pad | any pad of group A / group B | which pads are ground |
| 2 | A4 | `GND` console pad | confirms A4 is ground (expected) |
| 3 | B1 | `GND` console pad | confirms B1 is ground (expected) |
| 4 | a resistor end near the SC14448 | a group A / B pad | whether a pad reaches a PCM candidate line |
| 5 | a resistor end near the SC14448 | the other end | whether it is a series element (≈0 Ω vs a value) |
| 6 | any candidate pad | `VCC` 1.8 V / 3.3 V rail | excludes power wrong-guesses |

**Do not** try to reach a QFP pin with a probe while powered.  With the board
off, a pin can be touched with a fine probe only if it is already exposed and
the owner is comfortable doing so; otherwise stop and record `UNKNOWN`.

### 1.2 How to interpret the result

| Reading | Meaning |
|---|---|
| ≈ 0 Ω | direct copper connection |
| a stable value (e.g. 33 Ω, 100 Ω) | series resistor — the far end is the safer scope point |
| no continuity, open | not the same net (a buffer/transistor may still separate them) |
| a diode-like reading | semiconductor in the path; not a PCM line |

**Absence of continuity is not proof of absence of a path** — a series
resistor, buffer or transistor can sit between two points.

## 2. Stage 2 — passive scope, only on an identified net

Only after stage 1 names a net.  The two measurements are FSC and BCLK; do
them one at a time, one channel.

### 2.1 Setup

| Item | Value |
|---|---|
| Ground | short lead to a **verified** board ground (console `GND` pad) |
| Probe | ×10, ≥ 1 MΩ, ≤ 15 pF |
| Instrument | 1.8 V-capable front end; a plain digital scope is enough |
| Trigger | rising edge, ~0.9 V, normal, ~200 mV hysteresis |
| Overview time base | 200 µs/div (2 ms ≈ 16 frames) |
| Detail time base | 20 µs/div (200 µs ≈ 1.6 frames) |

### 2.2 FSC

| Property | Expected |
|---|---|
| Frequency | 8000 Hz |
| Period | 125 µs |
| Shape | square-ish, one pulse per frame |

### 2.3 BCLK

| Property | Expected | Source |
|---|---|---|
| Frequency (formula) | 1 024 000 Hz | 8 slots × 16 bit × 8 kHz |
| Frequency (OEM log) | 1 025 720 Hz | FRITZ!OS print |
| Edges per slot | 16 | GPL |

On **our** board under OpenWrt neither frequency has been measured; both are
expectations, not results.

### 2.4 Success criteria

| Observation | Conclusion |
|---|---|
| FSC 125 µs ±1 %, stable, BCLK 16 edges per slot | clocks confirmed — C4 becomes meaningful |
| BCLK only | chip started, TDM not framed |
| nothing on the net, but the same net runs under FRITZ!OS | OpenWrt-specific gate (reset/firmware/clock) |
| nothing under both systems | wrong net, or the chip is not clocked |

## 3. Stage 3 — results template

Fill one row per net actually measured.

| Net | Probe point | Identified by | DC | Frequency | Vpp | Result |
|---|---|---|---|---|---|---|
| FSC candidate | | continuity from __ | | | | |
| BCLK candidate | | continuity from __ | | | | |
| MCL candidate | | continuity from __ | | | | |

## 4. What absence does **not** mean

A flat line must not be read as "SC14448 broken", and must not be read as
"the full DECT firmware is required".  Possible causes, each to be excluded
separately:

- the SC14448 is held in reset (GPIO40 reads low as an input);
- no firmware was uploaded;
- the audio block is gated for another reason;
- the probe is on the wrong net or loads the line;
- the pins were never muxed to I2S on this board under this boot path.

## 5. GO / NO-GO

| Action | Decision | Condition |
|---|---|---|
| unpowered continuity on pads and resistors | **GO** | board disconnected |
| scope on a net identified in stage 1 | **GO** | 1.8 V-capable front end, one verified ground |
| scope on a QFP pin while powered | **NO-GO** | risk of short; find a pad/resistor instead |
| probing group A/B "because they are there" | **NO-GO** | they are not identified as PCM |
| GPIO40 toggle | **NO-GO** | separate approval |
| firmware upload | **NO-GO** | separate stage |
| any DMA/TDM start | **NO-GO** | `dma_start` returns `-EOPNOTSUPP` |

## 6. What the owner should send back

1. Which pads/resistors were measured and how each was identified.
2. Continuity results (open / 0 Ω / value).
3. If a net was found: FSC period, BCLK frequency, edges per slot, and raw
   samples.
4. Whether the same point shows clocks under FRITZ!OS.
5. If no net is found: that is a valid answer — say so, and we look for a
   schematic or a higher-resolution photo of the SC14448 surroundings.
