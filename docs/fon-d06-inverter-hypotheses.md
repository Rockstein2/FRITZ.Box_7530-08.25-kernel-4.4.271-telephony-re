# D0.6-C — what could the 74LVC1G04 be doing?

> **Status: hypotheses only.**  The inverter is **not** identified as the
> reset line.  Nothing here is a measurement or a trace.

Measured by the owner **under OpenWrt only**: **VCC = 3.3 V, A = 3.3 V,
Y = 0 V**.
That is the correct truth table for an inverter (A high → Y low), so the part
was powered and functioning during that OpenWrt measurement. It says nothing
about the levels under a running FRITZ!OS.

---

## 0. What the software says, and what it cannot say

The recovered AVM code drives GPIO40 to logical **0** to assert reset and
**1** to release (`fon-d06-dect-reset-path.md`).  If the pad really is
active-high (as the board-table label suggests) that reading is
**contradictory**; either the label means something else, or an external
inversion sits between the pad and the chip.

An inverter near the chip is a plausible way to resolve that contradiction,
**but nothing in the binaries names it, and no trace has been followed.**
So the inverter stays a candidate, not an answer.

## 1. Hypothesis table

| Hypothesis | Why such a signal would exist | Required level (normal run) | Consistent with A=3.3 V / Y=0 V? | Evidence that would distinguish it |
|---|---|---|---|---|
| **H1 — RESET inversion** | SC14448 reset is active-low; SoC side may be active-high | reset released = chip pin HIGH; during run the pin is not asserted | **Yes** — Y = 0 could be the asserted state *if* reset is active-low and currently asserted, which fits the chip not running | toggle GPIO40 and watch both the pad and Y together |
| **H2 — boot-mode select** | many Dialog parts sample a strap at reset | depends on strap meaning | **Possible** — a static 0 is a valid strap | same toggle; a strap would only matter at reset edge |
| **H3 — regulator enable** | an LDO/DCDC enable, active depending on part | enabled = a fixed level for the whole run | **Possible**, but the owner already measured 1.8 V present on the rail, so the enable is satisfied regardless of Y | power sequencing capture |
| **H4 — clock / gate enable** | gate an external clock into the chip | enabled = fixed | **Weak** — FSC/BCLK are expected to come *from* the chip (master), so gating them externally is odd | presence/absence of clocks when Y changes |
| **H5 — level-shift helper for a 3.3 V–1.8 V boundary** | the part is 3.3 V powered, so it separates a 3.3 V control domain from a 1.8 V one | fixed after power-up | **Yes** — VCC 3.3 V with a low output looks like a level translation toward a 1.8 V side | measure the opposite side's domain; the 1.8 V rail exists |

### 1.1 Why H1 is not automatically the answer

The inverter sits near the SC14448, which is the usual reason people assume
"reset".  But:

- reset is driven by GPIO40, and no source ties that net to this part;
- an inverter used to translate 3.3 V → something else (H5) is just as common
  next to a mixed-voltage chip;
- the measured **A = 3.3 V, Y = 0 V** applies only to OpenWrt, where the DECT
  start-up sequence has not run. It cannot be extrapolated to working
  FRITZ!OS.

Therefore the measurement neither supports nor disproves H1. It is compatible
with the SC14448 being held in some inactive state under OpenWrt, but GPIO40
has not been electrically connected to A/Y and the SC14448 reset polarity is
unknown.

## 2. Status

| Claim | Status |
|---|---|
| The part is a working inverter | **CONFIRMED** (measurement) |
| It is powered from 3.3 V | **CONFIRMED** (measurement) |
| Its input or output is GPIO40 | **UNKNOWN** |
| Its output is the SC14448 reset | **UNKNOWN — not assumed** |
| Any hypothesis in §1 is true | **UNKNOWN** |

## 3. The single measurement that would settle it

One passive capture, **while already doing the reset work in a later,
separately-approved stage**:

- channel 1 on GPIO40 as a test pad (if reachable);
- channel 2 on the inverter's **A** and then **Y**;
- observe whether they toggle together with the reset pulse.

If A follows GPIO40 and Y is its inverse, H1 becomes testable.  If A is
constant while reset is exercised, the inverter is unrelated (H3/H5).
