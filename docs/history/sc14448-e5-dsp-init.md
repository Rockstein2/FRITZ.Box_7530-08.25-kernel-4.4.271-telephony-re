# E5-A — Gen2DSP initialization evidence

> **Status: historical analysis; current summary is `../sc14448-e5-summary.md`.**
> All findings are static, from SHA256-checked normal and p2test images.
> No hardware was touched (STRICTLY OFFLINE; K1/K2 NO-GO). Register names
> are **SC14480 analogies**, never a proven SC14448 map.

Report: `tools/reports/cr16-e5-dsp-registers.json`,
`tools/reports/cr16-e5-dsp-init.json`; analyzer:
`tools/cr16_audio_architecture.py`.

## Base cell and guard

Both images hold `[0xD6] = 0x01027F80` (bytes `80 7f 02 01`) and the DSP
init function itself checks the base before using it:

| Image | Guard | Skip | Init entry |
|---|---|---|---|
| normal | `0x133A cmpd $0x1027f80:l,(r1,r0)` | `0x1340 bne` to `popret` | `0x1330` |
| p2test | `0x0DB0 cmpd $0x1027f80:l,(r1,r0)` | `0x0DB6 bne` to `popret` | `0x0DA6` |

Every DSP-window access is `[0xD6]+offset` register-pair addressing; the
pair is re-loaded from `[0xD6]` after calls, so external writers of the
cell are not excluded (recorded as unresolved).

## Verified writes, per function

`dsp_init` (normal `0x1330` / p2test `0x0DA6`), callers `0x1462`/`0x0ED8`
(which pass `r2=1`, so the `beq0b` never fires and `0x80` is stored):

| Offset | Effective | Operation | Value | SC14480 name (analogy) |
|---|---|---|---|---|
| — | `0x00FF6006` | `storw r2` | `0x0080` | DIP_CTRL_REG bit7 URST=1 (stop DIP) |
| `+0x50` | `0x01027FD0` | `cbitw $2` | DSP_EN=0 | DSP_CTRL_REG (power down) |
| — | `0x00FF5808` | `orw $3` | AD_PD=1, DA_PD=1 | CODEC_ADDA_REG (converters down) |
| `+0x58` | `0x01027FD8` | `storw 0xFFFF` | clear all vectors | DSP_INT_REG |
| — | `0x00FF4004` | `storw $0` | all codec/PCM clocks off | CLK_CODEC_REG |
| `+0x54` | `0x01027FD4` | `storw` | `0x7980` | DSP_PC_START_REG |

`dsp_cfg` (normal `0x1856` / p2test `0x12D8`):

| Offset | Effective | Value | Name (analogy) |
|---|---|---|---|
| `+0x02` | `0x01027F82` | `0x0000` (all syncs 8 kHz) | DSP_MAIN_SYNC1_REG |
| `+0x5C` | `0x01027FDC` | `0x0773` | DSP_INT_PRIO1_REG |
| `+0x3C` | `0x01027FBC` | `0x0400` | DSP_MAIN_CTRL_REG (DIP-synced start) |
| — | `0x00FF4000` | `sbitw $7` | CLK_AMBA_REG |
| `+0x50` | `0x01027FD0` | `or 0xC`, then bit8 | DSP_CTRL: CLK_EN|EN, DBG_EN |
| — | *(helper call)* | `r2=0x7C00` | target `0x182E`/`0x12B0` **not on an instruction boundary; unresolved** |

`enable` (normal `0x190E` / p2test `0x1390`), reached from main via
`0x3A34→0x1A0A→0x1A4A` / `0x27152→0x1440→0x1480`:

| Offset | Effective | Value | Name (analogy) |
|---|---|---|---|
| — | `0x00FF5404` | `or 0x30` | INT_PRIO0_REG |
| — | `0x00FF5402` | `0x2000` | RESET_INT_PENDING_REG |
| `+0x5A` | `0x01027FDA` | `or 0x803C` | DSP_INT_MASK_REG |
| — | `0x00FF4006` | `0x0009` (CLK_DSP_EN, div 1) | CLK_DSP_REG |
| `+0x50` | `0x01027FD0` | `sbitw $2` | DSP_CTRL DSP_EN=1 |
| — | `0x00FF5808` | `and 0x7FFC` | CODEC AD/DA on |
| — | `0x00FF5804` | `cbitw $4` | VREF_INIT=0 (post precharge) |
| `+0x3C` | `0x01027FBC` | `0x0400` | DSP_MAIN_CTRL_REG |
| `+0x50` | `0x01027FD0` | `cbitw $3` | DSP_CLK_EN gated after bring-up |

`clk` (normal `0x1468` / p2test `0x0EE4`) writes `0x00FF600E` bit8
(DIP_CTRL2 SLOTCNT_RES), `0x00FF5806` bit2, `[0xD6]+0x64 = 1`
(`0x01027FE4`, **unmapped in the SC14480 reference tables**), and drives
the GPIO2/3 and `0xFF401C` (Reserved in SC14480) configuration.

## Runtime observers

* Vector 29 (`dsp_int` reference name) → handler normal `0x28A94` /
  p2test `0x27914`: saves state byte (`0x93CB`/`0x9512`), writes `0x28`,
  reads and writes back `[0xD6]+0x58` (DSP_INT read + write-1-to-clear
  per the SC14480 semantics), dispatches on VECTOR bits 3/2
  (`0x3B28`/`0x3B38` and `0x27744`/`0x27754`), restores the state byte,
  clears `0xFF5402 = 0x2000`, `retx`. **PROVEN_FIRMWARE_HANDLER.**
* Main dispatcher (normal `0x3A54→0x287B8`, p2test `0x27172→0x27502`)
  reads `[0xD6]+0x38` (`0x01027FB8`, PHASE_INFO under analogy) each pass
  when `[0x2B6]`/`[0x216]`≠0 and compares it against a struct slot,
  counting mismatches. **PROVEN_FIRMWARE_READ** (caller chain direct).

## What is NOT proven

* The `0x7C00` masked patch (helper at `0x182E`/`0x12B0`) — the call
  target is 2 bytes before the first locally consistent instruction; the
  store base `(r4,r3)` is not resolved from any caller.
* No CR16-side `DSP_CR16_INT` (bit4) write exists; the DSP is instead
  started periodically by main-counter syncs (MAIN_SYNC1 DSP_SYNC0-2 =
  8 kHz) — consistent with the interrupt handler above, not with a
  CR16-triggered model.
* SC14448 identity of every register remains CANDIDATE.
