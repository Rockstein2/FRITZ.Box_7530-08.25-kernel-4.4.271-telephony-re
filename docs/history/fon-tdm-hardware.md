# FON TDM/ADSS hardware parameters

> **Status: historical analysis.**
> This document records the reasoning and evidence as of the date it was
> written.  Some of its `UNKNOWN` / `UNVERIFIED` markers have since been
> answered.
> - Current confirmed facts: `../fon-known-facts.md`
> - Current open questions: `../fon-open-questions.md`
> - This file is kept for the reasoning trail, not as a status report.

Status: **transport recovered and documented; not hardware-validated**

This document reconstructs the QCA IPQ4019 ADSS/TDM/MBOX side of the
FRITZ!Box 7530 analog FON path.  It is the hardware reference for the minimal
diagnostic driver in `src/fon-driver/`.

Evidence is taken from:

- AVM GPL source `sources/kernel/linux/sound/soc/qcom/ipq/ipq-adss-avm.c`,
  `ipq-avm.c`, `ipq-adss.h` (FRITZ!OS 08.25, Linux 4.4.271);
- AVM board DTS `Fritz_Box_HW236.dtsi` and
  `qcom-ipq4019-audio.dtsi`;
- static disassembly of the local `modules/ubik2/pcmlink.ko`
  (`../../reports/pcmlink.disasm.txt`, `../../reports/pcmlink-sharedmem.txt`);
- the stock init script `reference/init.d/E41-capi`.

No hardware test was performed.  Registers marked "read-only" in the driver
are not written by it.

---

## 1. Board wiring and the two QCA audio paths

The 7530 DTS enables both the `tdm` and `pcm` descriptions:

```text
tdm@0   compatible = "qca,ipq4019-tdm"
        dma-tx-channel = <MBOX0_TX_ID>
        dma-rx-channel = <MBOX3_RX_ID>
        stereo-tx-port = <STEREO0_ID>
        stereo-rx-port = <STEREO3_ID>

pcm@7704000 compatible = "qca,ipq4019-pcm"
        dma-tx-channel = <MBOX3_TX_ID>
        dma-rx-channel = <MBOX0_RX_ID>
        stereo-tx-port = <STEREO3_ID>
        stereo-rx-port = <STEREO0_ID>
```

`pcmlink.ko` contains the `ipq40xxtdm_*` backend and is loaded with
`abmode=1` (SLIC1, no FPGA/FPGA2/PEF/spitdm bits).  Therefore the FON path
uses the **TDM** description, not the separate PCM description:

```text
FON playback (IPQ -> SC14448): MBOX0, STEREO0
FON capture  (SC14448 -> IPQ): MBOX3, STEREO3
```

The `pcm` node uses the opposite channel assignment.  Runtime confirmation is
still required because both nodes are enabled by the board DTS and neither
driver is part of mainline Linux.

The physical 16-bit slot-5 control word is the same in both descriptions, but
the driver must not select the PCM node by accident.  The DT binding for this
driver exposes named resources so the integrator makes that choice explicit.

---

## 2. Confirmed frame parameters

| Parameter | Value | Evidence and confidence |
|---|---|---|
| Frame rate | 8000 frames/s | `tdm_if_adss_dma_init()` documents 4 ms = 32 frames; `fs_per_dma = 32`; AVM TDM code uses 8000 in the BCLK formula. High. |
| Physical slots per frame | 8 | `ipq40xxtdm_linkinit` derives `slot_size = 8` from the six-codec-slot configuration (`6 < 8`), calls `tdm_if_config_init(8, 1, 1, master)`, and returns 8. `TxDMA`/`PutRxDMA` use that value as the frame stride (`8 * 2 = 16` bytes). High. |
| Logical codec slots | 6 | AVM boot/configuration reports `Codecslots=6 Slics=1 DECT=4`; `tdm_dma+0x08` is 6. High. |
| Slot width | 16 bit | `adss_config_tdm()` selects `STEREOn_CONFIG_DATA_WORD_SIZE(1)`, I2S 16-bit and MIC 16-bit. High. |
| Bytes per frame | 16 | 8 slots × 2 bytes. High. |
| Frame sync | 8 kHz; AVM programs sync-number field 0 | `adss_glb_tdm_ctrl_sync_num(0, ...)`; the exact FSYNC high-time/duty is a hardware/SC14448 property and is not proven. Medium-high. |
| Bit clock, nominal | 1.024 MHz | `8 slots × 16 bit × 8000 = 1.024 MHz`; the AVM source's master formula is `slots * 8 * sizeof(short) * 8000`. In slave mode the actual clock comes from the SC14448. High for the formula, medium for the actual measured value. |
| Master clock, nominal | 4.096 MHz | AVM master path uses `mclk = bclk * 4`. In slave mode the pin is an input. High for the formula, not measured. |
| TDM role | **IPQ4019/ADSS is slave; SC14448 supplies BCLK/FSC** | `tdm_dma+0x18 = 0`; `ipq40xxtdm_linkinit` then sets delays to 1 and passes `master=0`; board GPIO data marks FSC/DCL/MCL as inputs and DI as input/DO as output; stock `pcmlink abmode=1` does not set `abmode` bit 14. High, but still to be confirmed with a scope. |
| Data delay | RX = 1, TX = 1 bit clock | `ipq40xxtdm_linkinit` sets both delay fields to 1 when `master=0`; `tdm_if_config_init(slots, 1, 1, 0)` sets `GLB_TDM_CTRL_RX_DELAY`/`TX_DELAY`. High. |
| Word order in DMA memory | 16-bit little-endian words, linear slot order | AVM uses native ARM `strh`/`ldrh`/`u16` accesses; no `RXD_16BIT_SWAP`/`RXD_END_SWAP` bits are set by the code path. High for Linux-side memory representation. |
| Bit order on the wire | 16-bit TDM; exact SC14448 bit-order setting is not independently documented | `adss_config_tdm` only selects 16-bit mode. The SC14448 PCM+ configuration is in its firmware and is not recovered. Medium. |
| DMA frames per buffer | 32 frames = 4 ms | `fs_per_dma=32`; `tdm_if_adss_dma_init()` comment. High. |
| DMA buffer size | 512 bytes per ping-pong buffer | `8 slots × 2 bytes × 32 = 512`. High. |
| DMA descriptors | 16 | `ipq40xxtdm_linkinit` stores 16 on the stack for `tdm_if_dma_init`. High. |
| DMA descriptor size | 156 bytes (`0x9c`) on IPQ4019; stride is `L1_CACHE_ALIGN(156)` (192 bytes with 64-byte cache lines) | `struct _mbox_desc` includes `vuc_dword[36]`; `mbox_get_desc_size()` returns `L1_CACHE_ALIGN(sizeof(desc[0]))` on IPQ4019. High. |
| DMA address width | 28 bits | `mbox_get_mask()` returns `DMA_BIT_MASK(28)` on IPQ4019; descriptor and buffer addresses are masked. High. |

### 2.1 Why eight physical slots, despite six codec slots

The six codec slots are an AVM logical allocation.  The QCA hardware channel
number field is programmed with `slots - 1`:```text
ADSS_GLB_TDM_CTRL_REG:
  TX channel number = 7  (8 slots)
  RX channel number = 7  (8 slots)
  TX sync number    = 0
  RX sync number    = 0
  TX delay          = 1
  RX delay          = 1
```

This is done by `__tdm_if_config_init()` in `ipq-adss-avm.c`; the TDM
channel-number helper documents "real value = val + 1".  The ADSS API comment
also says `slots` was only tested at 8.

`TxDMA` obtains the frame stride from `TDMPriv+0x4b8`; `ipq40xxtdm_linkinit`
returns 8 (the selected hardware slot count), and `TxDMA` writes one frame
every `8 * 2 = 16` bytes.  `PutRxDMA` uses the same stride.

The `tdm_dma` object is not a bare scalar table: `.data+0xb0` contains
`+0x0=0xc0`, `+0x4=1`, `+0x8=6`, `+0xc=PutRxDMA`, `+0x10=TxDMA`,
`+0x18=0`.  The two non-zero callback fields are why
`ipq40xxtdm_linkinit` accepts the configuration; the `.rel.data` relocations
prove the callback identities.  The `+0x18` field is the master flag.

---

## 3. Proof that TX byte `0x0a` is physical TDM slot 5

This is not merely "the sixth word of an internal Linux buffer".

`TxDMA` (`pcmlink.ko @0x9710`) does the following for each frame:

```text
TX buffer base = B
B + 0x00 <- 0x0000
B + 0x02 <- 0xfefe
B + 0x04 <- 0xfefe
B + 0x06 <- 0xfefe
B + 0x08 <- 0x5555 or 0x0000
B + 0x0a <- 16-bit FON control word
B += 16              ; next frame
```

The increment is the hardware frame size: `TDMPriv+0x4b8 = 8` slots, and
`8 slots × 2 bytes = 16 bytes`.  Therefore `0x0a` is byte 10 of a frame whose
slot boundaries start at 0, 2, 4, ...:

```text
slot 0 = 0x00
slot 1 = 0x02
slot 2 = 0x04
slot 3 = 0x06
slot 4 = 0x08
slot 5 = 0x0a  <-- FON control/status word
slot 6 = 0x0c
slot 7 = 0x0e
```

`PutRxDMA` (`@0x9a60`) reads the status word from `frame + 0x0a` and advances
by the same 16-byte stride.  This confirms a physical slot-5 word, not just a
DMA-structure word, **provided the ADSS channel number is 8**.  That condition
is independently checked at runtime by the diagnostic driver by reading
`ADSS_GLB_TDM_CTRL_REG` and comparing its TX/RX channel numbers with the DT
slot count.

If a future board variant uses 16 physical slots, byte `0x0a` is still
16-bit slot 5; only the frame size and the positions of later slots change.

### 3.1 The fixed header values

`0x0000`, `0xfefe` (slots 1-3) and `0x5555` (slot 4) are written by
`TxDMA`.  The `0x5555` word is suppressed when `TDMPriv+0x808` is nonzero.
These are **TDM frame/idle markers**, not the SC14448 UART boot handshake.
The UART loader uses completely different values and a different transport
(STX `0x02`, SOH `0x01`, ACK `0x06`, NACK `0x15`, `HELLO DCX81`; see
`fon-dialog-dependency.md`).

The precise SC14448 semantic meaning of `0xfefe`/`0x5555` is **not proven**.
The driver preserves the proven Linux-side layout but does not claim to
interpret them.

`build_slic_ctrl` (`@0x8f68`) may overwrite the control slot after the fixed
header is written.  The `0x4000` marker is present for normal line control;
`0x8000 | half_period` selects the ring path.  See
`fon-pcmlink-register-path.md` for the call chain.

---

## 4. ADSS register map used by the GPL source

All addresses are physical IPQ4019 addresses from the DTS.  The driver maps
them from DT resources; it does not hardcode virtual addresses.

### 4.1 Global ADSS block

Base: `0x07700000`, resource size from DT (AVM maps at least `0x34` bytes;
the IPQ4019 range in `ipq-adss.h` is `0x20000`).

| Offset | Register | Bits used by AVM | Initialization / diagnostic meaning |
|---|---|---|---|
| `0x00` | `ADSS_GLB_PCM_RST_REG` | `GLB_PCM_RST_CTRL(x)` bit 0 | Not written by the TDM path analyzed; do not use as a generic reset. |
| `0x0c` | `ADSS_GLB_PCM_MBOX_CTRL_REG` | unknown | Not written by `ipq-adss-avm.c`; semantics unknown. Driver only maps/diagnoses if described in DT. |
| `0x10` | `ADSS_GLB_CHIP_CTRL_I2S_REG` | bit 0 interface enable | Audio probe writes interface enable (and B1K separately). |
| `0x14` | `ADSS_GLB_I2S_RST_REG` | `0xF` on IPQ4019 | `adss_glb_i2s_reset()` writes `0xF`, then `0`. This resets MBOX0/I2S0/MBOX3/I2S3 groups. |
| `0x18` | `ADSS_GLB_CLK_I2S_CTRL_REG` | OE bits 16,17,27,28 | Slave: clear all four (external pad clocks). Master: set TX/RX BCLK/MCLK output enables. |
| `0x1c` | `ADSS_GLB_TDM_CTRL_REG` | bits 3:0 TX channel-1; 8:4 TX sync; 19:16 RX channel-1; 24:20 RX sync; bit25 TX delay; bit26 RX delay | `slots-1 = 7`, sync 0, delays 1 for the 7530 slave configuration. |
| `0x30` | `ADSS_GLB_AUDIO_MODE_REG` | bits 0,2 = TDM; bit28 B1K | `adss_glb_tdm_mode()` sets TX/RX TDM bits; audio probe sets B1K. |

The driver reads `0x1c`, `0x30`, `0x18`, `0x14` as diagnostics and never
writes them.

### 4.2 Stereo/TDM port block

STEREO0 base: `0x07709000`; STEREO3 base: `0x0770f000`.  Each is a 4 KiB
region in the DTS.

`ADSS_STEREOn_STEREO0_CONFIG_REG` (offset `0x00`):

| Field | Value in 16-bit TDM mode | Meaning |
|---|---|---|
| `DATA_WORD_SIZE(1)` bits 13:12 | `1` | 16-bit data words |
| `I2S_WORD_SIZE_16` bit 11 | `0` | 16-bit I2S word |
| `MIC_WORD_SIZE_16` bit 16 | `0` | 16-bit microphone word |
| `MASTER` bit 8 | `0` for 7530 slave path | Port is clock slave |
| `ENABLE` bit 21 | set only by the DMA start path | Port enable |
| `MCK_SEL` bit 10 | `1` for external pad clock | Select external MCLK |
| `NO_I2S_DELAY` bit 18 | not set by AVM's TDM path | Delay behavior |
| `PCM_SWAP` bit 17 | not set | No PCM swap |
| `MIC_SWAP` bit 24 | not set | No mic swap |

The driver reads this register (`stereo_tx_cfg`, `stereo_rx_cfg`) but does
not enable either port.

### 4.3 MBOX blocks and the direction inversion

Physical bases from the 7530 DTS:

```text
MBOX0 0x07708000   IRQ 156, used by TDM playback (IPQ -> SC14448)
MBOX3 0x0770e000   IRQ 159, used by TDM capture  (SC14448 -> IPQ)
```

Register offsets (per MBOX):

| Offset | Register | Direction use |
|---|---|---|
| `0x10` | `MBOX_DMA_POLICY` | policy, 28-bit descriptor address, FIFO threshold |
| `0x18` | `DMA_RX_DESCRIPTOR_BASE` | **playback** descriptor base (DMA engine RX view) |
| `0x1c` | `DMA_RX_CONTROL` | playback START/STOP/RESUME |
| `0x20` | `DMA_TX_DESCRIPTOR_BASE` | **capture** descriptor base (DMA engine TX view) |
| `0x24` | `DMA_TX_CONTROL` | capture START/STOP/RESUME |
| `0x44` | `MBOX_INT_STATUS` | TX complete bit 6, RX complete bit 10 |
| `0x4c` | `MBOX_INT_ENABLE` | corresponding enable bits |
| `0x58` | `MBOX_FIFO_RESET` | TX init bit 0, RX init bit 2 |

AVM's `mbox_dma_start()` confirms the inversion: for `PLAYBACK` it writes
`ADSS_MBOXn_DMA_RX_CONTROL_START`, and for `CAPTURE` it writes
`ADSS_MBOXn_DMA_TX_CONTROL_START`.  This is the DMA engine's view, not the
audio direction name.

The diagnostic driver prepares descriptors only.  It does not program the
policy/control registers and does not enable interrupts.

---

## 5. DMA ring format

AVM's `struct _mbox_desc`:

```c
struct _mbox_desc {
    unsigned int length : 12;  /* bits 11:0  */
    unsigned int size   : 12;  /* bits 23:12 */
    unsigned int vuc    : 1;   /* bit 24     */
    unsigned int ei     : 1;   /* bit 25     */
    unsigned int rsvd1  : 4;   /* bits 29:26 */
    unsigned int EOM    : 1;   /* bit 30     */
    unsigned int OWN    : 1;   /* bit 31     */
    unsigned int BufPtr;
    unsigned int NextPtr;
    unsigned int vuc_dword[36]; /* reserved on IPQ4019 */
};
```

Observable values in `mbox_dma_prepare_desc()`:

```text
OWN     = 1
ei      = 1
rsvd1   = 0
EOM     = 0
BufPtr  = 28-bit physical address of ping-pong buffer (i & 1)
NextPtr = 28-bit physical address of next descriptor
size    = length = DMA buffer size (512 bytes for FON geometry)
```

`mbox_dma_init()` computes:

```text
DMABufferSize      = slots * 2 * fs_per_dma = 8 * 2 * 32 = 512
DescriptorPoolSize = L1_CACHE_ALIGN(16 * sizeof(desc)) = 16 * 192 = 3072
AlignedBufferSize  = L1_CACHE_ALIGN(512) = 512
DMAPoolSize        = 3072 + 2 * 512 = 4096
```

There are two distinct sizes:

- `sizeof(struct _mbox_desc)` = **156 bytes**; the `vuc_dword[36]` tail is
  part of the IPQ4019 descriptor, not removable padding.
- `mbox_get_desc_size()` = `L1_CACHE_ALIGN(156)` = **192 bytes** with the
  64-byte A7 cache line.  `ipq_desc_ptr()` and `NextPtr` use this stride;
  bytes 156..191 are alignment padding between descriptors.

The diagnostic driver enforces this with `_Static_assert` for the 156-byte
structure and `FON_DMA_DESC_STRIDE = ALIGN(sizeof(...), L1_CACHE_BYTES)`.
It does not hard-code 192 as a universal hardware constant; the target cache
line determines the stride.

The vendor places descriptors and both ping-pong buffers in one coherent
pool; the diagnostic driver uses separate coherent allocations, checks that
every address fits the 28-bit ADSS mask, and checks buffer cache-line
alignment.  Descriptors and buffers are obtained with
`dma_alloc_coherent()`; the physical handles are programmed directly, never
ordinary virtual addresses.  After filling the ring the driver issues
`dma_wmb()`; there is no explicit cache flush because the coherent allocation
is already DMA-coherent.  This is a deliberate 6.12 replacement for the
vendor's `kzalloc`/`virt_to_phys` + `dmac_flush_range` pattern and still needs
hardware validation.

---

## 6. Clock, reset, pinctrl and interrupt facts

### 6.1 Clocks

The 7530 DTS gives the TDM node four clocks:

```text
audio_tx_bclk = <&adcc ADCC_TXB_CLK_SRC>
audio_tx_mclk = <&adcc ADCC_TXM_CLK_SRC>
audio_rx_bclk = <&adcc ADCC_RXB_CLK_SRC>
audio_rx_mclk = <&adcc ADCC_RXM_CLK_SRC>
```

`__tdm_if_config_init()` behaves differently by role:

- `master=1`: computes `bclk = slots * 8 * sizeof(short) * 8000`, `mclk =
  bclk * 4`, sets external clock to 0, and programs the ADCC clocks.
- `master=0`: uses dummy rates 254 (BCLK pad input) and 255 (MCLK pad input),
  `extclk = 1`; the clock framework selects the external pad clocks.

The slave path is the one matching `tdm_dma+0x18 = 0`, GPIO directions and
`pcmlink abmode=1`.

### 6.2 Reset

The audio node has `resets = <&gcc AUDIO_BLK_ARES>`.  AVM's audio probe:

```text
reset_control_assert(audio_blk_rst)
usleep_range(20000, 24000)
reset_control_deassert(audio_blk_rst)
```

The TDM reset register `0x14` is separately written `0xf` then `0`.

The diagnostic driver obtains the optional reset control but **does not
assert it** during probe.  No unknown reset is toggled automatically.

### 6.3 Pinctrl/GPIO

The board hardware-config table contains:

```text
gpio_avm_pcmlink_fsc     GPIO22  input active low  pinmux2
gpio_avm_pcmlink_fsc_2   GPIO26  input active low  pinmux3
gpio_avm_pcmlink_dcl     GPIO21  input active low  pinmux2
gpio_avm_pcmlink_dcl_2   GPIO25  input active low  pinmux3
gpio_avm_pcmlink_mcl     GPIO20  input active low  pinmux2
gpio_avm_pcmlink_mcl_2   GPIO24  input active low  pinmux3
gpio_avm_pcmlink_di      GPIO23  input active low  pinmux3
gpio_avm_pcmlink_do      GPIO27  output active low pinmux3
```

The active-low marking is a board-table convention; it does **not** by itself
prove signal polarity.  The important structural fact is that FSC, DCL, MCL
and DI are described as inputs and DO as an output, consistent with the
IPQ4019 being the TDM slave.

The driver calls `devm_pinctrl_get()` but does not select a state.  A future
integration must provide the correct `default`/`audio_slave` pinctrl state in
DT and validate polarity.

### 6.4 Interrupts

The MBOX nodes have interrupts:

```text
MBOX0 IRQ 156
MBOX1 IRQ 157
MBOX2 IRQ 158
MBOX3 IRQ 159
MBOX4 IRQ 163
```

AVM can use a shared RX IRQ (`only_rxirq`) or separate interrupts.  The
completion bits are TX bit 6 and RX bit 10 in `MBOX_INT_STATUS`.  The
diagnostic driver records the optional IRQ but does not request it and does
not start DMA.

### 6.5 MMIO-read prerequisite

The known AVM audio probe order is:

```text
map ADSS global region
get/reset AUDIO_BLK_ARES
assert reset
usleep(20000..24000)
deassert reset
enable I2S interface (0x10 bit 0)
set B1K (0x30 bit 28)
```

The TDM node separately owns the four ADCC BCLK/MCLK clocks.  The AVM source
does **not** prove that a read of the ADSS global registers is safe while the
AHB/peripheral clock is gated.  Mainline/OpenWrt 6.12 also lacks the AVM ADCC
provider, so this driver deliberately does not toggle the reset or enable any
clock during probe.

The diagnostic driver therefore:

- does not read MMIO during probe;
- leaves `diag_refresh` disabled unless `allow_mmio_reads=1`;
- requires the operator to prove the AHB/peripheral clock and reset state
  before the explicit refresh;
- never enables clocks, asserts reset, or starts TDM as a side effect of a
  read.

This is a safety limitation, not missing register knowledge.  The first
hardware test must establish the clock/reset state independently, preferably
with the same owner that enabled the register block in the stock system.

---

## 7. What the GPL source does not provide

The following are **not** recovered from GPL source and remain blockers for a
real FON driver:

1. **SC14448 slot-5 semantics.**  The Linux side packs a 16-bit control word;
   which bits select hook/ring/line-feed/ADC/PWM inside the SC14448 is not
   documented.
2. **SC14448 firmware dependence.**  See
   `fon-dialog-dependency.md`.  The GPL TDM code assumes the external
   device is already generating clocks and responding.
3. **Exact bit order and framing on the wire.**  The ADSS side is 16-bit TDM,
   but the SC14448 PCM+ configuration is firmware-controlled.
4. **Discrete line/ring circuit.**  There is no separate SLIC IC.  The
   LM324/BCP53-16 high-voltage topology and safe test voltages are not
   recovered.
5. **Runtime confirmation of TDM vs PCM node.**  Both are enabled in the
   board DTS; `pcmlink` uses the TDM backend, but the target DT must select
   the intended path.
6. **Meaning of `tdm_dma+0x00/+0x04/+0x08`.**  The fields are a 6-codec-slot
   configuration used to select the 8-slot ADSS geometry; the exact vendor
   names of `0xc0`, `1` and `6` are not needed for the recovered stride.
   `+0x0c/+0x10` are resolved as the `PutRxDMA`/`TxDMA` callback pointers.

A future read-only trace should capture `ADSS_GLB_TDM_CTRL_REG` and the
MBOX TX/RX buffers during hook and ring transitions, and compare them with
`pcmlink_ul_writeregister(0x40/0x44/0x48/0x4c/0x50)` traces.

---

## 8. Primary source locations

The following line numbers refer to the AVM GPL 08.25 source tree
(`sources/kernel/linux/...`) and the local disassembly reports:

| Fact | Source |
|---|---|
| TDM register offsets and bit names | `sound/soc/qcom/ipq/ipq-adss.h:33-80` |
| 16-bit TDM mode, reset mask, master/enable/extclk bits | `sound/soc/qcom/ipq/ipq-adss-avm.c:2008-2040` |
| config fields, BCLK/MCLK formula, slave dummy rates, register sequence | `sound/soc/qcom/ipq/ipq-adss-avm.c:2042-2098` |
| `tdm_if_adss_config_init()` / exported wrapper | `ipq-adss-avm.c:2110-2124`; `ipq-avm.c:30-37` |
| DMA buffer size, descriptor pool, 28-bit mask | `ipq-adss-avm.c:992-1060`, `668-696` |
| descriptor fill values | `ipq-adss-avm.c:1314-1348` |
| MBOX policy and play/capture inversion | `ipq-adss-avm.c:1352-1416` |
| start order and 125 µs gap | `ipq-adss-avm.c:2234-2268` |
| audio block reset | `ipq-adss-avm.c:554-580` |
| `tdm` DTS channel mapping and clocks | `arch/arm/boot/dts/qcom-ipq4019-audio.dtsi:189-204` |
| board enable and GPIO table | `arch/arm/boot/dts/Fritz_Box_HW236.dtsi:278-317`, `344-383` |
| `TxDMA` header/stride/slot-5 write | `pcmlink.ko @0x9710`, disassembly lines around `0x98b8-0x98e0` |
| `PutRxDMA` slot-5 read and stride | `pcmlink.ko @0x9a60`, disassembly around `0x9b38-0x9b98` |
| `ipq40xxtdm_linkinit` slot count/master/delays | `pcmlink.ko @0x9e40`, disassembly `0x9e90-0xa008` |
| `tdm_dma` defaults `.data+0xb0`: `+0=0xc0`, `+4=1`, `+8=6`, `+0xc=PutRxDMA`, `+0x10=TxDMA`, `+0x18=0` | ELF `.data` dump and `.rel.data` / `../../reports/pcmlink.disasm.txt` |
| stock `abmode=1` | `reference/init.d/E41-capi:5` |

`tdm_dma+0x18` is the master flag read by `ipq40xxtdm_linkinit`.  With the
stock `abmode=1`, `fpgadata_init` does not set its `0x4000` master bit, so the
flag remains zero and the ADSS is configured as a slave.

---

## 9. Driver diagnostic path

`src/fon-driver/fon_hw.c` implements only the safe part of this document.
The default `probe_only=1` mode does not map or acquire any hardware resource:

1. platform device probe;
2. DT named MMIO resources (`adss`, `pcm`, `mbox_tx`, `mbox_rx`,
   `stereo_tx`, `stereo_rx`), optional clocks/reset/pinctrl/IRQ;
3. **no MMIO access during probe**; cached diagnostics are filled only by an
   explicit `diag_refresh` after `allow_mmio_reads=1` and an independent
   clock/reset check;
4. comparison of the DT slot count with the TX/RX channel fields in
   `ADSS_GLB_TDM_CTRL_REG` after that refresh;
5. explicit `dma_prepare` sysfs action that allocates and fills the ring but
   does not write any hardware register;
6. `dma_start` refuses to run unless both module parameters are explicitly
   enabled, and currently returns `-EOPNOTSUPP` because the remaining
   hardware semantics are not validated.

The first safe hardware test is described in
`fon-linux612-port.md` and the final report.  It is read-only: boot the
driver without `dma_prepare`/`dma_start`, inspect the diagnostics, and only
then decide whether to proceed.

---

## 10. Confidence summary

| Claim | Confidence |
|---|---|
| 8 kHz, 8 physical slots, 16-bit, 16-byte frame | high (source + disassembly) |
| Slot 5 is at byte `0x0a` in each frame | high |
| MBOX0 TX / MBOX3 RX for the TDM path | high (DTS + `pcmlink` backend) |
| 512-byte ping-pong buffers, 32 frames, 16 descriptors | high |
| 28-bit DMA addresses | high |
| 16-bit little-endian Linux memory layout | high |
| IPQ4019 is TDM slave; SC14448 supplies clocks | high, not scope-confirmed |
| SC14448 firmware required for FON behavior | high from boot flow, not hardware-proven |
| Exact SC14448 control/status bits | unknown |
| Exact line/ring voltages and topology | unknown |
