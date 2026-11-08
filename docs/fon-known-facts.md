# FON: known facts (single source of truth)

Status: **confirmed evidence only. Anything not listed here is either an open
question (`fon-open-questions.md`) or historical reasoning under
`docs/history/`.**

Every row names its evidence class:

| Class | Meaning |
|---|---|
| **GPL** | read directly from the AVM `08.25` GPL tarball |
| **DT** | from the board device tree in this repository or in the GPL tree |
| **OEM-DTB** | from the compiled HW236 tree extracted from FRITZ!OS 08.25 `kernel.image` |
| **OEM** | observed in `history/wiki-fritzos-oem-bootlog-reference.txt` (FRITZ!OS, kernel **4.4.60**, build 2021-04-26) |
| **OEM-CAPTURE** | observed in `reference/oem-08.25-boot/` — OEM FRITZ!OS **08.25** on this board, captured 2026-11-08 |
| **DISASM** | recovered from a proprietary AVM binary; file/function/address must be cited |
| **CODE** | implemented and offline-tested in `src/fon-driver/` |
| **OFFLINE** | verified on this workstation, no hardware |
| **RUNTIME-RO** | observation through read-only interfaces: serial console, `/proc`, sysfs or debugfs; no module load and no intentional GPIO/MMIO writes. A debugfs read is not proof of zero hardware side effects |
| **HW-TEST** | controlled hardware execution: test-image boot, module load, clock/reset/MMIO writes, or a bench measurement that requires explicit authorisation |

**A row marked GPL/DT/OEM is not automatically true for our kernel.**  The OEM
log comes from 4.4.60, we run 6.12/4.4.271-OpenWrt.  Rows needing runtime
confirmation on our build are marked `(runtime)`.

The evidence class describes **where** a fact came from. The truth status
(`CONFIRMED` / `INFERRED` / `UNKNOWN` / `DISPROVED`) is separate: static
evidence is never promoted to hardware proof.

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

## 1a. Production router baseline (RckBox, 2026-11-07)

This workspace contains **one** FRITZ!Box 7530, hostname `RckBox`.  It is the
only unit available for the bench, so a RAM-only test would use it after
production service is moved to another router.  The NAND must stay untouched.

All rows below were read over `/dev/ttyUSB0` at 115200 8N1 and a root shell,
with read-only commands only.  No module was loaded and no flash write was
performed.

| Fact | Value | Evidence |
|---|---|---|
| Board | `AVM FRITZ!Box 7530`, compatible `avm,fritzbox-7530` | RUNTIME-RO |
| Firmware | OpenWrt 25.12.6 `r33311-981c978eff` (official release) | RUNTIME-RO |
| Kernel | 6.12.112, `#0 SMP Sat Oct 17 21:45:38 2026` | RUNTIME-RO |
| Kernel command line | ` coherent_pool=4M` only; **no `root=`** | RUNTIME-RO |
| Root filesystem | squashfs `/dev/ubiblock0_1`, read-only, mounted on `/rom` | RUNTIME-RO |
| Overlay | UBIFS `/dev/ubi0_4`, mounted on `/overlay` (71.5 MiB, 16.6 MiB used) | RUNTIME-RO |
| Console | `/dev/ttyUSB0`, 115200 8N1, root shell `root@RckBox:~#` | RUNTIME-RO |
| `sysupgrade` | `/sbin/sysupgrade` present | RUNTIME-RO |
| NAND health | 872 good PEBs, 0 bad, 0 corrupted, max erase counter 10 | RUNTIME-RO |
| Recovery partitions | `urlader0` / `urlader1` present (`mtd5`/`mtd6`) | RUNTIME-RO |

MTD layout (size / erasesize 128 KiB):

| MTD | Size | Name |
|---|---|---|
| mtd0 | 0x00080000 | SBL1 |
| mtd1 | 0x00080000 | MIBIB |
| mtd2 | 0x00080000 | QSEE |
| mtd3 | 0x00040000 | CDT |
| mtd4 | 0x00080000 | QSEE_B |
| mtd5 | 0x00040000 | urlader0 |
| mtd6 | 0x00040000 | urlader1 |
| mtd7 | 0x00840000 | nand-tffs |
| mtd8 | 0x00400000 | uboot0 |
| mtd9 | 0x00400000 | uboot1 |
| mtd10 | 0x06d00000 | ubi |

UBI volumes on `mtd10` (LEB 126 976 B, 872 PEBs, 20 reserved):

| ID | Name | Size | Use |
|---|---|---|---|
| 0 | `kernel` | 29 LEB (3 682 304 B) | bootloader loads the FIT kernel from here |
| 1 | `rootfs` | 43 LEB (5 459 968 B) | squashfs, exposed as `ubiblock0_1` + `/rom` |
| 2 | `avm_config` | 17 LEB (2 158 592 B) | AVM data, not used by OpenWrt |
| 3 | `avm_userdata` | 103 LEB (13 078 528 B) | AVM data, not used by OpenWrt |
| 4 | `rootfs_data` | 656 LEB (83 296 256 B) | UBIFS overlay (`/overlay`) |

The boot chain has no `root=` argument: OpenWrt preinit attaches UBI, creates
`ubiblock0_1`, and `mount_root` switches to the UBIFS overlay.  This is the
standard UBI boot flow, not a custom AVM one.

### Restore-image comparison

The installed kernel is byte-identical to the official 25.12.6 image:

| Item | SHA-256 |
|---|---|
| `kernel` volume, first 3 638 736 B | `278f42934b35cb41a2956c2344c554808de5b2011c8143fd403ebb8927252db6` |

The installed rootfs is **not** byte-identical to the official image.  It has
the same build time, same inode count and same file set size, but 132 bytes
more squashfs data:

| Item | Value |
|---|---|
| Installed squashfs `bytes_used` | 5 374 478 B |
| Official image squashfs `bytes_used` | 5 374 346 B |
| Both `mkfs_time` | 2026-10-17 23:45:38 |
| Both inode count | 1281 |
| Installed rootfs (volume, full) | `84b6c1a5a3b3b1a2f891f9a7aca1bde7462cfaa3fdb04795e6346e6493149492` |
| Installed rootfs first 5 374 976 B | `564c6af007371ab564436a73c4b52c8106de0ef04de50374535cdd9dbbcb007c` |

This is consistent with a locally built/ImageBuilder image derived from the
same release, not with a different release.  It is functionally the same
firmware, but reflashing the official image would not reproduce the current
rootfs byte for byte.  A byte-exact rootfs could only be preserved by reading
`/dev/ubi0_1` first; that dump was deliberately **not** taken because the
bench procedure never writes NAND.

Verified restore assets outside the repository:

| Asset | Hash / note |
|---|---|
| `../../restore/openwrt-25.12.6/openwrt-25.12.6-ipq40xx-generic-avm_fritzbox-7530-squashfs-sysupgrade.bin` | `011e020205fed455c79ee68ebb4d9ce43e6b05698bd99b05ebfc5c851f7ceb73` |
| `../../restore/openwrt-25.12.6/version.buildinfo` | `r33311-981c978eff` (matches the board) |
| `../../backups/RckBox-config-*.tar.gz` | configuration only; newest 2026-11-06 21:31 |



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

### 1c. SC14448 variant and codec count — unconfirmed

The board component list in the historical analysis shows a marking of the
form `SC14448-B96R101QNC`.  A public short datasheet for the **SC14448B**
family lists a very similar order code (suffix `X`), which suggests the 7530
may carry the **B** revision rather than the A revision.

Status: **not confirmed.**  No marking on our board has been read, and
order-code similarity alone is not identification.

Related claim under review: an older project note assumed two internal audio
codecs.  The public SC14448B material describes **one** 16-bit audio codec.
Until the datasheet for the exact variant or a die marking is read, the
correct statement is: **one codec is documented for SC14448B; a second one
is unproven.**

This matters for the FON because a second codec would imply an audio path
our driver does not model at all.

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
| Frames per DMA buffer | `fs_per_dma` is computed as `[r5] / [r5+8]` from the board config (`ipq40xxtdm_linkinit` `0x9ef0..0x9f28`), not a literal 32; the 7530 board values are in the closed `avm_get_hw_config_table` → **UNRESOLVED (Q76)**.  The GPL comment `4 ms == 32` describes the intent, not the passed number | GPL (doc comment), DISASM |
| Buffer size | 512 bytes per ping-pong half **only if** `fs_per_dma = 32` and `slots = 8` (`32 * 8 * 2`); 32 is the offline driver's constant, not an OEM-proven value | derived, UNRESOLVED (Q76) |
| DMA descriptors | 16 | GPL |
| Descriptor size (IPQ4019) | 156 bytes, `L1_CACHE_ALIGN` = 192 | GPL |
| Driver slot count | `qcom,tdm-slots = <8>` matches GPL | DT, GPL |

**Measured vs formula:** 1 025 720 Hz is 0.17 % above 8x16x8k.  That is the
slave-mode clock produced by the SC14448, not by our PLL.  It is a **sanity
value, not a tuning target**.

### 4b. Which audio node the FON uses (C3, 2026-11-08)

The 7530 DTB enables **two** QCA audio descriptions with **opposite**
channel pairs.  Only one is the FON path.

| Node | dma-tx | dma-rx | stereo-tx | stereo-rx | Role |
|---|---|---|---|---|---|
| `tdm@0` (`qca,ipq4019-tdm`) | 0 | 7 | **0** | **3** | **FON / pcmlink** |
| `pcm@7704000` (`qca,ipq4019-pcm`) | 6 | 1 | 3 | 0 | not the FON path |

Evidence: compiled HW236 DTB (`tdm@0` block, `pcm@7704000` block) and the OEM
runtime log `intf_tdm_probe: ena: dma-tx-channel=0 stereo-tx-port=0 / ena:
dma-rx-channel=7 stereo-rx-port=3` (`history/fon-oem-bootlog-crosscheck.md`).

**`stereo-tx-port`/`stereo-rx-port` select the hardware**, not
`dma-tx-channel`: `tdm_if_adss_dma_init()` passes `stereo_tx`/`stereo_rx` as
the `dma_id` and uses `mbox_data[stereo_tx].irq`
(`ipq-adss-avm.c:2208,2216`).  `dma-tx-channel` is read and logged only.

Consequence for our DTS: `mbox_tx=0x7708000`, `mbox_rx=0x770E000`,
`stereo_tx=0x7709000`, `stereo_rx=0x770F000` — **already correct**.

### 4d. TX frame word at offset 0x08 (D0.5, 2026-11-08)

`TxDMA` (`0x98ac..0x98c8`) writes:

```
movw r2, #0x5555
ldr  r3, [TDMPriv, #0x808]
cmp  r3, #0
movne r2, #0
strh r2, [frame + 0x08]
```

`+0x808` is set to 1 by `fpgadata_init` (`0x9434..0x944c`) only when
`(config & 0x1003) == 0x1001`, i.e. an FPGA is present.  Stock `pcmlink`
runs `abmode=1` (**no FPGA**) on the 7530, so `+0x808 == 0` and the TX frame
carries **0x5555** at offset 0x08.  `0x0000` is the FPGA-board branch.

Driver default is therefore `FON_TDM_HDR08_5555`; `tdm_hdr08_zero=1` selects
the other branch for experiments.

### 4c. Terminology: GPL vs proprietary disassembly

Some FON facts in this file are **not** from published GPL source.  They come
from disassembling proprietary AVM modules and are labelled accordingly:

| Fact | Source class |
|---|---|
| slot-5 control word at frame offset `0x0a` | **DISASM** (`pcmlink.ko`) |
| hook = RX status bit 3 → reg 0x44 bit 7 | **DISASM** (`pcmlink.ko`) |
| `build_slic_ctrl` bit layout | **DISASM** (`pcmlink.ko`) |
| MBOX/stereo/TDM channel selection | **GPL** (`ipq-adss-avm.c`) + DTB + OEM log |
| 8 slots × 16 bit, slave mode, delays | **GPL** (`ipq-adss-avm.c`) |

Do not describe a `DISASM` fact as "GPL".  Both are `CONFIRMED` on the Linux
side; neither proves the SC14448 side.

## 5. GPIO (board HW236)

| Function | GPIO | Notes | Evidence |
|---|---|---|---|
| DECT reset (`gpio_avm_dect_reset`) | **40** | source macro `AVM_DEF_HW_PARAM_GPIO_OUT_ACTIVE_HIGH`; compiled `param=<0x0b>` | GPL, OEM-DTB |
| DECT RD (`gpio_avm_dect_rd`) | 16 | OEM live readback: `func=1`, UART RX; the name does not create a second GPIO function (Q78 closed) | GPL, OEM-DTB, OEM-CAPTURE |
| PCMLINK FSC | 22 (mux2) / 26 (mux3) | input; compiled `function=<2>/<3>` | GPL, OEM-DTB |
| PCMLINK DCL | 21 (mux2) / 25 (mux3) | input; compiled `function=<2>/<3>` | GPL, OEM-DTB |
| PCMLINK MCL | 20 (mux2) / 24 (mux3) | input; compiled `function=<2>/<3>` | GPL, OEM-DTB |
| PCMLINK DI | 23 (mux3) | input; compiled `function=<3>` | GPL, OEM-DTB |
| PCMLINK DO | 27 (mux3) | output; compiled `function=<3>` | GPL, OEM-DTB |
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

### 5a. Passive pin observation under OpenWrt (2026-11-07)

All PCM candidate pins were read as GPIO inputs for two seconds each; the
pad direction was already `in`, so reading changed nothing.

| Pin | Level | Transitions in 2 s |
|---|---|---|
| GPIO20 (MCL, mux2) | 1 | 0 |
| GPIO21 (DCL, mux2) | 0 | 0 |
| GPIO22 (FSC, mux2) | 1 | 0 |
| GPIO23 (DI) | 1 | 0 |
| GPIO24 (MCL, mux3) | 1 | 0 |
| GPIO25 (DCL, mux3) | 0 | 0 |
| GPIO26 (FSC, mux3) | 1 | 0 |
| GPIO27 (DO) | 1 | 0 |

No transitions were observed on either pinmux group.

**This does not prove the clocks are absent.**  Each sample spawned a
separate process to read a sysfs file, so the effective sampling rate is at
most tens of kHz, and it reads through the GPIO subsystem rather than the
TLMM register.  A signal at 8 kHz or above can be completely invisible to
this method.  The measurement only rules out a slow, steady oscillation.

A kernel-side edge counter validated against a known signal is required
before anything can be said about FSC or BCLK.

Reset line:

| Pin | Direction | Level |
|---|---|---|
| GPIO40 (DECT reset) | `in` | **0** |

The AVM board table declares GPIO40 as `OUT_ACTIVE_HIGH`. Nothing in OpenWrt
drives it, the pad is an input, and it reads low. This does **not** establish
the physical level or asserted state at the SC14448 reset pin: the AVM GPIO
API transformation, electrical connection, and any inversion are unresolved
(Q13/Q15).

### 5b. D0.6 reset and PCMLINK pinmux reconstruction (2026-11-08)

| Fact | Evidence | Status |
|---|---|---|
| Compiled OEM DTB | offset `0x98d038`, 26,963 bytes, SHA256 `3083e2acedc800015fea5ee7e57fa6cc8da551e21ee792095cbd8a7224bb841f` | OEM-DTB |
| GPIO40 profile slot | `get_profile()` stores `gpio_avm_dect_reset` at `profile+0x28` (`Piglet_noemif.ko` `0x3844..0x385c`) | DISASM |
| Reset API assert state | `dakota_gpio_ctrl(gpio,0,1)` at `0xb44`, then `dakota_gpio_out_bit(gpio,0)` at `0xb54` | DISASM |
| UART-before-release order | `msm_dectuart_init()` at `0xb80`, then `dakota_gpio_out_bit(gpio,1)` at `0xb9c`; second branch `0xd10` then `0xd28` | DISASM |
| Physical reset polarity | API arguments 0/1 do not prove pad or SC14448-pin levels | **UNKNOWN** |
| PINMUX2/PINMUX3 values | compiled DTB contains `function=<2>` for GPIO20–22 and `<3>` for GPIO23–27 | OEM-DTB |
| Linux TLMM selector | `i2s_rx` index 2 for GPIO20–22; `i2s_rx/tx/td` index 3 for GPIO23–27; `mux_bit=2` gives field bits `0x08/0x0c` | GPL |
| PCMLINK applies pin config | `pcmlink.ko:ipq40xxtdm_linkinit()` calls `dakota_gpio_pinconfig(gpio, profile_field, 1)` at `0xa168` | DISASM |
| Piglet clock check | `Check_TDMInterface()` uses a measured 100 ms window and reports `frequency = 5 * edges`; it reads the TLMM input bit after `dakota_gpio_ctrl(gpio, 0, 0)`, has no explicit `dakota_gpio_pinconfig()` in this path, does not generate FSC/BCLK, and produces the `[piglet]TDM` boot line | DISASM |
| Piglet TDM window | `cyclefreq` magic `0x10624dd3`, `lsr #6`, `mul #100` -> cycles in 100 ms; FSC and DCL use sequential windows; threshold 100 edges | DISASM |
| pcmlink diagnostic check | `ipq40xxtdm_checkhw()` is a `cmd_general` diagnostic, not boot init; it uses a 64-bit fixed-point constant and a ~195 ms window, then the same `5 * edges` expression, so its printed value is ~1.95x high and is not the Piglet boot value | DISASM |
| C0+ userspace probe | `tools/fon-tlmm-clock-probe/` reads TLMM `GPIO_IO(n)` bit 0 through a read-only `/dev/mem` mapping; no MMIO writes, GPIO requests, pinctrl, clock or reset calls; checkpoints every 64 reads detect gaps; 52 synthetic checks | DISASM, GPL, OFFLINE |
| C0+-K kernel module | `kernel/fon_tlmm_probe.c` is idle after `insmod`; one debugfs write triggers one 20–50 ms measurement of GPIO21/22/25/26; maps one 4 KiB page; `readl` only; built offline against 6.12.112, not loaded | DISASM, GPL, OFFLINE |
| Stock OpenWrt `/dev/mem` | OpenWrt 25.12.6 build config has `# CONFIG_DEVMEM is not set`; the userspace probe therefore needs a reviewed `CONFIG_DEVMEM=y` test kernel, or the one-shot kernel module | OFFLINE |
| Piglet ctrl side effects | `dakota_gpio_ctrl()` may reconfigure the pad; its body is unavailable, so this is **not** a proven hardware read-only procedure | **UNKNOWN** |
| AVM API transformation | body of `dakota_gpio_pinconfig()` and physical effect of `dakota_gpio_out_bit()` are unavailable | **UNKNOWN** |
| OEM DTB selection | three HW236 DTBs are present in `kernel.image`: `0x98d038` (`subrevision=2`), `0x993990`/`0x99a2e8` (`subrevision=0`); FON-relevant properties are identical. The OEM runtime log reports `HWS(2)`, so this board is **subrevision 2** and the first blob matches it. Which blob the bootloader actually selects is still not observed (Q80) | OEM-DTB, OEM-CAPTURE / **selection UNKNOWN** |
| Local OEM rootfs verified against live system | all 99 `/lib/modules/4.4.271/*.ko`, 4 `/lib/firmware` files, `dect_eeprom`, `dect_manager`, `telefon` and `voipd` MD5-match the live OEM 08.25 system; `sha256sum` is absent on the OEM BusyBox, local SHA256 manifests remain authoritative | OEM-CAPTURE |
| Live OEM FDT | `/sys/firmware/fdt`: `/chosen/stdout-path=serial0`, `/avm-hw-revision/subrevision=2`, `/chosen/wlan_dect_configs=<0x2bc000 0x2bc800 0x2bd000>` | OEM-CAPTURE |
| OEM clock tree | `audio_clk_src`=200 MHz, `gcc_audio_pwm_clk`=200 MHz, `gcc_audio_ahb_clk`=100 MHz disabled; SC14448 TDM clock is not visible there | OEM-CAPTURE |
| `/proc/avm/profile` | it is **AVM Profiler v3** (CPU tracing), not a board/hardware profile; `csv` is empty, so it does not expose `avm_get_hw_config_table()` | OEM-CAPTURE |
| 74LVC1G04 | VCC/A/Y = 3.3/3.3/0 V measured under OpenWrt only; no link to GPIO40 or reset proven | RUNTIME-RO / **UNKNOWN role** |

Current D0.6 status and document navigation: `fon-d06-summary.md`.
Detailed disassembly is retained under `history/fon-d06-*.md`; the DTB
extraction procedure is `runbook/fon-oem-dtb-extraction.md`.

### 5c. OEM FRITZ!OS 08.25 runtime capture (2026-11-08)

Primary source: `reference/oem-08.25-boot/`. This is OEM **08.25** on this
board, not the older 4.4.60 wiki log.

| Fact | Value | Evidence |
|---|---|---|
| Board revision string | `FW(08.25)HW(236)HWS(2)BV(1.11581)BN(131719)FS(08.25)BT(1)` | OEM-CAPTURE |
| DECT UART | `msm_dectuart_probe: set dectuart_port to ttyMSM0` | OEM-CAPTURE |
| Runtime GPIO table | `gpio_avm_dect_reset 40`, `gpio_avm_dect_rd 16` | OEM-CAPTURE |
| Shared UART | `[piglet]===== shared usage of UART (DECT and CONSOLE) ...` | OEM-CAPTURE |
| DECT firmware upload | `dect_loader-bootmode`, then `upload of 'dectfw_secondlevel_441.hex' successfull` | OEM-CAPTURE |
| OEM TDM report | `[piglet]TDM: FS: 8000 Hz CLK: 1024355 Hz` | OEM-CAPTURE |
| PCMLINK and DMA | `pcmlink` module loaded; `mbox_dma_init: irq=107 hwirq=191` | OEM-CAPTURE |

These confirm the OEM-side sequence and the board subrevision, but they do
**not** prove GPIO40 polarity, the actual TLMM `FUNC_SEL`, physical PCM
wiring, or any OpenWrt behaviour. Q13/Q15/Q27/Q31/Q39/Q77/Q81 stay open.

### 5d. OEM 08.25 live console readback (2026-11-08)

Primary reference: `/home/rck/Downloads/OpenWrt7530/evidence/oem-08.25/console/2026-11-08/`.
Read-only console commands; no write, no toggle, no module load.

| Fact | Value | Evidence |
|---|---|---|
| GPIO40 at rest | `OUT`, `func=0`, `val=1`, `TLMM_GPIO_CFG=0x00004a02` | OEM-CAPTURE |
| GPIO16 | `IN`, `func=1` (blsp_uart0 RX), `val=1`, `CFG=0x00000004` | OEM-CAPTURE |
| GPIO17 | `OUT`, `func=1` (blsp_uart0 TX), `val=1`, `CFG=0x00000204` | OEM-CAPTURE |
| GPIO20 / GPIO24 | `func=0`, PU, `CFG=0x00004802` | OEM-CAPTURE |
| GPIO21 / GPIO22 | `func=2`, PU, `CFG=0x0000480a` | OEM-CAPTURE |
| GPIO23 / GPIO25 / GPIO26 | `func=3`, PU, `CFG=0x0000480e` | OEM-CAPTURE |
| GPIO27 | `OUT`, `func=3`, PU, `CFG=0x00004a0e` | OEM-CAPTURE |
| `pinmux-pins` for GPIO20–27 | `(MUX UNCLAIMED)` while `/proc/avm/gpio/list` shows func 2/3 | OEM-CAPTURE |
| ISDN/PCMLINK | `Codecslots=9 Slics=1 Pots=0 TE=0 NT=0 DECT=4 no HwCross DSP-EC: 0` | OEM-CAPTURE |
| ISDN registers | `REG_DIR=01100076`, `REG_ANALOG_IN=00000088`, `REG_ANALOG_OUT=01100026`; others zero | OEM-CAPTURE |
| `slic0/offhook` | `0` | OEM-CAPTURE |
| Piglet parameters | `piglet_dectmode=261`, `piglet_bitfilemode=2`, `hostclkmaster=0`, `dect_serial=0` | OEM-CAPTURE |
| PCMLINK parameters | `abmode=1`, `c55x_hexfile=/lib/modules/c55fw.hex`, `noslic=N`, `nocapi=N` | OEM-CAPTURE |

Consequences, kept narrow:

- **GPIO40 is high (logical 1) as an output while OEM is running.** The OEM
  reset sequence uses API 0 then 1, so this is consistent with reset released.
  It does not prove the SC14448 pin polarity or exclude an inverter.
- **GPIO16 is the UART RX pin** (`func=1`, owned by `78af000.serial`); the
  board-table name `gpio_avm_dect_rd` does not create a second GPIO function.
- **The OEM PCM mux is mixed:** MUX2 on GPIO21/22, MUX3 on GPIO23/25/26/27,
  while MCL GPIO20/24 remain `func=0`.
- `pinmux-pins` showing `(MUX UNCLAIMED)` is therefore **not** a hardware
  `FUNC_SEL` readback; the same pins show func 2/3 in `/proc/avm/gpio/list`.
- This is still OEM 08.25 state, not OpenWrt. The OpenWrt `FUNC_SEL`, physical
  PCB connectivity and reset-net polarity remain **UNKNOWN**.

### 5e. C0+ software TDM clock probe (offline, 2026-11-08)

| Fact | Value | Evidence |
|---|---|---|
| OEM boot check | `Piglet_noemif.ko:Check_TDMInterface()` at `0x3f0c..0x414c` | DISASM |
| OEM window | 100 ms: `high32(cyclefreq * 0x10624dd3) >> 6` = cyclefreq/1000, then `* 100` = cyclefreq/10 cycles | DISASM |
| OEM formula | `frequency = edges / (2 * 100 ms) = 5 * edges` | DISASM |
| OEM window order | FSC and DCL are measured in sequential 100 ms windows, not simultaneously | DISASM |
| OEM message | `[piglet]TDM: FS: 8000 Hz CLK: 1024355 Hz` | OEM-CAPTURE |
| pcmlink diagnostic | `ipq40xxtdm_checkhw()` at `0xa3b4..0xa7f0`, reached from `cmd_general` `0xa880`; not the boot line | DISASM |
| pcmlink window | 64-bit constant `0x82de1b43db34b6d7`; `window ≈ cyclefreq * 0.195008` cycles (≈195 ms), not 0.381 s | DISASM |
| TLMM map | base `0x01000000`, `GPIO_IO(n) = + n*0x1000 + 4`, input bit 0 | GPL (`pinctrl-ipq4019.c`) |
| Userspace probe | `tools/fon-tlmm-clock-probe/`; `PROT_READ` only, no GPIO/pinctrl/clk/reset API | OFFLINE |
| Synthetic tests | 52 checks: 8 kHz at 4×/8×/16×, 1.024 MHz, undersampled/aliased BCLK, scheduler gaps, frequency change, pulses, noise, static and short-window | OFFLINE |
| Stock image blocker | `# CONFIG_DEVMEM is not set`; `CONFIG_IO_STRICT_DEVMEM=y` | OFFLINE |
| Hardware run | **not run**; requires separate approval | — |

The probe observes only the IPQ4019 input path.  It does not prove the
physical wire, amplitude, signal quality or the SC14448 reset/firmware state.

### UART routing, established from the DTS (2026-11-08)

| Fact | Source |
|---|---|
| `serial0` = `blsp_uart0` = `serial@78af000` | `Fritz_qcom-ipq4019.dtsi` |
| its pins are `serial_pins` | same file, `pinctrl-0` |
| the base mux entry uses `gpio60`/`gpio61` with `function = "blsp_uart0"` and `bias-disable` | same file |
| HW236 redeclares the entry with `pins = "gpio16","gpio17"`; `dtc` **merges** node properties, so `function = "blsp_uart0"` and `bias-disable` survive | `Fritz_Box_HW236.dtsi` + **compiled DTB** `3083e2ac…bb841f` |
| `serial@78b0000` is `disable` in the HW236 DTB | same DTB |
| the DECT loader attaches to the first probed port when no `avm,dectstub_uart` node exists (there is none) | `msm_serial.c:1886-1908` |
| GPIO16 is also the board's `gpio_avm_dect_rd` (DTB `value = <0x10>`) | `Fritz_Box_HW236.dtsi` + DTB |

Compiled-DTB facts (AVM HW236, SHA256 `3083e2acedc8…bb841f`): `serial_pinmux`
→ `mux { pins="gpio16","gpio17"; function="blsp_uart0"; bias-disable; }`;
`serial@78af000` is `status="ok"` with `pinctrl-0 = <that node>`;
`serial@78b0000` is `disable`; no `avm,dectstub_uart` node.  OpenWrt's DTB
(SHA256 `cd6c5dec…3f4522e`) has the same pinmux; it differs in that it has no
`serial0` alias / `stdout-path`.

Consequence: **the DECT loader and the console use the same known UART
controller.**  No independent second UART path was found in this
configuration.  This does **not** prove that the four pads or
`gpio16`/`gpio17` reach the SC14448, nor that no other UART hardware exists on
the board, and **no source states the voltage on the Dialog side**.

Under OEM 08.25, GPIO16 is live as `func=1` UART **RX** (`pinmux-pins`:
`78af000.serial ... function blsp_uart0 group gpio16`), and GPIO17 is the
matching UART TX. The board-table name `gpio_avm_dect_rd` therefore identifies
the UART RX line; no independent GPIO role is observed. Q78 is closed. The
console and `msm_dectuart_*` still share the controller, and the software
arbitration between them is not recovered (Q79).

Correction: an earlier revision of this section claimed the HW236 override
*drops* `function` and `bias-disable`.  That was wrong; `merge_nodes()` keeps
them, as the decompiled DTB shows.

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

Times above are from the wiki 4.4.60 log. The 2026-11-08 **08.25** capture on
this board shows the same sequence with `CLK: 1024355 Hz` instead of
`1025720 Hz`; both are OEM reports from different builds, not OpenWrt
measurements. See `reference/oem-08.25-boot/`.

**The SC14448 is already running before any TDM client appears.**  A
probe-only test must not assume an unprogrammed chip.

## 7. Data path

| Fact | Value | Evidence |
|---|---|---|
| FON register transport | `TxDMA` / `PutRxDMA`, 16-bit word in TDM/MBOX **slot 5** | DISASM |
| Hook detection | RX slot 5 status bit 3 -> `reg 0x44` bit 7 | DISASM |
| Ring control | `reg 0x48` bits 5/6 -> ring command -> TX slot 5 | DISASM |
| Line feed | `reg 0x48` writes + `build_slic_ctrl` | DISASM (exact SC14448 bits unproven) |
| FON over UART | **disproved** — no UART imports in `pcmlink`, `isdn_fbox_fon5`, `avm_dect` | GPL |
| `pcmlink_ll_set_status` as FON transport | **disproved** — real link is `FPGALink` / QCA-ADSS | GPL, DISASM |

These are Linux-side facts from the proprietary `pcmlink.ko` disassembly. They
are **CONFIRMED on the Linux side** but do not prove how the SC14448 interprets
slot 5 (Q16/Q17/Q75). The source-class split is repeated in §4c.

## 8. Console UART

| Fact | Value | Evidence |
|---|---|---|
| Device | `serial@78af000`, 0x200 bytes | DT |
| GIC SPI | 107 | DT |
| Pins | GPIO16/17 | DT |
| Pin roles at runtime | GPIO16 `IN func=1` UART RX; GPIO17 `OUT func=1` UART TX | OEM-CAPTURE |
| DECT port selection | `msm_dectuart_probe: set dectuart_port to ttyMSM0` | OEM-CAPTURE |
| Shared use | DECT loader and kernel console; OEM 08.25 prints `shared usage of UART (DECT and CONSOLE)` | OEM, OEM-CAPTURE |
| Arbitration | console and `msm_dectuart_*` share the controller; the arbitration is not recovered (Q79) | **UNKNOWN** |
| FON driver use | **none** | CODE |

## 9. Our driver — first hardware run

### 9a. Boot path proven on hardware (HW-TEST, 2026-11-07)

The probe-only initramfs was booted **into RAM over TFTP** on the real
FRITZ!Box 7530.  NAND was not written at any point.

| Fact | Value | Evidence |
|---|---|---|
| Bootloader | `U-Boot 2012.07 [local,r35279-c2a758b16a]`, EVA `1.11581` | HW-TEST |
| U-Boot environment | **`bad CRC, using default environment`** | HW-TEST |
| NAND | `Macronix MX30LF1G18AC`, 128 MiB, 872 good PEBs, 0 bad | HW-TEST |
| Recovery route | started from `(FRITZ7530) #`, `run tftpboot` | HW-TEST |
| U-Boot net settings | `serverip=192.168.1.70`, `ipaddr=192.168.1.1` (RAM only, no `saveenv`) | HW-TEST |
| TFTP | `Bytes transferred = 9129136` (matches the probe FIT exactly) | HW-TEST |
| Kernel process | `Run /init as init process` — initramfs, not NAND rootfs | HW-TEST |
| Shell after boot | `root@OpenWrt:~#` on `192.168.1.1`, SSH reachable | HW-TEST |
| USB storage | `usb-storage` + `uas` + SCSI load; stick appears as `sda1` | HW-TEST |

The stock NAND boot does **not** provide USB storage: on the production image
`/lib/modules/6.12.112/` contains no `usb-storage`, `uas`, `scsi-core` or
`ext4` modules, so the stick cannot be mounted there.  Only the test
initramfs can read it.

### 9b. Module ABI finding (important)

| Module source | Result |
|---|---|
| SDK build (`openwrt-sdk-25.12.6-ipq40xx-generic`), 73 980 B, `b867b8c5…ad870` | **rejected**: `struct module section size must match the kernel's built struct module size at run time` |
| Same build tree as the kernel (`openwrt-25.12.6-source`), 74 796 B, `cd5c05fb…aff6` | **loads and probes correctly** |

Both report `vermagic: 6.12.112 SMP mod_unload ARMv7 p2v8`; only the tree
matches the kernel ABI.  A module built in the SDK is therefore **not usable**
with a kernel built from the full source tree, even for the same release.
The kernel in the test image is built from the workspace tree
(`gcc` owner `rck@Rck-1`), not from the SDK.

### 9c. Stage A result (RUNTIME-RO, no module)

| Observation | Value |
|---|---|
| `model` / `compatible` | `AVM FRITZ!Box 7530` / `avm,fritzbox-7530` |
| FON node | `fon-tdm@7700000` present, `status = okay` |
| `/proc/iomem` | no `0x77xxxxxx` owner entries |
| `/proc/interrupts` | no SPI 156/159 rows |
| `dmesg` | no FON/ADSS/TDM messages |
| Audio clocks | `gcc_audio_ahb_clk`, `audio_clk_src`, `gcc_audio_pwm_clk` all present, **`deviceless`**, enable count 0 |
| GPIO40 | `pin 40 (GPIO_40): (MUX UNCLAIMED) (GPIO UNCLAIMED)` |
| Console | `ttyMSM0` holds the console |

Evidence: `../../evidence/stage-a/stage-a.tar.gz` and the console boot log.

### 9d. Stage B result (probe-only, HW-TEST)

`load-probe-only.sh --yes` passed.  Console and `dmesg`:

```text
fon-tdm 7700000.fon-tdm: probe-only: resources=0x3f irq_spi=156/159
    irq_intid=188/191 clock_refs=0 reset_refs=0 pinctrl_ref=0 dt_overlap=0
fon-tdm 7700000.fon-tdm: FON probe-only ready;
    no MMIO/clock/reset/IRQ/DMA access
```

| Diagnostic | Expected | Observed |
|---|---|---|
| `stage` | `0x23` | `0x23` |
| `resource_mask` | `0x3f` | `0x3f` |
| `irq_spi` | `156/159` | `156/159` |
| `irq_intid` | `188/191` | `188/191` |
| `irq` | `-1` | `-1` |
| `diag_valid` / `dma_prepared` / `dma_started` | `0` | `0` |
| `clock_refs` / `reset_refs` / `pinctrl_ref` | `0` | `0` |
| `slots` | `8` | `8` |
| `dt_overlap` | `0` | `0` |

Resources parsed from the live DTB (not from documentation):

| Index | Name | Start | End |
|---|---|---|---|
| 0 | `adss` | `0x07700000` | `0x07700033` |
| 1 | `pcm` | `0x07704000` | `0x07705fff` |
| 2 | `mbox_tx` | `0x07708000` | `0x07708fff` |
| 3 | `mbox_rx` | `0x0770e000` | `0x0770efff` |
| 4 | `stereo_tx` | `0x07709000` | `0x07709fff` |
| 5 | `stereo_rx` | `0x0770f000` | `0x0770ffff` |

No register was read: `audio_mode`, `tdm_ctrl`, `clk_ctrl`, `i2s_rst`,
`stereo_tx_cfg`, `stereo_rx_cfg` all report `0x00000000`.

Isolation checks:

- `/proc/iomem` byte-identical before and after the load;
- `/proc/interrupts` shows only counter growth for pre-existing IRQs, **no
  new rows**, so no IRQ was requested;
- after `unload.sh --yes`: `lsmod` has no `fon_tdm_drv`, no `driver` link and
  no `stage`/`diagnostics` attributes remain; the `7700000.fon-tdm` entry in
  `/sys/bus/platform/devices` is the DT node itself.

Evidence: `../../evidence/stage-b/stage-b-2/`.

### 9d-2. Stage C0 on hardware (RUNTIME-RO, 2026-11-07)

`bench/collect-stage-c0.sh` ran on the probe-only image.  It only read DT,
`/proc`, debugfs clocks and debugfs pinctrl.

| Observation | Value |
|---|---|
| FON node | present, `status = okay` |
| `qcom,tdm-slots` decoded from DT | **8** |
| `clocks` / `resets` / `pinctrl-0` on the FON node | **absent / absent / absent** |
| `gcc_audio_ahb_clk` | enable 0, hw gate `N`, `deviceless` |
| `audio_clk_src` | enable 0, hw gate `N`, parent XO, 48 MHz |
| `gcc_audio_pwm_clk` | enable 0, hw gate `N` |
| ADSS ranges in `/proc/iomem` | **none claimed** |
| SPI 156/159 | absent |
| GPIO20-27 and GPIO40 | all `(MUX UNCLAIMED) (GPIO UNCLAIMED)` |

Comparison with a clock that *is* in use: `gcc_blsp1_ahb_clk` has
`enable=4`, `hw=Y`, consumer `78af000.serial`; `gcc_audio_ahb_clk` has the
same parent (`pcnoc_clk_src`, enabled) but no consumer.  The audio branch is
gated by the absence of an owner, not by a dead parent.

The pinmux observation is about **Linux ownership**, not the hardware
register. `(MUX UNCLAIMED)` means that no Linux pinctrl/GPIO consumer owns the
pin; it is not a readback of the TLMM `FUNC_SEL` field and does not prove that
the field is `0`. The actual mux value, the pad state, the electrical
connection to the SC14448 and the presence of FSC/BCLK all remain **UNKNOWN**
(Q27/Q31). A read-only TLMM readback or a passive measurement is required.

Evidence: `../../evidence/stage-c0-final/stage-c0g/`, archive sha256
`2a9f4afc3164131a180e579e55fa9c43b1bb9c02146e23e32d993e95a4030d7e`.
Three collector defects were only visible on the device and are fixed:
BusyBox awk has no `strtonum`, `od` is absent, and the iomem owner test
matched non-ADSS ranges.

### 9d-3. C1 preparation image built (2026-11-07, not booted)

The FON node now carries the two links the C1 stage needs:

```dts
clocks = <&gcc GCC_AUDIO_AHB_CLK>;   /* 0x181b010 bit 0 */
resets = <&gcc GCC_AUDIO_BCR>;       /* 0x181b008 bit 0, id 44 */
```

Verified offline three ways:

| Check | Result |
|---|---|
| `dtc` on the standalone test DTS | `clocks = <0x05 0x13>`, `resets = <0x05 0x2c>` |
| built board DTB | same two properties, `status = "okay"` |
| DTB extracted from the FIT | same two properties inside the image |

Build artefacts:

| Artefact | Value |
|---|---|
| initramfs FIT | 9 129 176 B, sha256 `4c3bdfd1ca1bd07b0318fad600c8a920227842671c2e29b8d8aac7c72e5825d9` |
| kernel `vmlinux` | sha256 `a79df5c3...baf32` (rebuilt: the DTB is part of the kernel image) |
| `fon_tdm_drv.ko` | unchanged, sha256 `cd5c05fb...6aff6` |

The module did not change, so the Stage B kit on the stick stays valid, and
the probe-only behaviour (`clock_refs=0`, `reset_refs=0`) must stay identical
after this image boots — that is the first thing to confirm.

### 9d-4. Probe-only still side-effect free with the C1 links (HW-TEST, 2026-11-07)

The C1 preparation image was booted into RAM and Stage B was repeated.

| Diagnostic | Before (9d) | After the DT change |
|---|---|---|
| `stage` | `0x23` | `0x23` |
| `clock_refs` | `0` | **`0`** |
| `reset_refs` | `0` | **`0`** |
| `pinctrl_ref` | `0` | `0` |
| `irq` | `-1` | `-1` |
| `/proc/iomem` before/after | identical | identical |
| new `/proc/interrupts` rows | none | none |
| unload | clean | clean, no driver link or attributes |

Live DT confirmed inside the running kernel:

```text
clocks  interrupts  resets  status
clocks  00000000 00 00 00 05 00 00 00 13    /* &gcc, GCC_AUDIO_AHB_CLK = 19 */
resets  00000000 00 00 00 05 00 00 00 2c    /* &gcc, GCC_AUDIO_BCR     = 44 */
status  okay
```

Conclusion: **declaring a clock and a reset in DT does not make a
probe-only load acquire them.**  The resources exist for C1 and remain
untouched under Stage B.

Evidence: `../../evidence/stage-b-c1/stage-b-c1/`.

### 9d-5. Metric defect: clock_refs did not measure what it claimed

While preparing C1 the diagnostic counter was found to be misleading:

```c
tdm->clock_refs = fon_dt_string_count(np, "clock-names");
tdm->reset_refs = fon_dt_string_count(np, "reset-names");
```

It counted the **`-names`** properties only.  After the DT gained

```dts
clocks = <&gcc GCC_AUDIO_AHB_CLK>;
resets = <&gcc GCC_AUDIO_BCR>;
```

without `clock-names`, the module still printed `clock_refs=0`, which read
as "the node declares no clock".  That conclusion was wrong: the properties
were present and verified in the live DT.

Consequence for the earlier claim: the Stage B result after the DT change
does **not** by itself prove that probe-only ignores the links.  What does
prove it is the rest of the same run — `FON probe-only ready; no
MMIO/clock/reset/IRQ/DMA access`, unchanged `/proc/iomem`, no new interrupt
rows — plus the fact that the probe-only branch returns before any
`devm_clk_get()`/`devm_reset_control_get()` call exists in that path.

Fixes:

- `clock_refs`/`reset_refs` now count phandles **and** names;
- diagnostics gained the raw facts `dt_clocks`, `dt_clock_names`,
  `dt_resets`, `dt_reset_names`, so "declared" can never again be confused
  with "acquired";
- the FON node now also carries `clock-names = "audio_ahb"` and
  `reset-names = "audio_blk"`, because the full-mode path obtains clocks by
  name and C1 would otherwise get nothing.

### 9d-6. Corrected metric verified on hardware (2026-11-07)

The rebuilt module reports the DT facts separately from the acquisition
state, and the distinction is now visible:

| Field | Value | Meaning |
|---|---|---|
| `dt_clocks` | **2** | one phandle plus one cell (`#clock-cells = 1`) |
| `dt_clock_names` | **1** | `clock-names = "audio_ahb"` |
| `dt_resets` | **2** | one phandle plus one cell |
| `dt_reset_names` | **1** | `reset-names = "audio_blk"` |
| `clock_refs` / `reset_refs` | **3** / **3** | combined counter, no longer zero |
| **`clk_present`** | **0** | the driver acquired **no** clock |
| **`reset_present`** | **0** | the driver acquired **no** reset |
| `pinctrl_present` | `0` | no pinctrl state |
| `irq` | `-1` | no IRQ requested |

So the earlier ambiguity is gone: the node **declares** a clock and a reset
(non-zero `dt_*`), and probe-only **still acquires neither** (`*_present`
are 0).  `FON probe-only ready; no MMIO/clock/reset/IRQ/DMA access` is
printed from that same run.

Artifacts: module `a9ee7a13...d30f` (76 412 B), image `154bd755...4811`,
evidence `../../evidence/stage-b-c1b/stage-b-c1b/`.

### 9d-7. Stage C1: the ADSS block answers on the bus (HW-TEST, 2026-11-07)

First authorised clock/reset/MMIO access.  Module `2b523aec...9e40`,
loaded as `probe_only=0 run_c1=1`.

Sequence actually executed (each step logged before it ran):

```text
step 1  devm_clk_get("audio_ahb")
step 2  clk_prepare_enable      -> rate 100000000 Hz
step 3  devm_reset_control_get("audio_blk")
step 4  assert, 20-24 ms, deassert
step 5  ioremap adss / stereo_tx / stereo_rx
step 6-11  six readl() calls, no write anywhere
step 12 reset asserted again
step 13 clk_disable_unprepare
```

Register values read once, immediately after the reset pulse:

| Register | Offset | Value |
|---|---|---|
| `ADSS_GLB_AUDIO_MODE` | `0x30` | `0x00000000` |
| `ADSS_GLB_TDM_CTRL` | `0x1c` | **`0x00010001`** |
| `ADSS_GLB_CLK_I2S_CTRL` | `0x18` | `0x00000000` |
| `ADSS_GLB_I2S_RST` | `0x14` | `0x00000000` |
| `STEREO_TX_CONFIG` | `0x00` | **`0x00000102`** |
| `STEREO_RX_CONFIG` | `0x00` | **`0x00000102`** |

Interpretation, from the GPL bit definitions:

- `TDM_CTRL = 0x00010001`: `TX_CHAN_NUM = 1` and `RX_CHAN_NUM = 1`, i.e.
  **two channels per direction, not the eight slots the FON needs**
  (`GLB_TDM_CTRL_TX_CHAN_NUM(slots-1)` would require `7`);
  delays and sync counts are zero.
- `STEREO_CONFIG = 0x102`: bit 8 is `STEREO_CONFIG_MASTER`, so **the block
  came up as master, not slave**.  Bit 1 is not part of the documented
  mask and its meaning is unknown.
- Everything else is zero, which is what a freshly deasserted block should
  report.

What this proves:

| Question | Answer |
|---|---|
| Is the ADSS window readable? | **yes** |
| Does the AHB clock gate it? | not proven either way — it was enabled, and reads worked |
| Are values plausible, not bus noise? | **yes**: no `0xffffffff`, two structured fields |
| Is TDM configured for the FON? | **no** — channel count is 1, not 7 |
| Is the block in slave mode? | **no** — `MASTER = 1` |

A clock-framework warning was emitted on step 13 (`clk_branch_toggle`
warn path from `clk_core_disable`): the gate did not report halting within
the poll timeout.  The enable count did return to 0 and the block was left
asserted, but the warning means the stop is **not confirmed**.

After `rmmod`: no module, `gcc_audio_ahb_clk` back to enable 0, no
`0x77000000` region in `/proc/iomem`, no leftover attributes.

### 9d-8. Stage C2: the ADSS accepts the FON configuration (HW-TEST, 2026-11-07)

First stage that **writes** to ADSS.  Module `3546c2b9...85c6`, loaded as
`probe_only=0 allow_hw_writes=1 run_c2=1`.

Sequence: enable AHB clock -> pulse reset -> baseline read -> write three
registers -> read back -> re-assert reset -> disable clock.  No DMA, no IRQ,
no GPIO, no SC14448 traffic.

| Register | Before | Written | Read back | Match |
|---|---|---|---|---|
| `ADSS_GLB_TDM_CTRL` | `0x00010001` | `0x06070007` | `0x06070007` | **yes** |
| `STEREO_TX_CONFIG` | `0x00000102` | `0x00240000` | `0x00240000` | **yes** |
| `STEREO_RX_CONFIG` | `0x00000102` | `0x00240000` | `0x00240000` | **yes** |
| `ADSS_GLB_AUDIO_MODE` | `0x00000000` | `0x10000005` | `0x10000005` | **yes** |
| `ADSS_GLB_CLK_I2S_CTRL` | — | not written | `0x00000000` | — |
| `ADSS_GLB_I2S_RST` | — | not written | `0x00000000` | — |

Decoded:

- `TDM_CTRL = 0x06070007`: `TX_CHAN_NUM = RX_CHAN_NUM = 7` (eight slots) and
  both 1-bit delays set — the geometry the FON path needs;
- `STEREO_CONFIG = 0x00240000`: `ENABLE` (21) and `NO_I2S_DELAY` (18) set,
  **`MASTER` (8) cleared**, so the block is now a slave;
- `AUDIO_MODE = 0x10000005`: `B1K` (28), `INTERFACE_EN` (0), `TX TDM` (0)
  and `RX TDM` (2) set.

What this proves:

| Question | Answer |
|---|---|
| Does ADSS accept writes? | **yes**, all three read back exactly |
| Can the block be set to eight slots? | **yes** |
| Can it be switched to slave? | **yes**, `MASTER` stayed cleared |
| Is the bus stable under writes? | **yes**, no hang, no abort |
| Is a clock output enabled? | **no** — `CLK_I2S_CTRL` is zero, and in slave mode it must stay zero |

Remaining unknown: with the block correctly configured as slave, the FON can
only work if the **SC14448 actually drives BCLK/FSC**.  Nothing in software
can tell us that; it is still Q27.

The clock-framework warning on the disable path appeared again (same
`clk_branch_toggle` path).  After `rmmod`: no module, `gcc_audio_ahb_clk`
back to enable 0, no `0x77000000` region.

### 9d-9. C1/C2 error handling and the AVM order (2026-11-07, code only)

Review of the executed C1/C2 found four defects, all fixed without a new
hardware run:

| Defect | Effect | Fix |
|---|---|---|
| C1 returned 0 after a failed step | false success | every failure stored in `err` and returned |
| C1 overwrote `step` with a cleanup number | misleading trace | `step` is the last completed step |
| C2 did not save reset assert/deassert errors | false success | the errno is kept; `cleanup_err` is separate |
| `stereo_ok` accepted a readback with only `ENABLE` | false success | all four registers compared, mismatch returns `-EIO` |

Order corrections against AVM's `ipq-adss-avm.c`:

- `ADSS_GLB_CHIP_CTRL_I2S` (`0x10`, bit 0) must be enabled during the ADSS
  probe, before TDM configuration; the executed C2 never wrote it;
- `ADSS_GLB_I2S_RST` (`0x14`) is pulsed (`0xF`, 4-5 ms, then `0`);
- STEREO uses `DATA_WORD_SIZE(1)`, which sets `BIT(12)`; the executed C2
  left it at zero.

The executed hardware values remain valid as observations (C1 and C2 both
ran, registers were written and read back), but they were produced by a
sequence that was **incomplete**, so they do not prove a working FON setup.

Address correction: `STEREO0_CONFIG` is at `0x07709000` and
`STEREO3_CONFIG` at `0x0770f000`.  The earlier `0x07708000`/`0x0770c000`
were MBOX windows.  The executed C2 therefore wrote the right STEREO
blocks.

### 9d-10. Firmware analysis: what is proven and what is not (2026-11-07)

A CR16 `objdump` was built locally from `binutils-2.44` and validated on the
known-good `0x2582` snippet.  Nothing was installed system-wide.

**Proven from the image:**

| Claim | Evidence |
|---|---|
| `0xFF6006` is written `0x80`, read, then written `0` | disassembly of `0x2558`-`0x25B8` (address `0x00FF6006`, *not* `0x000F6006`; see §9h) |
| `0x80` is `BIT(7)` | by value |
| it is a trigger, not a format register | set and cleared nine instructions later; no rate/word-size/master field exists in the function |
| the read-back is discarded | `movw $0x400:m,r2` overwrites the value at `0x25ac` |
| `0x000000` is not a valid entry point | `loadm $1,r0` then `illegal`; execution instead reaches `0x000008` through the loader hand-off |
| no slot-5 / FON command handler found | bounded search over all immediate peripheral references and both large code blocks |
| `0x2570` calls `0x3C8C`, `0x257E` calls `0x24F8` | branch decoder, §9d-11 |
| `0x24F8` is not recursive | decompiled as a bounded loop; its only `bal` caller is `0x257E` |
| `0x000008` is executable | `br 0x15AA` in `normal`, `br 0x1026` in `p2test` |

**Still unproven:**

| Question | Why |
|---|---|
| which top-level path reaches `0x2558` on the real chip | a static CFG path from `0x1602` exists, but `0x1602` is not proven to be the reset entry (Q47/Q64) |
| what `BIT(7)` of `0xFF6006` does | no code reads it back |
| whether `0xFF600E` is used | not found as an immediate; indirect access not excluded |
| whether `0x000F6002` is set by `0x00FF6006` | the two addresses are not proven to alias |
| whether the table at `0x24` is used as the hardware vector table | the runtime copy at `0x15F6` is unresolved |

Branch targets are decoded by the validated rule. Executing this code on the
SC14448 remains unverified; instruction bytes, boundaries and immediate
constants are unaffected.

### 9d-11. CR16 branch decoding solved; call graph re-derived (2026-11-07)

**The encoding is now established from the binutils source and confirmed on
firmware:**

```text
allWords = (w0 << 32) | (w1 << 16) | w2
p        = EXTRACT(allWords, 16, 24)          for a 2-word bal
sign     = p & 1                              <- bit 0, not the top bit
target   = addr + ((-p) & 0xFFFFFE)           when sign
target   = addr + p                           otherwise, mod 2^24
```

`addr` is the address of the instruction itself.  `objdump` prints the
**absolute target**; its `*-` prefix only reflects the sign flag.

Independent proof: `0x0AF0` prints `*-0x496` and `0x496` starts with
`push $0x7,r7,RA`, a prologue.  `0x131E` prints `*-0x11CE` and `0x11CE`
starts with `push $0x1,r7`.  `0x257E` prints `*-0x24f8` and `0x24F8` is the
block entry.  A prologue cannot appear mid-function, so the printed
magnitude is the target.

**Validated call targets:**

| Call | Target | Content |
|---|---|---|
| `0x2570` | `0x3C8C` | `push $0x3,r7,RA`; copies or clears an array through `0x28CF4` / `0x28D3C` |
| `0x257E` | `0x24F8` | the `0xFF400A` bit loop — **not recursive**; `0x24F8` contains no call to itself |

**Caller of `0x24F8`:** `0x257E` is the only `bal` site that targets it.

**Cross-block graph:** 1298 `bal` candidates, 1289 resolve inside a loaded
run.  Edges exist in both directions between `0x2b4-0x1aad` and
`0x24f8-0x3cfd`, so the block is connected — but its entry address still has
no external caller.

**Peripheral note:** `0xf6400:m` is a 16-bit absolute operand whose
effective address is `0x000F6400` unless a segment is implied; whether the
hardware decodes it as `0xFF6400` is **not established**.

### 9d-12. Global CFG: the PCM bring-up chain (2026-11-07)

The 6-byte instruction bug was fixed (objdump prints the extra word on a
second line with no mnemonic), and a global CFG across all runs was built.
Instruction sizes in `dectfw_secondlevel_441.hex`: 2 B x 13 546, 4 B x
4 832, 6 B x 1 191.

**Reachability chain found:**

```text
0x1602 (candidate top level, no caller in the image)
  -> 0x39F8 -> 0x3A2C -> 0x25FB8 -> 0x25F90
       -> 0x25FAA -> 0x2558 -> 0x257E -> 0x24F8 (not recursive)
```

Current loop facts (the earlier "512 words" and "recursion" readings are
withdrawn; see `history/fon-dialog-cr16-cfg.md` and
`history/fon-dialog-peripheral-init.md`):

| Claim | Status |
|---|---|
| `0x24F8` is reachable from the top-level CFG | **proven statically** |
| `0x257E` is the only caller of `0x24F8` | **proven statically** |
| `0x24F8` contains no self-call | **proven statically** |
| `0x25F90` writes **511** 16-bit words with `0x1001` at `0x01000002`–`0x010003FE` | **proven** (indices 1–511; `0x01000000` itself is not written) |
| it then pulses `0x00FF6006` and polls `0x000F6002` for `1` | **proven** |
| the buffer is the PCM buffer | **not proven** — `0x01000000` is in no loaded run |
| `0x1001` has a known field layout | **not proven** |

`p2test` reproduces the same constants at shifted addresses
(`0x1001` at `0x26750`, poll at `0x26764`, `0xFF6006` at `0x1E3E`), so the
bring-up is the same code in both builds. The earlier edge statistics are
historical and are not repeated here.

## 9g. CR16 decoding and CFG (OFFLINE, 2026-11-07, iteration 3)

| Fact | Value | Level |
|---|---|---|
| 2-byte conditional target for `49 1f` at `0x25FA8` | `0x25F9A` (−0x0E) | L2 |
| 2-byte conditional target for `1d 1f` at `0x25FB4` | `0x25FAE` (−0x06) | L2 |
| branch validation matches, both images | **7 920** (normal 4 085 + p2test 3 835), **0 mismatches**, **0 unsupported** | L2 |
| unsupported branch forms | **0** — the 113 former cases (112 backward `disps17`, 1 `disps25`) decode with the `cr16-dis.c` rule | L2 |
| `br` semantics | unconditional jump, no link, no fall-through | L2 |
| `0x25F90` loop | `cmpw $0x200` + `bhi` → 0x25F9A | L3 |
| fill iterations | **511** (indices 1..511) | L4 |
| fill range | `0x01000002` … `0x010003FE` | L4 |
| `bhi` condition | `PSR.L`, set when `Rdest < Rsrc` (CR16A manual) | L4 |
| `0x2558`…`0x25B8` | one function, no caller of `0x257E` | L3 |
| address operand `abs20` | `((b0 & 0x0F) << 16) \| word1` | L2 |

CFG statistics (normal image, 22 669 edges after `br` was reclassified as an
unconditional jump): `DIRECT_RESOLVED` 22 244, `DIRECT_UNSUPPORTED` 0,
`INDIRECT_REGISTER` 382, `INDIRECT_TABLE_RESOLVED` 0,
`FALLTHROUGH_UNRESOLVED` 9, `OUTSIDE_LOADED_IMAGE` 2,
`TARGET_NOT_INSTRUCTION` 30.  Mode A from `0x1602` reaches 8 340
instructions, mode B 17 546, mode C is empty.

`br` is the unconditional relative branch (CR16A §"BR (Unconditional
Branch)"); it has no fall-through, and 615 false fall-through edges were
removed when this was fixed.

Nothing in this section reaches L5 (hardware): the register meanings remain
unknown.

## 9h. Peripheral cross-references (OFFLINE, 2026-11-07)

Produced by `tools/cr16_peripheral_xrefs.py`; report in
`tools/reports/peripheral-xrefs.json`; details in
`history/fon-dialog-peripheral-xrefs.md` and `history/fon-dialog-peripheral-map.md`.

The first version of this scanner saw only `abs20` operands and `movd`
literals: it recognised `disp:m(rp)` but not the `disp:s(rp)` form the
firmware actually uses, so **no** register-pair access appeared in its report
(0 resolved register-pair accesses, 618 records of which 568 were address
literals).  The current version (3) parses every operand form, tracks
register pairs inside a basic block, and classifies every memory instruction.
The numbers below come only from version 3.

`0x000F6006` and `0x00FF6006` are **different addresses** and are listed
separately; nothing establishes that they alias the same register.

| Fact | Value | Evidence |
|---|---|---|
| reader(s) of `0x000F6002` | exactly one, `0x25FAE` (normal) / `0x26764` (p2test) | L1/L2 |
| writer(s) of `0x000F6002` | none among resolved forms; `UNKNOWN`/`SYMBOLIC` accesses remain unexamined | L2 |
| writers of `0x000F6006` | `0x1348`, `0x145C`, both writing `0x0080` | L2 |
| readers of `0x000F6006` | `0x2602C`, `0x28CDE` | L2 |
| writers of `0x00FF6006` | `0x258C` (`0x0080`), `0x25B4` (`0`) | L2 |
| readers of `0x00FF6006` | `0x25AA` (value discarded) | L2 |
| writers of `0x000F6400` / `0x000F6402` | one each (`0x255E` / `0x2566`), no readers | L2 |
| writers of `0x000F5402` | seven, values `0x0400`, `0x2000`, `0x0100`, `0xFFFF` | L2 |
| `0x00FF5406` | read-modify-write at `0x1A1A`–`0x1A22`, `0x259C`–`0x25A2`, `0x26046`–`0x26050` | L2 |
| `0x01000000` | 6 `movd` literals; stores at `0x25D0`/`0x2618` are `SYMBOLIC` (`0x01000000 + 2*r3/r4`) | L2 |
| reader of `0x01000000` | none resolved to a constant; all uses are computed (Q55) | L2, limited |
| access width of every register above | 16 bits (`loadw`/`storw`) | L2 |
| the `0x000Fxxxx` and `0x00FFxxxx` blocks are the same hardware | **not established** | — |

Statistics (version 3 + PERIPH-2.2), `ADDRESS_LOAD` kept outside the memory
totals:

| Counter | normal | p2test |
|---|---|---|
| decoded instructions | 19 570 | 18 058 |
| memory instructions, supported | 5 167 | 4 703 |
| memory instructions, unsupported (`loadm`/`loadmp`) | 16 | 2 |
| READ / WRITE / READ_MODIFY_WRITE | 2 596 / 2 272 / 299 | 2 374 / 2 076 / 253 |
| address RESOLVED / SYMBOLIC / UNKNOWN | 951 / 8 / 2 812 | 964 / 10 / 2 631 |
| address STACK / INDEXED / PC_RELATIVE | 826 / 529 / 41 | 697 / 380 / 21 |
| ADDRESS_LOAD (not a memory access) | 568 | 480 |

The register-effects rules are documented in
`history/fon-dialog-cr16-register-effects.md`.  Two corrections since PERIPH-2.1:

| Rule | Value |
|---|---|
| widening/multiply forms | `OP src,dest` (CR16A `MOVZB src, dest`, `MULi src, dest`): `movzw r3,(r7,r6)` **writes the pair**, `movzb r8,r0` writes `r0` |
| `sbit*`/`cbit*` | read-modify-write of one bit, 299 operations in `normal` that earlier statistics did not count |
| `tbit*` | single-bit read, 567 operations in `normal` |
| `loadm`/`loadmp`/`storm`/`stormp` | not decoded; listed per instruction under `memory_unsupported` |
| `pop`/`popret` | register list not modelled (Q60); harmless today because blocks never carry state across a `pop` |

What precedes `0x25F90` on the path from `0x1602`: `0x3A08 di`,
`0x3A0C -> 0x1388` (clears `0xF5404/6/8/A`, sets `0xFF4856` bits, sets
`0xF401A` bit 1, writes `0x80` to `0x000F6006`), `0x3A28` writes `0xFFFF` to
`0x000F5402`.  What follows: `0x25FB8` calls `0x25EA6`.

No register in this section reaches L5; none is named after a function.

## 9i. The `data:l` (abs24) form was invisible (OFFLINE, 2026-11-07)

The 6-byte `opc20` load/store form printed as `<abs>:l` was dropped by the
first scanner.  Its address is

```text
words = [b0 | b1<<8, b2 | b3<<8, b4 | b5<<8]
packed = words[0]<<32 | words[1]<<16 | words[2]
addr  = ((packed >> 16) & 0xF) << 20 | ((packed >> 24) & 0xF) << 16 | (packed & 0xFFFF)
```

which matches all 161 (normal) and 170 (p2test) occurrences and the assembler
output for `0x0fffff`, `0x100000` and `0xff4c00`.

Its two consequences:

| Fact | Value | Evidence |
|---|---|---|
| `0x15AE` (normal) / `0x1030` (p2test) | `storb r0,0xff4c00:l` with `r0 = 0xFF` — the first **direct** access to the `0x00FFxxxx` block | L1/L2 |
| `0x15B6` (normal) / `0x1038` (p2test) | `storb r0,0xff5000:l` with `r0 = 0x08` | L1/L2 |

Both blocks are 8-bit accesses, unlike every other studied `0xFFxxxx`
register (16-bit), and are not reached in mode A.

The `imm:l` printouts of `movd`/arithmetic instructions are **not** decoded by
this formula: binutils' disassembler derives them from the `imm20`/`imm32`
argument class, and the assembler itself rejects `movd $imm:l` (it emits
`imm:m`).  Only `movd`'s printed literal is used, never an address derived
from its encoding.

## 9j. CR16 addressing, system registers and alias candidates (OFFLINE, 2026-11-07)

Documents: `history/fon-dialog-cr16-addressing.md`,
`history/fon-dialog-cr16-system-registers.md`,
`history/fon-dialog-address-alias-hypotheses.md`; report
`tools/reports/cr16-address-alias.json` from `tools/cr16_address_alias.py`.

| Fact | Value | Evidence |
|---|---|---|
| CR16A address width | 18 bits (`0 … 0x3FFFF`) | L2, manual §2.4 |
| is the core CR16A? | **no** — the images address above `0x3FFFF` | L1 |
| `abs20` field | 20 bits, low nibble of byte 0 is bit 20 | L1/L2 |
| `abs24` field | 24 bits, relocation refuses above `0xFFFFFF` | L1 |
| decoder masking | **none** — neither encoding is shifted or masked | L2 |
| `INTBASE` | written once: `0x24` (`0x15E6`, `0x1068`) | L2 |
| `ISP` / `USP` | `0x3FF0` / `0x3F00` | L2 |
| `CFG` | bit 8 only; cleared by the first-level image, set by it and by the second-level image | L2 |
| table at `INTBASE` | 31 address-like words, not code bytes; the runtime effect of the copy at `0x15F6` is unresolved | **UNKNOWN** |
| reset entry | `0x15AA`/`0x102C` starts the system-register setup and has **no caller** in the image; not proven to be the reset vector | L3 |
| address pairs with equal low 20 bits | **12** in `normal`, **12** in `p2test`, the same set | L2 |
| `0x000F6006` ↔ `0x00FF6006` | same low bits, different access structure | L2 |
| are the two one physical register? | **UNKNOWN** — no document, no hardware | — |

## 9k. Boot chain and memory layout (OFFLINE, 2026-11-07)

Documents: `history/fon-dialog-firstlevel-cfg.md`, `history/fon-dialog-uart-boot-protocol.md`,
`history/fon-dialog-boot-memory-map.md`, `history/fon-dialog-boot-handoff.md`; report
`tools/reports/cr16-boot-memory-map.json`.

| Fact | Value | Evidence |
|---|---|---|
| first-level image | one block, `0x10080`–`0x102E9`, 618 bytes | L1 |
| second-level image (`normal`) | 9 blocks, `0x0`–`0x28DCD`, 54 047 bytes | L1 |
| upload format on the wire | `u32be address`, `u32be length`, then the bytes | L2 |
| loader writes received bytes where | `storb r2,0x0:s(r12)` at `0x1022C`, `(r12)` from the 4-byte header | L2 |
| is the second-level relocated | **no** — the header carries the address and the loader adds no base | L2 |
| loader code overwritten by the image | **no** — no second-level block covers `0x10080` | L1 |
| `0x0` is a plausible entry | **no** — `loadm $1,r0` then `illegal`; the hand-off enters `0x000008`, whose `br` is decoded | L2 |
| runtime execution of the hand-off | **not observed** on the SC14448; only the static chain is proven | **UNKNOWN** |
| `0x28D56` semantics | walks 8-byte records `{u32le count, u32le dest}` from `(r3,r2)` to `(r5,r4)` and writes `count` **zero** bytes per record (`r4` forced to 0 at `0x28D62`) | L2 |
| call `0x15F6` | `fn_28d56(0x1C, 0x24)` = one record `{count=0x8F2, dest=0x936C}` → clears 2290 bytes at `0x936C` | L2 |
| `0x936C` | first byte past the block that starts at `0x9000`; not covered by any block | L1 |
| table at `0x24` | **31** entries of 32-bit little-endian values; ×2 gives instruction boundaries (`0x28996`, `0x28A94`, `0x28CD0`, `0x28DCA`) | L2 |
| `0xA0` is not a vector | its bytes `01 05 …` are TLV tag 1 (RFPI, length 5) from `piglet_protocol.h` | L1 |
| `.bss` in p2test | clears `[0x94A4, 0x9B43)`, one byte short of the next block at `0x9B44` (all blocks start even) | L2 |
| table is an exception dispatch table | 31 entries, entry = handler address ÷ 2 (confirmed by TobleMiner `device/vectors.s`) | L2 + external |
| real handlers | vectors 24, 26, 29; all other indices share the `nop`/`retx` stub | L2 |
| vectors 20–22 (UART RX/TX, SPI per SC14441) | **stubs** in both images — the SC14441 numbering does not transfer | L2 |
| handler acknowledgements | vector 24 writes `0x0100`, 26 writes `0x0400`, 29 writes `0x2000` to `0x000F5402` | L2 |
| `.bss` clear | `[0x936C,0x9C5E)` (normal) and `[0x94A4,0x9B44)` (p2test) end exactly at the next block | STRONG_INFERENCE |
| UART bit layout | RI = 6, TI = 5, baud field 2–4 = `0xC` → 115200 | L2 + external, matches |
| watchdog | `0x000F4C00 ← 0xFF` inside the wait loops | L2 + external, matches |
| `CFG` bit 8 | set before `INTBASE`; reference calls it "read exception handlers as 32 bit wide" | strong hypothesis |
| PLL / clock registers | `0x00FF4010` (`CLK_PLL_CTRL_REG`) and `0x00FF481E` (`PAD_CTRL_REG`) are used at the **exact** reference address; `0x000F4002/400C/4012/401A` match the reference's `0x00FF40xx` clock block | L2 + external |
| SC14448 reference config | the fork declares `CHIP_SC14448`, RAM origin `0x00010000`, and lists `Gigaset C430 / SC14448` as tested; the RAM size is marked "just a guess" in the source | external only |
| table encoding | word offsets (address ÷ 2); 4/4 address-like values land on prologues, p ≈ 3e-9 by chance | L2 |
| `0x7C` | **inside** block 1 (`0x0`–`0xD4`), holds `0x00014668` | L1 |
| first-level load address | `0x10080` | L1 |
| first-level execution entry | **UNKNOWN** | — |
| first-level hand-off targets | with `signed16(word1 & 0xFFFE)` all three four-byte branches (`0x1017C`, `0x10250`, `0x10298`) reach `0x010100`, the retry loop | L2 |
| `0x10284` (`disps25`) | **decodes to `0x000008`** (sign in bit 0, 24-bit magnitude, `addr + (-mag & 0xFFFFFE)`, masked to 24 bits) | L2 |
| `0x000008` | `br 0x15AA` in `normal`, `br 0x1026` in `p2test` | L2 |
| hand-off chain | loader `0x10284` → `0x8` → `0x15AA`/`0x1026` → start-up → `0x1602` → `0x25F90` | **L3, static** |
| immediate tracking | a register value is invalidated by any write other than the `movw` that loaded it | L2 |
| `0x01000000` region | not present in any uploaded image | L1 |
| `CFG` bit 8 | cleared by the loader, set before its hand-off wait and by the second-level start-up | L2 |

## 9e. Offline state of the driver

| Fact | Value | Evidence |
|---|---|---|
| Probe-only diagnostics | `stage=0x23`, `mode=probe-only`, `resource_mask=0x3f`, `diag_valid=0`, `dma_prepared=0`, `dma_started=0`, `irq_spi=156/159`, `irq_intid=188/191`, `irq=-1` | CODE, OFFLINE, **HW-TEST (§9d)** |
| **Loadable module** (build tree) | 74 796 bytes, sha256 `cd5c05fb...6aff6` | HW-TEST |
| SDK-built module | 73 980 bytes, sha256 `b867b8c5...ad870` — rejected by the kernel (`struct module` size) | HW-TEST |
| Offline test suites | mock 40, TDM/DMA, dialog (incl. real firmware), bench 32, prepare-tree 13, prepare-image 10 | OFFLINE |
| checkpatch | 0 errors, 4 intentional warnings | OFFLINE |
| sparse | no diagnostics | OFFLINE |

## 9f. Bench-script fixes found by the hardware run

Two script defects only surfaced on the device and are fixed:

| Defect | Effect | Fix |
|---|---|---|
| `diff` listed as a required tool | pre-flight aborted on the slim initramfs, which has `cmp` but no `diff` | `diff` dropped from the requirement list; the diagnostic copy uses `cp` |
| `probe_only` parameter regex expected `probe_only:bool` | `modinfo` actually prints `probe_only (bool)`, so pre-flight rejected the correct module | regex accepts `[(]bool[)]` |

`bench/tests/run.sh` was updated to fake the real `modinfo` wording and is back
to **32 passed, 0 failed**.

## 10. What this document deliberately excludes

Everything that is a hypothesis, a plan, or reasoning about how we got here.
Those live in `fon-open-questions.md` (what is still unknown) and in the
historical documents, which are marked as such.
