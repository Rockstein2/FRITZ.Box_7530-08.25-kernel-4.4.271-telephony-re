# E5-F — standalone OpenWrt readiness inventory

> **Status: historical analysis; current summary is `../sc14448-e5-summary.md`.**
> Static, offline. Report: `tools/reports/cr16-e5-readiness.json`.
> E5 builds no driver code; this is an evidence inventory only.

| Component | OEM sequence | Register values | HW deps | Offline implementable | Runtime confirm |
|---|---|---|---|---|---|
| SC14448 reset/boot | PARTIALLY (bootloader handshake separate) | NO | NO | LIMITED | YES |
| firmware loading | PARTIALLY (image loads at fixed addresses incl. the `0x17300` DSP block) | NO | NO | LIMITED | YES |
| clock initialization | PROVEN (PLL `0x0800→0x0852→0x085A`, CODEC/PER/DSP dividers, CLK_AMBA) | PROVEN | SC14480_ANALOGY | YES | YES |
| PCM+ configuration | PROVEN (master `0x43` / slave `0x45`, 8 kHz frame, PCM_CLK select) | PROVEN | SC14480_ANALOGY | PARTIALLY | YES |
| DSP initialization | PROVEN (powerdown → program select `0x7980` → enable) | PROVEN | SC14480_ANALOGY | YES | YES |
| CODEC initialization | PROVEN (VREF→MIC→LSR→ADDA powerup order) | PROVEN (bit sequences) | SC14480_ANALOGY | YES | YES |
| audio routing | UNRESOLVED (inside DSP microcode) | NO | NO | NO | YES |
| analog line control | NOT_REACHED (no proved command path, E4.2) | NO | NO | NO | YES |

## Assessment

The strongest E5 result for a standalone driver: the OEM firmware carries
**candidate** DSP/CODEC/PCM bring-up register sequences — clock
dividers, CODEC analog order, PCM master/slave modes and the DSP start
address are all instruction-proven with concrete values, in both images.
A plausible model is therefore the one the task proposed: keep the OEM
firmware as a **closed DSP/CODEC engine** and drive it from Linux,
instead of reimplementing the analog bring-up.

That model is **not proven and cannot be built on yet** (E5.1 audit):

1. every register identity is an SC14480 analogy — the SC14448 map is
   unconfirmed;
2. the `0x17300` block is only a **candidate** DSP program
   (`DSP_PROGRAM_CANDIDATE_REFERENCED_BY_PC_START`); under the SC14480
   Table 63 its CR16 range is a *Reserved* microcode region, and whether
   the DSP executes it at all is unproven;
3. audio timing is configured for DIP (`<A_NORM>`) synchronisation of
   the main counter — whether the DIP must be radio-active is unknown,
   and other DSP start sources are not excluded;
4. no command path to any analog line function is proved (E4.2), so FON
   control stays out of reach regardless of the audio engine;
5. the Linux-side TDM geometry (8×16-bit slots, 1.024 MHz) does not
   match the firmware-side PCM geometry (4 channels, 1.152/2.304 MHz)
   — the interconnection itself is an open question (Q46/Q55/Q75).

## What must exist before a safe audio test

* an SC14448 system-controller/memory-map document (or equivalent
  evidence) confirming the DSP window, the DSP-PC-to-flash mapping and
  the PCM pins;
* a producer-backed proof of the DIP start / `<A_NORM>` issue or a
  runtime observation of the main counter;
* a decision on the PCM interface mismatch (IPQ4019 ↔ SC14448).

No register-write reconstruction, however complete, removes the
RUNTIME_VERIFICATION_REQUIRED status of the audio path (K1/K2 NO-GO).
