# SC14448: offline plan for a hardware check (nothing executed)

> **Status: operational document.**
> This is a runbook, not an evidence record.  Hardware facts are maintained in
> `../fon-known-facts.md`; unresolved items in `../fon-open-questions.md`.

Status: **plan only.**  No step below has been run for this document.  Every
step is passive unless it is explicitly marked otherwise, and no step may be
started without a separate approval.

The plan answers one question: *is the SC14448 running a PCM/TDM interface,
and does it execute the `0x25F90` sequence?*  It is written so that the
cheapest observation that can falsify the hypotheses comes first.

---

## 1. What an observation can and cannot show

This section exists because earlier revisions of this file drew causal
conclusions they could not support.

| Observation | What it establishes | What it does **not** establish |
|---|---|---|
| an unchanged pattern in the `0x01000000` area | the bytes did not change during the observation | that nothing reads the area: a read does not modify memory |
| FSC/BCLK present | the interface is being clocked | which block, register or code path caused the clocking |
| `0x000F6002` changing, or not changing | the value of one register at the observed moments | which operation, if any, caused the change |
| FSC/BCLK present **and** `0x000F6002` changing | two facts observed at the same time | that the sequence under study caused either one |

Correlation is not causation.  Establishing a cause requires an independent
variable that is changed on purpose (for example, skipping the write and
observing that the effect disappears) and that is an **active** experiment,
which this plan does not authorise.

Equally, a negative observation is not a refutation: if `0x000F6002` never
becomes 1, the loop at `0x25FAE` cannot exit normally, but that says nothing
about which block the surrounding code belongs to.

## 2. Preconditions to establish before touching anything

| # | Check | Why | How it is done without writes |
|---|---|---|---|
| 1 | Is GPIO40 holding the chip in reset? | if reset is asserted nothing else matters | read the SoC pin state and the net from the schematic; the pin was already observed as an input |
| 2 | Is the SC14448 powered? | an unpowered chip answers nothing | measure the supply rails |
| 3 | Is the chip's oscillator running? | clocks may come from the chip in the master role | probe the crystal/clock output |

## 3. Passive observation of the link

| # | Signal | What it shows |
|---|---|---|
| 4 | FSC / frame sync (8 kHz) | a frame sync proves the interface is clocked, not that data flows |
| 5 | BCLK (≈1.025 MHz for 8×16 bits) | together with FSC it proves the bit/frame structure |
| 6 | DI (chip → SoC) and DO (SoC → chip) | any activity on DO proves the SoC side transmits; activity on DI proves the chip answers |

A logic analyser is required; a GPIO sampler cannot resolve 8 kHz or 1 MHz
(this was established earlier and is documented in `../fon-known-facts.md`).

**Distinguishing "clocked" from "transferring data":** FSC and BCLK exist
without data.  Data requires looking at the bit stream inside each slot: a
slot that carries a constant over many frames is idle, a slot whose payload
changes with the line state (hook on/off) is carrying control.

## 4. Observing the registers of the sequence

| # | Observation | Requires | Interpretation limits |
|---|---|---|---|
| 7 | Read `0x000F6002` repeatedly while the firmware runs the `0x25F90` path and note whether it ever reads 1 | debug access | a change shows the value changed; it does not show what caused it.  No change means the loop cannot exit normally, not that the block is unrelated to PCM |
| 8 | Read the `0x01000000` area over time | debug access | an unchanged area does **not** show that nobody reads it |

Both observations need to read the chip's memory or bus (JTAG or a loaded
monitor).  That is **not** passive and needs its own approval.  No register
of the sequence is written by these steps.

## 5. Stopping an experiment safely

* Cut power or assert reset through the existing safe path; never leave the
  chip in an unknown state with the SoC still driving DO.
* Record the state of every register that was observed *before* the stop,
  so a follow-up can compare.
* The FON driver in this repository must not be modified for the experiment;
  use a separate tool.

## 6. What has to be learnt before an active FON test is allowed

1. whether the chip's `0x000F6002` ever reads 1 on this path (step 7) — a
   precondition for the sequence to complete at all;
2. whether the SoC's TDM master is really the clock master, or the chip is;
3. whether the slot-5 control word ever reaches the chip (DO activity);
4. whether the chip answers (DI activity).

Points 1 and 3 are necessary but not sufficient: neither shows causality.

## 7. Readings and what they do not decide

| Reading | Honest interpretation |
|---|---|
| FSC + BCLK present | the interface is clocked by *something* |
| `0x000F6002` observed as 1 | the value was 1 at that moment |
| both together | a correlation between two observations; not yet a link |
| FSC/BCLK absent | no frame timing; the interface is not clocked on this board/state |
| `0x000F6002` never observed as 1 | the `0x25FAE` loop cannot exit; the block may still be PCM |
| DO carries the slot-5 word but DI stays constant | the chip is not answering on DI |

None of these rows alone confirms or refutes the PCM/TDM hypothesis.  A causal
claim needs a controlled difference (active), which requires separate
approval.

## 8. Order of work

1. steps 1–3 (no writes, no firmware);
2. steps 4–6 with a logic analyser;
3. only then step 7, with debug access explicitly approved;
4. an active FON test last, and only if 1–3 gave a consistent picture.

Any debug access, reset manipulation or firmware load requires separate
permission.
