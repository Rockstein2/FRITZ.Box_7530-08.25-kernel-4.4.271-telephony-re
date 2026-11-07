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
| **RUNTIME** | read from the real board over the serial console; no writes, no module load |

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

## 1a. Production router baseline (RckBox, 2026-11-07)

This workspace contains **one** FRITZ!Box 7530, hostname `RckBox`.  It is the
only unit available for the bench, so a RAM-only test would use it after
production service is moved to another router.  The NAND must stay untouched.

All rows below were read over `/dev/ttyUSB0` at 115200 8N1 and a root shell,
with read-only commands only.  No module was loaded and no flash write was
performed.

| Fact | Value | Evidence |
|---|---|---|
| Board | `AVM FRITZ!Box 7530`, compatible `avm,fritzbox-7530` | RUNTIME |
| Firmware | OpenWrt 25.12.6 `r33311-981c978eff` (official release) | RUNTIME |
| Kernel | 6.12.112, `#0 SMP Sat Oct 17 21:45:38 2026` | RUNTIME |
| Kernel command line | ` coherent_pool=4M` only; **no `root=`** | RUNTIME |
| Root filesystem | squashfs `/dev/ubiblock0_1`, read-only, mounted on `/rom` | RUNTIME |
| Overlay | UBIFS `/dev/ubi0_4`, mounted on `/overlay` (71.5 MiB, 16.6 MiB used) | RUNTIME |
| Console | `/dev/ttyUSB0`, 115200 8N1, root shell `root@RckBox:~#` | RUNTIME |
| `sysupgrade` | `/sbin/sysupgrade` present | RUNTIME |
| NAND health | 872 good PEBs, 0 bad, 0 corrupted, max erase counter 10 | RUNTIME |
| Recovery partitions | `urlader0` / `urlader1` present (`mtd5`/`mtd6`) | RUNTIME |

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
| `../../restore/openwrt-25.12.6-ipq40xx-generic-avm_fritzbox-7530-squashfs-sysupgrade.bin` | `011e020205fed455c79ee68ebb4d9ce43e6b05698bd99b05ebfc5c851f7ceb73` |
| `../../restore/version.buildinfo` | `r33311-981c978eff` (matches the board) |
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

The AVM board table declares GPIO40 as `OUT_ACTIVE_HIGH`.  Nothing in Linux
drives it, the pad is an input, and it reads low, which is consistent with
the SC14448 being **held in reset**.  Polarity at the chip is still
unverified (Q15).

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

## 9. Our driver — first hardware run

### 9a. Boot path proven on hardware (2026-11-07)

The probe-only initramfs was booted **into RAM over TFTP** on the real
FRITZ!Box 7530.  NAND was not written at any point.

| Fact | Value | Evidence |
|---|---|---|
| Bootloader | `U-Boot 2012.07 [local,r35279-c2a758b16a]`, EVA `1.11581` | RUNTIME |
| U-Boot environment | **`bad CRC, using default environment`** | RUNTIME |
| NAND | `Macronix MX30LF1G18AC`, 128 MiB, 872 good PEBs, 0 bad | RUNTIME |
| Recovery route | started from `(FRITZ7530) #`, `run tftpboot` | RUNTIME |
| U-Boot net settings | `serverip=192.168.1.70`, `ipaddr=192.168.1.1` (RAM only, no `saveenv`) | RUNTIME |
| TFTP | `Bytes transferred = 9129136` (matches the probe FIT exactly) | RUNTIME |
| Kernel process | `Run /init as init process` — initramfs, not NAND rootfs | RUNTIME |
| Shell after boot | `root@OpenWrt:~#` on `192.168.1.1`, SSH reachable | RUNTIME |
| USB storage | `usb-storage` + `uas` + SCSI load; stick appears as `sda1` | RUNTIME |

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

### 9c. Stage A result (passive, no module)

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

Evidence: `../../restore/stage-a/stage-a.tar.gz` and the console boot log.

### 9d. Stage B result (probe-only, verified)

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

Evidence: `../../restore/stage-b/stage-b-2/`.

### 9d-2. Stage C0 on hardware (2026-11-07, passive)

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

The pinmux state is the decisive passive result: no GPIO in the PCM group is
muxed to `i2s_rx`/`i2s_tx`/`i2s_td`, so **the ADSS pads are not connected to
the PCM pins in the current configuration**.  Whether the SC14448 toggles
them anyway cannot be answered by software.

Evidence: `../../restore/stage-c0-final/stage-c0g/`, archive sha256
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

### 9d-4. Probe-only still side-effect free with the C1 links (2026-11-07)

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

Evidence: `../../restore/stage-b-c1/stage-b-c1/`.

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
evidence `../../restore/stage-b-c1b/stage-b-c1b/`.

### 9d-7. Stage C1: the ADSS block answers on the bus (2026-11-07)

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

### 9d-8. Stage C2: the ADSS accepts the FON configuration (2026-11-07)

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

**Proven:**

| Claim | Evidence |
|---|---|
| `0xFF6006` is written `0x80`, read, then written `0` | disassembly of `0x2558`-`0x25B8` |
| `0x80` is `BIT(7)` | by value |
| it is a trigger, not a format register | set and cleared nine instructions later; no rate/word-size/master field exists in the function |
| the read-back is discarded | `movw $0x400:m,r2` overwrites the value at `0x25ac` |
| the block at `0x000000` is data | linear disassembly gives `illegal` almost everywhere |
| no direct branch targets `0x2558` or `0x24F8` | whole-image search |
| no slot-5 / FON command handler found | bounded search over all immediate peripheral references and both large code blocks |

**Not proven:**

| Question | Why |
|---|---|
| where the `0x2570` / `0x257E` calls go | the two candidate interpretations of `objdump`'s printed target give different answers, and neither survives every test (see the call-graph document) |
| who calls the `0x24F8` selector | no direct branch, no pointer table found |
| what `BIT(7)` of `0xFF6006` does | no code reads it back |
| whether `0xFF600E` is used | not found as an immediate; indirect access not excluded |

Branch targets in the firmware analysis are therefore **provisional**.
Instruction bytes, instruction boundaries and all immediate constants are
unaffected.

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
| `0x257E` | `0x24F8` | the enclosing block itself — **recursive re-entry** |

**Caller of `0x24F8`:** none outside the block.  No `bal` targets it, no
aligned 16-bit word equals it, and the two 3-byte matches (`0x318D`,
`0x287C7`) lie inside `movb $0x25:m,rN` instructions, so they are not table
entries.

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
       -> 0x25FAA -> 0x2558 -> 0x257E -> 0x24F8 (recursion)
```

**`0x25F90` is a PCM bring-up routine:**

```text
25f92  movd $0x937c:l,(r8,r7)
25f98  storw $0x1:s,0x0:s(r8,r7)     ; counter = 1
25f9a  movw $0x1001:m,r2             ; fill value
25f9e  bal  -> 0x25BA                ; table[base + index*2] = value
25fa4  cmpw $0x200:m,r0
25fa8  bhi  *-0x25f9a                ; 512 words at 0x01000000
25faa  bal  -> 0x2558                ; pulse 0xFF6006
25fae  loadw 0xf6002:m,r0
25fb4  bne  *-0x25fae                ; wait for readiness == 1
```

So the previous iteration's "only recursion, no caller" conclusion was
**incomplete**: the caller lives in the `0x25Fxx` block that the old
per-run CFG could not reach.

What is proven and what is not:

| Claim | Status |
|---|---|
| `0x24F8` is reachable from top-level code | **proven** (CFG path above) |
| `0x257E` re-enters with the high byte of its argument | **proven** |
| there is no external caller of `0x24F8` other than `0x257E` | **proven** |
| `0x25F90` fills 512 words at `0x01000000` with `0x1001` | **proven** |
| it then pulses `0xFF6006` and polls `0xF6002` for `1` | **proven** |
| the buffer is the PCM buffer | **not proven** — `0x01000000` is in no loaded run |
| `0x1001` has a known field layout | **not proven** |

Statistics (second-level image): 9 blocks, 19 570 decoded, 0 verified
entries, 404 candidate entries, 8 178 reachable, 1 490 direct calls, 376
cross-block calls, 0 resolved indirect edges, 2 706 unresolved, 204
invalid targets.

`p2test` reproduces the same constants at shifted addresses
(`0x1001` at `0x26750`, poll at `0x26764`, `0xFF6006` at `0x1E3E`), so the
bring-up is the same code in both builds.

## 9e. Offline state of the driver

| Fact | Value | Evidence |
|---|---|---|
| Probe-only diagnostics | `stage=0x23`, `mode=probe-only`, `resource_mask=0x3f`, `diag_valid=0`, `dma_prepared=0`, `dma_started=0`, `irq_spi=156/159`, `irq_intid=188/191`, `irq=-1` | CODE, OFFLINE, **RUNTIME (9d)** |
| **Loadable module** (build tree) | 74 796 bytes, sha256 `cd5c05fb...6aff6` | RUNTIME |
| SDK-built module | 73 980 bytes, sha256 `b867b8c5...ad870` — rejected by the kernel (`struct module` size) | RUNTIME |
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
