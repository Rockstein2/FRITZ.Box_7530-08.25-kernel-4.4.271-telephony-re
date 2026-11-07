# Stage C1 — ADSS MMIO read (active, not authorised)

> **Status: NO-GO until the gates below are closed.**
> This runbook describes an operation that writes to clock and reset
> registers and reads an unproven MMIO window.  It must not be executed
> without explicit, separate approval and a physical power-cycle path.

Stage C0 is passive.  Stage C1 is the first stage that **changes hardware
state**: it enables a clock, releases a block reset and performs `readl()` on
the ADSS block.

---

## 1. Question C1 answers

Can the ADSS register block be read safely from Linux, and what are the
values of:

```text
ADSS_GLB_AUDIO_MODE     0x07700030
ADSS_GLB_TDM_CTRL       0x0770001c
ADSS_GLB_CLK_I2S_CTRL   0x07700018
ADSS_GLB_I2S_RST        0x07700014
STEREO0_CONFIG          0x07708000
STEREO3_CONFIG          0x0770c000
```

Nothing else.  C1 does not configure TDM, does not touch DMA, does not talk
to the SC14448 and does not enable any analog path.

---

## 2. Gates that must be closed first

| # | Gate | How it is closed | Status |
|---|---|---|---|
| G1 | C0 has run on the target image and its summary is archived | `bench/collect-stage-c0.sh` | open |
| G2 | The FON DT node has explicit `clocks = <&gcc GCC_AUDIO_AHB_CLK>` and `resets = <&gcc GCC_AUDIO_BCR>` | DT change + rebuild | **done 2026-11-07**: patch 900 updated, image `4c3bdfd1...` built and verified, not booted |
| G3 | No other driver owns `0x07700000` or `GCC_AUDIO_BCR` | C0 `adss-ranges.txt`, `clk_summary` | open |
| G4 | The passive TDM measurement has been taken (§ of `fon-tdm-passive-test.md`) | scope/logic analyser | **not done** |
| G5 | A physical power-cycle path is available and tested | operator | open |
| G6 | The exact module under test is rebuilt in the kernel tree and hashed | build record | open |

G2 is now closed in the DT and in a built image.  The links are descriptions
only; a probe-only load must not acquire them.  Booting the new image and
confirming that `clock_refs=0` / `reset_refs=0` still hold is the check that
keeps Stage B valid.

G4 is not strictly required for the MMIO read, but it is what tells us
afterwards whether the read produced a *correct* state or a plausible
garbage value.

---

## 3. Proposed C1 module behaviour

A separate module parameter set on the **existing** probe-only driver, not a
new driver:

```text
c1_mmio=1        enable the C1 path (default 0)
```

Probe with `c1_mmio=0` must behave exactly like today's Stage B.

With `c1_mmio=1` the module performs, in this order:

1. `devm_clk_get()` for `GCC_AUDIO_AHB_CLK`; abort if missing;
2. `clk_prepare_enable()`; log the return code and the resulting
   `clk_summary` enable count;
3. `devm_reset_control_get()` for `GCC_AUDIO_BCR`; abort if missing;
4. `reset_control_assert()`, `usleep_range(20000, 24000)`,
   `reset_control_deassert()`;
5. `devm_ioremap()` of resource 0 only (0x34 bytes);
6. six `readl()` calls, logged one per line;
7. `clk_disable_unprepare()`;
8. leave the block asserted-or-not exactly as found (record the initial
   state first; there is no API to read it, so record it as unknown).

Each step logs before and after, so a hang is localised by the last line on
the console.

---

## 4. Rollback

| Failure | Action |
|---|---|
| `clk_prepare_enable` fails | stop, nothing to undo |
| `reset_control_get` fails | `clk_disable_unprepare`, stop |
| synchronous abort on `readl` | kernel oops, module not unloaded; power cycle |
| hang on `readl` | watchdog (b017000) resets the board; power cycle |
| any value looks wrong | `rmmod`, power cycle, keep the log |

There is **no** safe in-place recovery from a bus hang.  The physical
power-cycle path in G5 is the rollback.

---

## 5. Why C1 is not merged into Stage B

Stage B must stay a known-good, side-effect-free loader that can be run any
number of times.  C1 changes state and can crash the board.  Keeping them
behind different parameters means a failed C1 run never invalidates the
Stage B evidence.

---

## 6. Stop conditions

- any kernel `WARNING`, `BUG`, `Oops`, abort or panic;
- more than 3 identical `readl` values, which would suggest a stuck bus;
- `clk_summary` not showing the audio AHB clock enabled after step 2;
- the board stops responding to the console;
- the SC14448 gets warm.

Power off.  Do not retry without a new decision.

---

## 7. Exit criteria

C1 is successful when:

- the six registers were read at least once;
- the values are stable across two runs;
- `/proc/iomem` shows the ADSS range claimed *by our driver* while loaded and
  free again after `rmmod`;
- `clk_summary` returns to enable count 0 after unload.
