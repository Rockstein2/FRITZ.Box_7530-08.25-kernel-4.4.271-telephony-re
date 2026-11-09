# Dialog PCM comparison — SC14CVMDECT vs AVM SC14448

> **Status: comparison of evidence classes, not a settings transfer.**
> Sources: SC14CVMDECT datasheet rev 3.0 and the project's own OEM capture /
> PCMLINK reconstruction.

## 1. Comparison

| Parameter | SC14CVMDECT SF (datasheet) | AVM SC14448 / FRITZ!Box 7530 | Evidence status |
|---|---|---|---|
| FSC | 8 or 16 kHz | approximately 8 kHz | CVM: PDF p22; AVM: OEM capture `FS: 8000 Hz` |
| Master BCLK | 1.152, 1.536, 2.304 or 4.608 MHz | approximately `1.024355 MHz` (OEM log) | CVM: PDF p23; AVM: OEM capture |
| PCM mode | Phoenix API controlled; master or slave | OEM firmware / PCMLINK/TDM path | CVM: API/datasheet; AVM: DISASM |
| Logical TDM slots | CVM-specific; SC14480 reference has 4×16-bit PCM channels | 8 logical slots in the reconstructed frame | AVM: project reconstruction; CVM/SC14480: do not map directly |
| Control path | Phoenix API / DSP PCM control | Linux `pcmlink.ko` -> TDM slot 5 | AVM: DISASM; no CVM equivalence |
| FSC pulse | 1, 8, 16 or 32 bits | not measured / not reconstructed | CVM only |
| Clock edge | API `PcmClkOnRising` | not established from the static PCMLINK model | CVM only |
| Open drain | API `PcmDoutIsOpenDrain`, `PcmIsOpenDrain` | not established | CVM only |
| Wire order | datasheet/API configuration | raw DMA model known; physical wire order **UNKNOWN** | AVM E1/E2/E3 |
| Slot-5 handler | not applicable | **NOT FOUND** | AVM E0–E3 |

## 2. The BCLK difference is real

SC14480 additionally describes a **four-channel × 16-bit** PCM interface
(printed p64) and mentions a `1.024 MHz` clock for DIP 8/9 mode (printed
p33–34).  That 1.024 MHz is a sequencer clock, not automatically the PCM
BCLK; it must not be used to explain the AVM `~1.024355 MHz` observation
without a separate measurement.

The CVM list is:

```text
1.152 MHz
1.536 MHz
2.304 MHz
4.608 MHz
```

The OEM FRITZ!Box capture reports approximately **1.024355 MHz**, which is
not one of those four values.  Therefore:

- do not copy a CVM `PcmClk` setting into the SC14448 path;
- do not assume the CVM PCM timing diagram is the FRITZ!Box timing;
- the observed 8 kHz FSC does not make the two clock trees equivalent;
- SC14480's four 16-bit PCM channels are not the AVM eight logical slots.

The OEM value is a measurement/report from the working AVM system, not a
datasheet maximum or a static reconstruction.  The SC14448-side divider and
pinmux remain separate questions.

## 3. What is already established on the Linux side

| Item | Status |
|---|---|
| TX slot-5 control formula | **PROVEN** Linux-side (DISASM, `build_slic_ctrl`/`TxDMA`) |
| RX status mapping | **PROVEN** Linux-side; physical meaning of most bits unknown |
| Raw DMA `EOR #2` pair swap | **PROVEN** for decoded halfword accesses; audio path uses the same instruction |
| Physical wire order | **UNKNOWN** |
| SC14448 slot-5 firmware consumer | **NOT FOUND**; no proven source-to-sink chain |

The CVM reference can help name PCM options, but it cannot close any of these
AVM-side questions.

## 4. Slot terminology

Do not mix:

- DECT RF slots: 0…23 (radio frames/slots);
- PCM/TDM logical slots: 0…7 in the reconstructed FRITZ!Box frame;
- slot 5: the reconstructed FON control/status position in the **logical**
  frame, not a DECT RF slot.

The OsmocomDECT patch and CVM documentation use “slot” in different contexts;
the register cross-reference keeps them separate.

## 5. Pinmux warning

The CVM datasheet maps, for that chip:

```text
P2[2] -> PCM_CLK
P2[3] -> PCM_DI
P2[4] -> PCM_DO
P2[5] -> PCM_FSC
```

The SC14448 firmware accesses the same numeric `0x00FF48xx` GPIO/PAD family,
but the observed `P2_MODE` write does not prove those four pins are selected
as PCM on the FRITZ!Box.  The physical FRITZ!Box pin/net mapping remains
**UNKNOWN**; Q31 is unchanged.
