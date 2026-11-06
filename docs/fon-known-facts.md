# FON: known facts (single source of truth)

Status: **confirmed evidence only.  Anything not listed here is either an open
question (`fon-open-questions.md`) or historical reasoning (the other
`docs/fon-*.md` files).**

Every row names its evidence class:

| Class | Meaning |
|---|---|
| **GPL** | read directly from the AVM `08.25` GPL tarball |
| **DT** | from the board device tree in this repository or in the GPL tree |
| **OEM** | observed in `history/wiki-fritzos-oem-bootlog-reference.txt` (FRITZ!OS, kernel **4.4.60**, build 2021-04-26) |
| **CODE** | implemented and offline-tested in `src/fon-driver/` |
| **OFFLINE** | verified on this workstation, no hardware |

**A row marked GPL/DT/OEM is not automatically true for our kernel.**  The OEM
log comes from 4.4.60, we run 6.12/4.4.271-OpenWrt.  Rows needing runtime
confirmation on our build are marked `(runtime)`.

---

## 1. Hardware identity

| Fact | Value | Evidence |
|---|---|---|
| SoC | Qualcomm IPQ4019, ARMv7 Cortex-A7 | DT |
| Telephony controller | Dialog SC14448 (DECT + analog FON) | GPL, OEM |
| Analog line | one FXS port (TAE/RJ11); not a second DECT path | GPL |
| SLIC logical interfaces | 1 | OEM (`Slics=1`) |
| DECT channels | 4 | OEM (`DECT=4`) |
| POTS/TE/NT | 0 | OEM (`Pots=0`) |

`Pots=0` is a PCMLINK **slot-allocation counter**, not a statement that the
analog FON is absent.  The analog line is driven by `isdn_fbox_fon5` over the
same TDM transport.

## 2. Register blocks (FON / ADSS)

| Block | Address | Size | Evidence |
|---|---|---|---|
| ADSS audio (`audio@7700000`) | `0x07700000` | `0x34` | GPL, DT |
| ADSS secondary (`0x7707000`) | `0x07707000` | `0x20` | GPL |
| PCM (`pcm@7704000`) | `0x07704000` | `0x2000` | GPL, DT |
| MBOX0 | `0x07708000` | `0x1000` | GPL, DT |
| MBOX1 | `0x0770a000` | `0x1000` | GPL |
| MBOX2 | `0x0770c000` | `0x1000` | GPL |
| MBOX3 | `0x0770e000` | `0x1000` | GPL, DT |
| MBOX4 (SPDIF) | `0x07706000` | `0x1000` | GPL |
| STEREO0 | `0x07709000` | `0x1000` | GPL, DT |
| STEREO1 | `0x0770b000` | `0x1000` | GPL |
| STEREO2 | `0x0770d000` | `0x1000` | GPL |
| STEREO3 | `0x0770f000` | `0x1000` | GPL, DT |

Our driver maps six of these (`adss`, `pcm`, `mbox_tx`, `mbox_rx`,
`stereo_tx`, `stereo_rx`) — `resource_mask = 0x3f`.

## 3. Interrupts

| Fact | Value | Evidence |
|---|---|---|
| mbox0 DT specifier | `GIC_SPI 156` | DT |
| mbox3 DT specifier | `GIC_SPI 159` | DT |
| GIC INTID arithmetic | `SPI n -> INTID n + 32` | GPL, OEM |
| mbox3 INTID | **191** | OEM (`mbox_dma_init: ... hwirq=191`) |
| mbox3 virq at that boot | 107 | OEM (runtime, not portable) |
| AVM interrupt type | **FIQ**, not IRQ | OEM (`avm_request_fiq_on`) |
| Our interrupt type | normal threaded IRQ | CODE |
| Trigger | `IRQ_TYPE_LEVEL_HIGH` in DT | DT |
| Actual trigger on our kernel | not yet read | `(runtime)` |

The FIQ/IRQ difference is deliberate.  It means AVM's handler latency cannot
be reproduced, but the INTID arithmetic is confirmed.

## 4. DMA and TDM framing

| Fact | Value | Evidence |
|---|---|---|
| Frame rate | 8000 frames/s | GPL, OEM |
| Physical slots per frame | 8 | GPL (`adss_glb_tdm_ctrl_ch_num(slots - 1)`, "only 8 tested") |
| Logical codec slots | 6 | OEM (`Codecslots=6`) |
| Slot width | 16 bit | GPL |
| Bytes per frame | 16 | GPL (`8 * 2`) |
| Bit clock formula | `slots * 8 * sizeof(short) * 8000` | GPL |
| Bit clock, master mode | 1.024 MHz | GPL |
| Bit clock, measured on FRITZ!OS | **1 025 720 Hz** | OEM |
| MCLK, master mode | `bclk * 4` = 4.096 MHz | GPL |
| TDM role | **ADSS is slave; SC14448 supplies BCLK/FSC** | GPL, OEM |
| Data delay | RX = 1, TX = 1 bit clock | GPL |
| DMA TX channel | 0 (MBOX0) | GPL, OEM |
| DMA RX channel | 7 (MBOX3) | GPL, OEM |
| Stereo TX port | 0 | GPL, OEM |
| Stereo RX port | 3 | GPL, OEM |
| Frames per DMA buffer | 32 (= 4 ms) | GPL |
| Buffer size | 512 bytes per ping-pong half | GPL |
| DMA descriptors | 16 | GPL |
| Descriptor size (IPQ4019) | 156 bytes, `L1_CACHE_ALIGN` = 192 | GPL |
| Driver slot count | `qcom,tdm-slots = <8>` matches GPL | DT, GPL |

**Measured vs formula:** 1 025 720 Hz is 0.17 % above 8x16x8k.  That is the
slave-mode clock produced by the SC14448, not by our PLL.  It is a **sanity
value, not a tuning target**.

## 5. GPIO (board HW236)

| Function | GPIO | Notes | Evidence |
|---|---|---|---|
| DECT reset (`gpio_avm_dect_reset`) | **40** | `AVM_DEF_HW_PARAM_GPIO_OUT_ACTIVE_HIGH` | GPL |
| DECT RD (`gpio_avm_dect_rd`) | 16 | | GPL |
| PCMLINK FSC | 22 (mux2) / 26 (mux3) | input, active low | GPL |
| PCMLINK DCL | 21 (mux2) / 25 (mux3) | input, active low | GPL |
| PCMLINK MCL | 20 (mux2) / 24 (mux3) | input, active low | GPL |
| PCMLINK DI | 23 (mux3) | input | GPL |
| PCMLINK DO | 27 (mux3) | output, active low | GPL |
| USB power enable | 49 | | GPL |
| LED power | 39 | active low | GPL, OEM |
| LED FON (`gpio_avm_led_fon`) | **35** | active low — **not** the reset line | GPL, OEM |
| LED WLAN | 34 | | OEM |
| LED connect | 45 | | OEM |
| Button WLAN | 42 | | OEM |
| Button connect | 41 | | OEM |
| Button DECT | 43 | | OEM |

**GPIO40 and GPIO35 are different signals.**  Any text that treats GPIO40 as
the FON LED is wrong.

`AVM_DEF_HW_PARAM_GPIO_OUT_ACTIVE_HIGH` is an AVM **software convention**.  It
does not prove the electrical level at the SC14448 reset pin.

## 6. Boot order on FRITZ!OS

| Time | Event | Evidence |
|---|---|---|
| 0.39 s | `msm_dectuart_probe` -> ttyMSM0 on `78af000` | OEM |
| 1.40 s | console enabled on ttyMSM0 | OEM |
| 11.9 s | `piglet.service` starts | OEM |
| 12.03 s | `dect_loader-bootmode` | OEM |
| 17.77 s | `dectfw_secondlevel_441.hex` upload OK | OEM |
| 19.98 s | `TDM: FS: 8000 Hz CLK: 1025720 Hz` | OEM |
| 20.12 s | `pcmlink` loaded | OEM |
| 20.33 s | `isdn_fbox_fon5` loaded | OEM |
| 20.39 s | `mbox_dma_init` success | OEM |
| 20.69 s | `Codecslots=6 ...` | OEM |

**The SC14448 is already running before any TDM client appears.**  A
probe-only test must not assume an unprogrammed chip.

## 7. Data path

| Fact | Value | Evidence |
|---|---|---|
| FON register transport | `TxDMA` / `PutRxDMA`, 16-bit word in TDM/MBOX **slot 5** | GPL |
| Hook detection | RX slot 5 status bit 3 -> `reg 0x44` bit 7 | GPL |
| Ring control | `reg 0x48` bits 5/6 -> ring command -> TX slot 5 | GPL |
| Line feed | `reg 0x48` writes + `build_slic_ctrl` | GPL (exact SC14448 bits unproven) |
| FON over UART | **disproved** — no UART imports in `pcmlink`, `isdn_fbox_fon5`, `avm_dect` | GPL |
| `pcmlink_ll_set_status` as FON transport | **disproved** — real link is `FPGALink` / QCA-ADSS | GPL |

## 8. Console UART

| Fact | Value | Evidence |
|---|---|---|
| Device | `serial@78af000`, 0x200 bytes | DT |
| GIC SPI | 107 | DT |
| Pins | GPIO16/17 | DT |
| Shared use | DECT loader and kernel console | OEM |
| FON driver use | **none** | CODE |

## 9. Our driver (offline state)

| Fact | Value | Evidence |
|---|---|---|
| Probe-only diagnostics | `stage=0x23`, `mode=probe-only`, `resource_mask=0x3f`, `diag_valid=0`, `dma_prepared=0`, `dma_started=0`, `irq_spi=156/159`, `irq_intid=188/191`, `irq=-1` | CODE, OFFLINE |
| Module build (SDK 25.12.6) | 73 980 bytes, sha256 `b867b8c5...ad870` | OFFLINE |
| Offline test suites | mock 40, TDM/DMA, dialog (incl. real firmware), bench 29, prepare-tree 13, prepare-image 10 | OFFLINE |
| checkpatch | 0 errors, 4 intentional warnings | OFFLINE |
| sparse | no diagnostics | OFFLINE |

## 10. What this document deliberately excludes

Everything that is a hypothesis, a plan, or reasoning about how we got here.
Those live in `fon-open-questions.md` (what is still unknown) and in the
historical documents, which are marked as such.
