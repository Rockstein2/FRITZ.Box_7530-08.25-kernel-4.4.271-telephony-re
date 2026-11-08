# FON-E0 — protocol confidence and open questions

> **Status: offline synthesis.**  This is the honest confidence matrix, not a
> driver authorization.

---

## 1. Confidence matrix

| Claim | Status | Evidence |
|---|---|---|
| `pcmlink` exposes virtual registers 0x40/0x44/0x48/0x4c/0x50 | **CONFIRMED** | `pcmlink` and `isdn_fbox_fon5` disassembly |
| Writes are queued in an 8-byte, 64-entry ring | **CONFIRMED** | `lpcmlink_ul_writeregister` `0x34b8` |
| `TxDMA` consumes a ring entry and builds slot-5 control | **CONFIRMED** | `TxDMA` `0x9710` |
| Control formula in `build_slic_ctrl` | **CONFIRMED** | `0x8f68..0x8fac` |
| `reg48` bits 4-11 -> control bits 0-3/5-8 | **CONFIRMED** | same |
| `reg2c` bits 17/18 -> control bits 4/9 | **CONFIRMED** | same |
| Normal marker `0x4000` | **CONFIRMED** | same |
| Special marker `0x8000` + `TDMPriv+0x7f4` | **CONFIRMED** | `0x8f70`, `TxDMA` `0x99a0` |
| `TxDMA` fixed header `0x0000/0xfefe/0x5555` | **CONFIRMED** | `0x9874..0x98d8` |
| Exact byte-order/slot-index mapping after `EOR #2` | **INFERRED / CAVEAT** | `TxDMA` stores; see TX document |
| `PutRxDMA` maps RX status bit 3 -> reg44 bit 7 | **CONFIRMED** | `0x9b38..0x9b90` |
| RX 0x8000 suppresses reg44 update | **CONFIRMED** | `0x9b44..0x9b50` |
| RX 0x4000 does not suppress reg44 update | **CONFIRMED** | `0x9b54..0x9b74` |
| RX zero -> raw `0xbad00000` | **CONFIRMED** | `0x9bbc` |
| Hook bit is callers' interpretation of reg44 bit 7 | **INFERRED** | `slic_get_hook_state` |
| SC14448 is the slot-5 consumer | **INFERRED (high)** | board/PCM topology; no firmware handler |
| SC14448 firmware has a slot-5 handler | **UNKNOWN** | bounded search found none |
| `0x4000` means idle | **UNKNOWN** | not proven |
| `0x8000` means ring | **UNKNOWN** | not proven |
| High-voltage ring/line-feed topology | **UNKNOWN** | no schematic/measurement |
| Minimum standalone driver is feasible | **CONDITIONAL** | depends on Q16/Q17/Q75 |

## 2. Q16 / Q17 / Q30 / Q74 / Q75 / Q76

### Q16 — TX slot-5 meaning

- **Previous:** unknown.
- **New:** full Linux-side bit source and formula; markers separated from data
  bits; special path tied to `TDMPriv+0x7f4`/register `0x30`.
- **Status:** **still open** for SC14448 semantics.
- **Blocker:** firmware handler or a trace of slot 5 inside the SC14448.

### Q17 — RX slot-5 status meaning

- **Previous:** only hook bit 3 known.
- **New:** complete Linux-side bit extraction: status 0-3 -> reg44 4-7,
  status 5-8 -> reg44 8-11, status 4/9-14 not mapped, 0x8000 no update,
  0x4000 updates, zero -> `0xbad00000`.
- **Status:** **still open** for physical meaning of bits 0-2, 4-14.
- **Blocker:** firmware-side status assembly or a hardware trace.

### Q30 — FON without AVM DECT userspace

- **Previous:** open.
- **New:** no separate UART/SPI/I2C/GPIO FON control path found; the only
  recovered control path is the PCMLINK/TDM slot-5 chain.
- **Status:** **open**.  A standalone driver may need the SC14448 firmware,
  but this is not proven without a hardware experiment.

### Q74 — frame builder matches TxDMA

- **Previous:** dry-run builder not compared.
- **New:** logical header/control values and formula match the disassembly.
  The `EOR #2` byte-order mapping is a recorded caveat, so “byte-for-byte”
  is **not** claimed.
- **Status:** **partially resolved**.

### Q75 — firmware consumer of slot 5

- **Previous:** unknown.
- **New:** bounded negative search over resolved accesses; no slot-5 handler.
- **Status:** **still open**.  Indirect/cross-block paths are not excluded.

### Q76 — `fs_per_dma`

- **Previous:** narrowed to board config, numeric value unknown.
- **New:** E0 did not recover the closed board table.
- **Status:** **still open**.  Do not use 32 as confirmed OEM value.

## 3. Minimum independent FON driver

The minimum, if the SC14448 side is eventually proven, is:

1. QCA ADSS/TDM/MBOX transmit/receive at 8 kHz, 8 x 16-bit slots;
2. a slot-5 control/status channel with the formulas in
   `fon-sc14448-pcmlink-protocol.md`;
3. ring cadence and hook polling from the analog state machine;
4. audio slot routing for slots 6/7;
5. reset/firmware sequencing only when separately proven safe;
6. line/ring electrical safety, which is outside software.

The driver does **not** need the AVM virtual-register ABI if it can speak the
proven slot-5 bits directly, but it still needs the SC14448-side meaning of
those bits.  Without that, it can only be a transport/test harness, not a
functional FON driver.

## 4. What cannot be proven offline

- the physical slot/byte order after `EOR #2`;
- the SC14448 firmware handler and all analog effects;
- whether `0x4000`/`0x8000` are markers, strobes or state selectors;
- high-voltage ring/line-feed topology;
- the threshold/polarity of the hook bit;
- whether the SC14448 must be running for line control.
