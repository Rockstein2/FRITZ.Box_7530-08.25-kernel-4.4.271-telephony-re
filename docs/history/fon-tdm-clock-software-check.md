# Software TDM clock check (recovered from `pcmlink.ko`)

> **Status: reverse-engineering result plus a feasibility analysis.**
> The algorithm comes from the disassembly of `ipq40xxtdm_checkhw` in
> `reports/pcmlink.annotated.txt`.  Nothing here was executed on hardware.

`pcmlink.ko` does not need a scope either: it polls the TLMM input register
of the FSC and DCL pins and counts edges against the arch timer.  This
document recovers exactly how, and asks whether we can do the same on
Linux 6.12 **without changing the pinmux**.

---

## 1. The algorithm, instruction by instruction

Function: `ipq40xxtdm_checkhw`, `0xa3b4..0xa7f0`.

### 1.1 Look up the pins

```text
0xa3d8..0xa408  scan avm_current_hw_config for "gpio_avm_pcmlink_fsc",
                take entry value (GPIO number) into r5
0xa438..0xa464  scan again for "gpio_avm_pcmlink_dcl", GPIO number -> r6
0xa490..0xa49c  reject if the entry's function field is 0xa or 0xb
0xa4a0..0xa4b8  dakota_gpio_get_membase(fsc), dakota_gpio_get_membase(dcl)
```

`dakota_gpio_get_membase` returns the TLMM base for that pin; the code
checks the result for NULL and prints `error:no membase exist` otherwise.

### 1.2 Sample window

```text
0xa500  ipq40xx_get_cyclefreq()          -> cycles per second
0xa504  r3 = 0x186a0                     -> 100000
0xa50c  umull / umlal chain              -> window = cyclefreq * 100000 / 2^18
0xa530  lsr sl, r2, #18                  -> sl = window in cycles
```

`0x186a0 = 100000`, shifted by 18 bits: the compare window is
`cyclefreq * 100000 / 262144`, i.e. roughly **0.38 s** of arch-timer cycles
(a deliberately generous window, since it is then used as a timeout).

### 1.3 Read the input bit

```text
0xa4ec  dakota_gpio_ctrl(fsc, 0, 0)      -> configure as plain input
0xa4fc  dakota_gpio_ctrl(dcl, 0, 0)
0xa5cc  ldr r3, [r8, #4]                 -> TLMM base + 0x4
0xa5d0  and r3, r3, #1                   -> bit 0 = pin level
0xa614  ldr r3, [r7, #4]
0xa618  and r3, r3, #1
```

`+0x4` is the `io_reg` of GPIO *n*: `pinctrl-ipq4019.c` defines
`io_reg = 0x4 + 0x1000 * id` (line 242) and `in_bit = 0` (line 251).  So the
code reads the **raw input level** of the pad, nothing else.

The base returned by `dakota_gpio_get_membase` is therefore
`0x01000000 + 0x1000 * n` for pin `n`.

### 1.4 Count edges

```text
0xa5bc  r4 = 0 (FSC edges), ip = 0
0xa5c4  r2 = start cycle count
0xa5d4  if (ip != level) r4++          ; edge on change
0xa5dc  while (cycles - start <= window)
0xa5fc  compare 0xa5fc: first loop exits when the window elapsed
0xa610..0xa63c  second loop over DCL with r8 as the counter
```

The edge counter is incremented on **every change** of the sampled bit, so
one full period counts as two edges.

### 1.5 Report

```text
0xa6ec  r2 = r4 * 10 ; lsr #1   -> FSC Hz  (10 * edges / 2 = 5 * edges)
0xa6f8  r1 = r8 * 10 ; lsr #1   -> DCL Hz
0xa6f4  printk("[pcmlink]TDM: FS: %u Hz CLK: %u Hz")
0xa708  if (fsc_edges <= 0x63) failure bit 0
0xa714  if (dcl_edges <= 0x63) failure bit 1
```

So the printed frequency is `5 * edge_count` for the fixed window, and the
threshold is "at least 100 edges", i.e. at least 500 Hz as printed.

Measured on FRITZ!OS: `FS: 8000 Hz CLK: 1025720 Hz`, which matches the FON
geometry (8 kHz frames, ~1.0257 MHz bit clock).

---

## 2. Can we do this on OpenWrt 6.12?

Yes for the **reading** part, with two important conditions.

### 2.1 The pinmux question

`Check_TDMInterface` calls `dakota_gpio_ctrl(pin, 0, 0)` first, which requests
a plain GPIO **input**; the function's side effects are not recovered (Q81).
Our board DTS leaves GPIO20-27 unclaimed, and Stage C0 reported
`(MUX UNCLAIMED)`.  That is a Linux-ownership report, not a readback of the
hardware `FUNC_SEL`, so the actual peripheral mux remains **UNKNOWN**.

Two different questions are hidden here:

1. **Can Linux read the pad level?**  Yes — the TLMM input register reflects
   the pad regardless of the mux setting, and Linux already reads that
   register in `gpio_get_value()`.
2. **Does the pad carry the TDM signal?**  That depends on the board wiring
   and on whether the ADSS/pin function drives it.  If the SC14448 drives
   FSC/DCL towards the SoC, the pads see them regardless of our mux choice,
   because the signal arrives from outside.

So a **pure read** of `gpio_get_value(22)` / `gpio_get_value(21)` (or the
PINMUX3 pair 26/25) is a legitimate passive measurement: it touches no
muxing, no direction register, no interrupt configuration.

**Residual risk:** if the pins are muxed to a peripheral that also drives
them, reading is still harmless, but a value of 0/1 could be an idle level
rather than a clock.  The edge count distinguishes that.

### 2.2 What must NOT be done

| Action | Why not |
|---|---|
| `gpio_request` + `gpio_direction_input` | harmless but reserves the pin; not needed to read |
| any `pinmux` write | that is the active step we are avoiding |
| enabling the pin interrupt | changes interrupt configuration |
| `pinctrl_select_state("audio_slave")` | no such state exists in our DTS |

The safe form is `gpiod_get_optional()` plus `gpiod_get_value()`, or reading
`/sys/kernel/debug/gpio`-style state, without claiming direction.

### 2.3 Which pair to read

The pair is **not known** until Q31 is answered.  A passive test should read
**all five candidate pins** (20,21,22,24,25,26) and report which of them
toggle.  That answers the pinmux-group question at the same time, without
writing anything.

---

## 3. Proposed passive stage (C0+)

Not to be executed in this iteration.  Sketch:

```text
for each pin in {20,21,22,24,25,26}:
    obtain the GPIO descriptor without changing direction
    count level changes over ~200 ms using ktime_get()
    report Hz = edges / 2 / seconds
```

Expected outcomes:

| Observation | Meaning |
|---|---|
| no pin toggles | SC14448 is not driving anything (no firmware, or held in reset) |
| 26/25 toggle at 8 kHz / 1.0257 MHz | PINMUX3 group is the live one |
| 22/21 toggle | PINMUX2 group is live |
| all toggle at slow rates | floating pins, not TDM |

This is the cheapest possible answer to Q27 and Q31 and needs no scope.

---

## 4. Relation to the piglet check

`Piglet_noemif.ko` has `Check_TDMInterface()` (`0x3f0c`) doing the same kind
of sampling, and it is skipped when `piglet_hostclkmaster` is set.  Since
`pcmlink` owns the actual audio path and its check is the one that prints the
values we already have from the OEM log, `pcmlink` is the better reference.

---

## 5. Confidence

| Claim | Confidence | Basis |
|---|---|---|
| sampling window formula | high | exact constant `0x186a0` and shift 18 |
| register `base+4`, bit 0 | high | `io_reg`/`in_bit` in `pinctrl-ipq4019.c` |
| edge counting and `5 * edges` | high | multiply/`lsr#1` before `printk` |
| threshold of 100 edges | high | `cmp #0x63` on both counters |
| passive read is safe | medium | no API call changes state, but the pads' electrical role on HW236 is unverified |
