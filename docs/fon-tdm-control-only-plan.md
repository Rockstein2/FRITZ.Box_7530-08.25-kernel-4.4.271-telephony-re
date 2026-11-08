# D0.4 — passive FSC/BCLK verification and C3 safety gates

> **Status: plan only.  Nothing here has been executed.**
> No probe, GPIO, reset, DMA, firmware upload or MMIO write was performed to
> write this document.  The existing passive measurement procedure is in
> `../fon-tdm-passive-test.md`; this file adds the C3 decisions and the
> concrete scope settings.

Purpose: answer two questions **without changing anything**:

- **Q4** — is an 8 kHz frame sync actually present on the board?
- **Q27** — is the SC14448 running and generating the TDM clocks?

---

## 0. Why this gates the driver

`docs/fon-adss-tdm-channel-map.md` establishes the channel mapping
(`stereo-tx 0` / `stereo-rx 3` on the `tdm@0` node).  The driver can build
frames in memory, but it cannot validate them until the SC14448 is known to
supply BCLK/FSC.  Until then, any DMA start would run against a dead or
unclocked bus.

So C3 stops at **dry-run**, and D0.4 is the measurement that unlocks C4.

## 1. Expected signals and where they come from

| Signal | Expected | Source |
|---|---|---|
| FSC | 8 kHz, 125 µs period | OEM log `TDM: FS: 8000 Hz` |
| BCLK / DCL | ≈ 1 025 720 Hz measured (formula 1 024 000 Hz) | OEM log, GPL formula |
| Slots per frame | 8 | GPL |
| Bits per slot | 16 | GPL |
| Direction | **SC14448 is master; IPQ4019 is slave** | GPL slave path, board DTS |

The IPQ4019 will **never** generate these clocks in this configuration
(`master = 0` → `bclk = 254` sentinel = external pad clock).  Therefore:
**no clock on the wire means the SC14448 is not driving it**, not that the
SoC failed.

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

## 2. The decisive constraint: the pads are not muxed

Stage C0 (passive, already run) found that **no GPIO in the PCM group is
muxed to `i2s_rx`/`i2s_tx`/`i2s_td`**.  Mainline `pinctrl-ipq4019.c` exposes
no PCM/TDM function for GPIO20-27 at all; the ADSS block and the board wiring
drive those signals, not TLMM.

Consequences:

1. Linux cannot read the TDM activity through any GPIO/pinmux state.
2. The **only** way to answer Q4/Q27 is an electrical measurement at a real
   test point.
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

| Parameter | Value | Why |
|---|---|---|
| Probe | ×10, ≥ 1 MΩ, ≤ 15 pF | do not load a 1 MHz clock |
| Logic analyser threshold | **1.8 V-capable** | a 3.3 V-only front end may read permanent low |
| Ground | one lead, to a verified low-side board ground | avoid ground loops |
| Time base | 200 µs/div | ~1.6 frames across the screen |
| Trigger | rising edge, ~0.9 V, normal, ~200 mV hysteresis | FSC edges |
| Sample rate (LA) | ≥ 10 MSa/s | ≥ 10 samples per 1 µs BCLK period |
| Channels | FSC candidate + BCLK candidate, same time base | confirm 16 BCLK per slot |
| Storage | raw samples | decoded-only views hide periodic errors |

Never drive a signal, inject a clock, connect a signal generator, or hold a
probe on more than one net at once.

## 5. How to distinguish real TDM from noise

| Observation | Meaning |
|---|---|
| FSC period 125 µs ± 1 %, jitter < 1 µs | genuine 8 kHz frame sync |
| exactly 16 BCLK edges between two FSC edges per slot, 128 per frame | genuine 8-slot 16-bit TDM |
| stable duty cycle, no missing edges over ≥ 1000 frames | healthy master |
| BCLK present but FSC absent | partial init; chip started but TDM not framed |
| random bursts, no fixed period | not TDM; likely unrelated digital activity |
| flat line | SC14448 not clocking (§6) |

A single capture is not enough: record at least **10 s** continuously and
count frames, so a glitch is not mistaken for a clock.

## 6. When absence does **not** prove a fault

A flat line must not be read as "SC14448 broken":

- the chip may be held in reset (GPIO40 was observed low as an input);
- the firmware may never have been uploaded under OpenWrt;
- the FON block may be clock-gated until a channel is opened;
- the probe may be on the wrong net or too heavily loaded.

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
2. FSC period and jitter.
3. BCLK frequency and edges per slot.
4. A ≥ 10 s capture with raw samples.
5. Whether the same point shows clocks under FRITZ!OS.

With FSC/BCLK confirmed, C4 (active TDM) becomes meaningful; without them,
no driver change can be validated.
