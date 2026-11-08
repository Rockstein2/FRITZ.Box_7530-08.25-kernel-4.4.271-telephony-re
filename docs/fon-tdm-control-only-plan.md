# D0.4 — passive FSC/BCLK verification and C3 safety gates

> **Status: plan only.  Nothing here has been executed.**
> No probe, GPIO, reset, DMA, firmware upload or MMIO write was performed to
> write this document.  The existing passive measurement procedure is in
> `runbook/fon-tdm-passive-test.md`; this file adds the C3 decisions and the
> concrete scope settings.

Purpose: answer two questions **without changing anything**:

- **Q4** — is an 8 kHz frame sync actually present on the board?
- **Q27** — is the SC14448 running and generating the TDM clocks?

---

## 0. Why this gates the driver

`history/fon-adss-tdm-channel-map.md` establishes the channel mapping
(`stereo-tx 0` / `stereo-rx 3` on the `tdm@0` node).  The driver can build
frames in memory, but it cannot validate them until the SC14448 is known to
supply BCLK/FSC.  Until then, any DMA start would run against a dead or
unclocked bus.

So C3 stops at **dry-run**, and D0.4 is the measurement that unlocks C4.

## 1. Expected signals and where they come from

| Quantity | Value | Source |
|---|---|---|
| FSC | 8000 Hz (125 µs period) | OEM log `TDM: FS: 8000 Hz` |
| BCLK (OEM-reported) | 1 025 720 Hz | OEM log |
| BCLK (GPL formula) | 1 024 000 Hz = 8 × 16 × 8000 | GPL (`ipq-adss-avm.c:2060`) |
| BCLK on **our** board under OpenWrt | **UNKNOWN** | scope not yet applied |
| Slots per frame | 8 | GPL |
| Bits per slot | 16 | GPL |
| Direction | **SC14448 is master; IPQ4019 is slave** | GPL slave path, board DTS |

**1 025 720 Hz has not been measured by us.**  It is what FRITZ!OS printed,
and it is 0.17 % above the GPL formula.  Treat it as the expected value to
look for, not as a confirmed measurement on this board under OpenWrt.

The IPQ4019 will **never** generate these clocks in this configuration
(`master = 0` → `bclk = 254` sentinel = external pad clock).  Therefore a
missing clock points at the **SC14448 or the path to it**, not at the SoC
failing to drive its own output.

### 1.1 Candidate pins from the AVM board table

`Fritz_Box_HW236.dtsi` lines 344-383:

| Signal | PINMUX2 | PINMUX3 | Direction |
|---|---|---|---|
| MCL | GPIO20 | GPIO24 | input |
| DCL (BCLK) | GPIO21 | GPIO25 | input |
| FSC | GPIO22 | GPIO26 | input |
| DI | — | GPIO23 | input |
| DO | — | GPIO27 | output |

Only **PINMUX3** has data lines, so a full channel is the second column.  But
see §2: these are **AVM board-table class names, not IPQ4019 TLMM
functions**.

## 2. The constraint: Linux has no mux owner

Stage C0 (passive, already run) found that **no Linux consumer owns the PCM
pins** and that mainline `pinctrl-ipq4019.c` exposes no PCM/TDM function for
GPIO20-27.  OEM 08.25 live readback now shows the actual mixed state:
GPIO21/22=`func 2`, GPIO23/25/26/27=`func 3`, GPIO20/24=`func 0`
(`reference/oem-08.25/console/2026-11-08/`). The OpenWrt-side `FUNC_SEL`
remains unknown (Q31/Q77).

Consequences:

1. Mainline Linux cannot read TDM activity through its pinctrl state; the
   hardware mux value is unknown.
2. The **only** way to answer Q4/Q27 is an electrical measurement at a real
   test point (or a reviewed TLMM readback).
3. Absence of a Linux-visible signal is **not** evidence that the SC14448 is
   silent.

## 3. Safe measurement points

| Point | Usable for | Status |
|---|---|---|
| group A (A1-A4) | level only so far; electrical identity **UNKNOWN** | not proven to be PCM |
| group B (B1-B4) | level only so far; electrical identity **UNKNOWN** | not proven to be PCM |
| the four console pads | console UART, not TDM | wrong signal |
| SC14448 QFP perimeter pins | possible, but must not be probed live | last resort |
| IPQ4019 balls | not accessible | — |

**No test point is yet known to carry FSC/BCLK.**  Do not assume group A/B
are the PCM lines: their measured levels (A3 = 0.6 V, SOT pin 2 = 0.8 V) are
interesting but unexplained, and the console is explicitly on other pins.

If a clock must be probed at the chip, prefer the **SC14448 side of a series
resistor**, with the board unpowered to identify the net, and only then probe
it live.  Never touch a QFP pin with a probe while the board runs unless
continuity to a safer pad exists.

## 4. Scope / analyser settings

### 4.1 Two settings, two purposes

| Mode | Time base | Shows | Purpose |
|---|---|---|---|
| **Overview** | 200 µs/div × 10 div = 2 ms | ~16 FSC frames | is anything toggling at all? |
| **Detail** | 20 µs/div × 10 div = 200 µs | ~1.6 frames | front shape, edges per slot |

(The earlier draft said "200 µs/div ≈ 1.6 frames"; that was wrong — 200 µs/div
spans 2 ms, which is 16 frames.)

### 4.2 Common settings

| Parameter | Value | Why |
|---|---|---|
| Probe | ×10, ≥ 1 MΩ, ≤ 15 pF | do not load a 1 MHz clock |
| Instrument threshold | **1.8 V-capable** | a 3.3 V-only front end may read permanent low |
| Ground | one lead, to a verified low-side board ground | avoid ground loops |
| Trigger | rising edge, ~0.9 V, normal, ~200 mV hysteresis | FSC edges |
| Channels | FSC candidate + BCLK candidate, same time base | confirm 16 BCLK per slot |

Never drive a signal, inject a clock, connect a signal generator, or hold a
probe on more than one net at once.

### 4.3 Capture plan

**A. Short high-speed capture** (digital scope, single-shot or normal):

- two channels, FSC candidate + BCLK candidate;
- ≥ 10 MSa/s per channel (≥ 10 samples per 1 µs BCLK period);
- long enough for a few dozen to a few hundred frames — at 10 MSa/s that is
  ~1.6 kB per frame per channel, so a few ms of memory covers hundreds;
- save the **raw samples**, not only a decoded view.

**B. Long stability observation** (not a 10 s = 100 Msample dump):

- use the scope's hardware frequency/period measurement, or a counter, on
  the FSC line;
- watch for **dropouts** (a missed FSC) and drift over minutes;
- if a stream capture is wanted, lower the sample rate to what the period
  measurement needs and record only the FSC channel.

A plain digital oscilloscope is sufficient: mode A for shape, mode B for
stability.  A logic analyser is convenient but not required.

## 5. How to distinguish real TDM from noise

| Observation | Meaning |
|---|---|
| FSC period 125 µs ± 1 %, jitter < 1 µs | genuine 8 kHz frame sync |
| exactly 16 BCLK edges between two FSC edges per slot, 128 per frame | genuine 8-slot 16-bit TDM |
| stable duty cycle, no missing edges over many frames | healthy master |
| BCLK present but FSC absent | partial init; chip started but TDM not framed |
| random bursts, no fixed period | not TDM; likely unrelated digital activity |
| flat line | not clocking — see §6 for what that does **not** prove |

A single capture is not enough: a stability run (mode B) is needed to rule out
a one-off glitch being mistaken for a clock.

## 6. When absence does **not** prove a fault

A flat line must not be read as "SC14448 broken", and it must not be read as
"firmware is required".  It may mean any of:

- the SC14448 is held in reset (GPIO40 was observed low as an input);
- no firmware has been uploaded under OpenWrt;
- the relevant clock is gated for another reason;
- the probe is on the wrong net, or loaded too heavily;
- the board's audio path behaves differently under OpenWrt for a reason not
  yet understood.

In particular, **"the FON needs the full DECT firmware" is still a
hypothesis**.  The AVM boot order makes it plausible, but no measurement has
shown that FON clocks stop when DECT firmware is absent.  Do not state it as
established.

Each of these has to be excluded separately before concluding the chip is
dead.  The comparison that matters is **FRITZ!OS vs OpenWrt on the same
point**: FRITZ!OS is known to print `TDM: FS: 8000 Hz CLK: 1025720 Hz`.

## 7. GO / NO-GO for D0.4

| Action | Decision | Condition |
|---|---|---|
| passive level measurement on A/B | **GO** | multimeter, board unpowered for continuity |
| scope on an identified TDM net | **GO** | net first identified unpowered; 1.8 V-capable front end |
| scope on a QFP perimeter pin | **NO-GO** unless a safer pad exists | risk of short/bridging |
| GPIO40 toggle | **NO-GO** | separate approval |
| firmware upload | **NO-GO** | separate stage |
| any DMA/TDM start | **NO-GO** | blocked by `dma_start` returning `-EOPNOTSUPP` |

## 8. What to report back

1. Which net was probed and how it was identified (continuity).
2. FSC period and jitter, from mode B.
3. BCLK frequency and edges per slot, from mode A.
4. Raw samples from the mode A capture.
5. Whether the same point shows clocks under FRITZ!OS.

With FSC/BCLK confirmed, C4 (active TDM) becomes meaningful; without them,
no driver change can be validated.
