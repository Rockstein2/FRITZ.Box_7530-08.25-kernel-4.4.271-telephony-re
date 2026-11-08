# Stage D0.6 runbook — read-only diagnostics under OpenWrt

> **Status: plan only.  Nothing here has been executed.**
> Every item is read-only.  No GPIO write, no TLMM write, no reset, no
> firmware upload.

The goal is to confirm, from the running OpenWrt system, which of the links in
`../fon-d06-summary.md` is already satisfied — **before**
any active step is proposed.

---

## 0. Rules

1. Nothing is written.  If a check would need a write, it is not in this list.
2. `devmem` on a computed TLMM address is **not** given as a ready command.
   The addresses in `../history/fon-d06-pcm-pinmux.md` are for verification first.
3. A missing signal is not a diagnosis (§5).

## 1. GPIO40 state (the reset line)

| # | Check | Question it answers | How |
|---|---|---|---|
| 1 | `cat /sys/kernel/debug/gpio` | is GPIO40 claimed? input or output? | `debugfs` |
| 2 | the same file, GPIO40 level | is it 0 (asserted) now? | same |
| 3 | `cat /sys/kernel/debug/pinctrl/*/pinmux-pins` | which function owns GPIO40 | `debugfs` |
| 4 | `grep -i gpio /proc/interrupts` | is any GPIO IRQ on 40 registered | procfs |

Expected from Stage A: unclaimed, input, level 0.  Confirming it again after
a fresh boot tells us whether something changed.

## 2. PCM candidate pins (GPIO20–27)

| # | Check | Question it answers |
|---|---|---|
| 5 | `pinmux-pins` for GPIO20–27 | are they muxed to anything, and claimed by whom |
| 6 | `debugfs/gpio` level for each | current static level |
| 7 | `debugfs/clk/*` for `gcc_audio*` | is the audio clock enabled at all |
| 8 | `/proc/iomem` for `7700000`-`77fffff` | does any driver own ADSS |
| 9 | `ls /sys/bus/platform/devices/` for audio/mbox nodes | are the DT nodes bound |

Item 5 is the one that decides whether Linux owns the pins: if they show
`gpio` and are unclaimed, no Linux consumer is driving them. This does **not**
read back the hardware `FUNC_SEL`, so it neither proves nor disproves the
AVM/SC14448 mux state. AVM's own path uses a GPIO-input request whose side
effects are not recovered (`../history/fon-d06-pcm-pinmux.md` §1, Q81).

## 3. Clocks and reset controllers

| # | Check | Question it answers |
|---|---|---|
| 10 | `debugfs/clk_summary` for `audio_*` | enable count and rate |
| 11 | `debugfs/reset` if present | is the audio block held in reset |

## 4. Kernel messages

| # | Check | Question it answers |
|---|---|---|
| 12 | `dmesg \| grep -iE 'dect\|piglet\|pcmlink\|tdm\|adss'` | any DECT/PCM activity |
| 13 | `dmesg \| grep -i 78af000` | is `ttyMSM0` the only user of that UART |

## 5. Interpretation, before any conclusion

Absence of a result must not be read as a fault:

- GPIO40 at 0 and unclaimed is **expected** under OpenWrt, because nothing
  performs the reset (`../history/fon-d06-dect-reset-path.md`);
- no `audio_*` clock is **expected**, because no driver enables ADSS;
- no PCM clocks is **expected** if firmware was never uploaded.

Each of these is a *link not yet crossed*, not a broken part.

## 6. What this plan deliberately does not do

| Not done | Why |
|---|---|
| write TLMM CFG for GPIO20–27 | unproven FUNC_SEL; could break console/interrupts |
| drive GPIO40 | active step, separate approval |
| upload firmware | separate stage |
| use `devmem` on a raw address | addresses verified only for stride; no side-effect review |
| start DMA/TDM | `dma_start` returns `-EOPNOTSUPP` |

## 7. If a software edge counter is later wanted

Stage C0 established that sysfs sampling is far too slow for 8 kHz.  A real
check would need a kernel-side counter on a claimed GPIO input — that is a
**code change plus an active claim**, and belongs to a separate, explicitly
approved stage.  This runbook only collects the passive state.
