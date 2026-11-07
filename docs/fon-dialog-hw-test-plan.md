# SC14448: offline plan for a hardware check (nothing executed)

Status: **plan only.**  No step below has been run for this document.  Every
step is passive unless it is explicitly marked otherwise, and no step may be
started without a separate approval.

The plan answers one question: *is the SC14448 running a PCM/TDM interface,
and does it execute the `0x25F90` sequence?*  It is written so that the
cheapest observation that can falsify the hypotheses comes first.

---

## 1. Preconditions to establish before touching anything

| # | Check | Why | How it is done without writes |
|---|---|---|---|
| 1 | Is GPIO40 holding the chip in reset? | if reset is asserted nothing else matters | read the SoC pin state and the net from the schematic; the pin was already observed as an input |
| 2 | Is the SC14448 powered? | an unpowered chip answers nothing | measure the supply rails |
| 3 | Is the chip's oscillator running? | clocks come from the chip in the master role | probe the crystal/clock output |

## 2. Passive observation of the link

| # | Signal | What it shows |
|---|---|---|
| 4 | FSC / frame sync (8 kHz) | a frame sync proves the interface is clocked, not that data flows |
| 5 | BCLK (≈1.025 MHz for 8×16 bits) | together with FSC it proves the bit/frame structure |
| 6 | DI (chip → SoC) and DO (SoC → chip) | any activity at all on DO proves the SoC side transmits; activity on DI proves the chip answers |

A logic analyser is required; a GPIO sampler cannot resolve 8 kHz or
1 MHz (this was established earlier and is documented in
`fon-known-facts.md`).

**Distinguishing "clocked" from "transferring data":** FSC and BCLK exist
without data.  Data requires looking at the actual bit stream inside each
slot: a slot that carries a constant (all zeros or all ones) over many
frames is idle, a slot whose payload changes with the line state (hook
on/off) is carrying control.

## 3. Detecting the poll loop of `0x25F90`

| # | Observation | Interpretation |
|---|---|---|
| 7 | Does anything change on `0x000F6002` after `0x80` is written to `0x000F6006`? | if it never changes, the firmware would spin forever at `0x25FAE`; if it changes to 1, the pulse and the poll are a handshake |
| 8 | Does the pattern in the `0x01000000` area stay constant? | a constant pattern means nothing reads it; a changing one means a consumer exists |

Both observations require reading the chip's memory or bus, i.e. a debug
access (JTAG or a loaded monitor).  That is **not** passive and needs its
own approval.

## 4. Stopping an experiment safely

* Cut power or assert reset through the existing safe path; never leave the
  chip in an unknown state with the SoC still driving DO.
* Record the state of every register that was observed *before* the stop,
  so a follow-up can compare.
* The FON driver in this repository must not be modified for the experiment;
  use a separate tool.

## 5. What has to be learnt before an active FON test is allowed

1. whether the chip acknowledges `0x80` at all (step 7);
2. whether the SoC's TDM master is really the clock master, or the chip is;
3. whether the slot-5 control word ever reaches the chip (DO activity);
4. whether the chip answers (DI activity).

Without (1) and (3) an active FON test would only repeat an unverified
assumption.

## 6. What result confirms or refutes the PCM hypothesis

| Result | Meaning |
|---|---|
| FSC + BCLK present **and** `0x000F6002` goes to 1 after the `0x80` pulse | the register pair and the pulse belong to a clocked interface the firmware starts — the PCM hypothesis is supported |
| FSC + BCLK present, `0x000F6002` never changes | the interface is clocked but the sequence is not completing — the register meaning is different from H1 |
| no FSC/BCLK, `0x000F6002` stays 0 | the block is not clocked at all; either the chip is not configured or not running the sequence |
| DO carries the slot-5 word but DI stays constant | the chip is not answering; the control word is not being processed |

## 7. Order of work

1. steps 1–3 (no writes, no firmware);
2. steps 4–6 with a logic analyser;
3. only then step 7, with debug access explicitly approved;
4. an active FON test last, and only if 1–3 gave a positive answer.
