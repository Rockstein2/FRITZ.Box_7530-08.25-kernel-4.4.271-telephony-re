# Why `gcc_audio_ahb_clk` warns on disable

> **Status: source analysis plus one hardware observation.**
> The WARNING itself was observed on hardware (Stage C1 and C2).  The cause
> below is derived from the mainline source in the build tree; no new
> hardware run was made for this document.

---

## 1. The observation

Both C1 and C2 ended with the same warning while dropping the clock:

```text
warn_slowpath_fmt from clk_branch_toggle
clk_core_disable from clk_disable
clk_disable from fon_c1_run
```

after which `clk_summary` reported `gcc_audio_ahb_clk` at enable count 0 and
hardware gate `N`, and the module unloaded cleanly.

---

## 2. Which driver path runs

`gcc_audio_ahb_clk` is defined in
`drivers/clk/qcom/gcc-ipq4019.c:520-534`:

```c
static struct clk_branch gcc_audio_ahb_clk = {
	.halt_reg = 0x1b010,
	.clkr = {
		.enable_reg = 0x1b010,
		.enable_mask = BIT(0),
		.hw.init = &(struct clk_init_data){
			.name = "gcc_audio_ahb_clk",
			.parent_hws = (const struct clk_hw *[]){
				&pcnoc_clk_src.clkr.hw },
			.flags = CLK_SET_RATE_PARENT,
			.num_parents = 1,
			.ops = &clk_branch2_ops,
		},
	},
};
```

Two facts decide everything below:

1. it uses **`clk_branch2_ops`**, not `clk_branch_ops`;
2. `halt_check` is **not set**, so it is `0`, which `clk-branch.h:31`
   defines as `BRANCH_HALT`.

The parent is `pcnoc_clk_src`, enabled by other consumers (`78af000.serial`
keeps it at count 6), so the parent is not the problem.

---

## 3. What the disable path actually checks

`clk_branch2_disable()` (`clk-branch.c:133`) calls
`clk_branch_toggle(hw, false, clk_branch2_check_halt)`.

`clk_branch_toggle` (`clk-branch.c:94`) clears the enable bit through
regmap, then calls `clk_branch_wait`.

`clk_branch2_check_halt` (`clk-branch.c:43-59`) for `enabling == false`:

```c
return (val & CBCR_CLK_OFF) == (invert ? 0 : CBCR_CLK_OFF);
```

with `invert == false` (halt_check has no `BRANCH_HALT_ENABLE` bit) and
`CBCR_CLK_OFF = BIT(31)` (`clk-branch.h:59`).

So the check is: **does bit 31 of `0x181b010` read back as 1?**

`clk_branch_wait` polls that check 200 times with 1 ms delay and then:

```c
WARN(1, "%s status stuck at 'o%s'", name, enabling ? "ff" : "n");
return -EBUSY;
```

`clk_branch2_disable()` is a `void` function, so the `-EBUSY` is dropped and
only the WARNING is visible.

---

## 4. Two candidate explanations, and how to tell them apart

### H1 — the branch is a "branch2" whose halt reporting differs

`clk_branch2_ops` was introduced for branches that report an NOC FSM status
in bits 30:28 alongside an inverted-style CLK_OFF in bit 31.  For the
*enable* direction the check accepts either `CLK_OFF == 0` **or**
`FSM_STATUS == ON`, which is more permissive than plain `clk_branch_ops`.

On the *disable* direction both ops require `CLK_OFF == 1`.  If the IPQ4019
audio branch never sets bit 31 when gated, the warning is expected on every
disable, independent of our code, and the gate still physically closes
because bit 0 was cleared.

### H2 — the gate really does not close

The bit 0 write is rejected or re-asserted by hardware (for example because
the block still has an active consumer inside the audio subsystem that is
not modelled as a Linux clock), so the clock keeps running with software
`enable_count == 0`.

### Which one is true — not yet settled

The evidence we have:

| Observation | Supports |
|---|---|
| `clk_summary` shows count 0 and hw gate `N` after the warning | H1 or H2 (count is software) |
| the second C1/C2 run behaved identically | both |
| the warning appeared **only** on disable, never on enable | both |
| a later `clk_enable` + `clk_disable` cycle did not produce a different result | not tested |
| nobody has read `0x181b010` back after the warning | **missing** |

The decisive experiment is one `readl()` of `0x181b010` immediately after
the disable, inside the same driver.  That is a two-line change to C1/C2 and
does not need a new stage, but it does need one more hardware run and is
therefore **not executed in this iteration**.

---

## 5. Is the warning dangerous?

Not by itself.  A stuck halt bit is a status-reporting problem; the enable
bit write still happened, and no bus abort occurred in two runs.

What *would* be dangerous is assuming the gate closed.  Treat "the clock is
off" as **unproven** until bit 31, bit 0 and the actual rate are read back.

---

## 6. What must NOT be done

| Temptation | Why not |
|---|---|
| add `CLK_IGNORE_UNUSED` | only affects unused-clock shutdown, not this path |
| drop `CLK_SET_RATE_PARENT` | unrelated to the halt poll |
| set `BRANCH_HALT_SKIP` on the branch | hides the signal without knowing whether it is real |
| mark it `CLK_IS_CRITICAL` | would pin the gate on forever |
| leave the clock enabled in the driver | leaves state behind on every unload |

None of these is applied.

---

## 7. AVM comparison

The AVM GPL tree shipped with this project contains only the audio
subsystem (`sound/soc/qcom/ipq/ipq-adss-avm.c`, `ipq-adss.h`) and the board
DTS.  It does **not** contain `drivers/clk/qcom/gcc-ipq4019.c`, so AVM's
variant of the audio branch descriptor and its halt flags cannot be
compared directly.  What the AVM driver does show (see
`fon-adss-avm-init-sequence.md`) is that it **never enables or disables the
audio AHB clock at all** — so AVM never exercises this code path.

That is itself informative: the gate may simply never have been toggled by
the vendor, which is why a halt-bit quirk could survive unnoticed.

---

## 8. Recommended next step

1. extend C1 (not C2) with a single post-disable `readl()` of `0x181b010`
   and log all 32 bits;
2. read the same before enable;
3. compare with `CLK_OFF` (`BIT(31)`) and `FSM_STATUS` (`GENMASK(30,28)`);
4. only then decide whether the gate is real, and only then consider a
   quirk.

This is a read of a GCC register, not of the ADSS window; it is safe with
the audio clock disabled and does not touch the audio block.

---

## 9. Summary

| Question | Answer |
|---|---|
| Why the WARNING? | `clk_branch2_check_halt` polls `BIT(31)` of `0x181b010`; it did not read 1 within 200 ms |
| Is it our code? | No. The check runs inside the clock framework for every consumer |
| Does the clock really stop? | **Unproven** — the enable bit is cleared and `enable_count` is 0, but the halt bit was never seen |
| Was AVM ever affected? | Unknown; AVM's driver never toggles this clock |
| Fix applied | None; adding a quirk without evidence is worse than the warning |
