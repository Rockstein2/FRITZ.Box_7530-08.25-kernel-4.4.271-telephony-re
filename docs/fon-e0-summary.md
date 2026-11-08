# FON-E0 summary — SC14448 ↔ PCMLINK protocol

> **Status: offline research completed to its evidence boundary.**
> No router was accessed.  No firmware, module, TDM, DMA, GPIO40, reset or
> analog line was executed.

## 1. What is now proven

- The Linux-side TX control formula (`build_slic_ctrl`, `pcmlink.ko` `0x8f68`)
  is recovered and reproduced by an offline reference decoder:
  `reg48` bits 4-11, `reg2c` bits 17/18, normal marker `0x4000`, special path
  marker `0x8000`.
- The special path is fed from `TDMPriv+0x7f4` by the command for register
  word `0x30`.
- The command ring is 64 x 8-byte entries; `flags` acts as a frame-delay gate.
- The RX formula (`PutRxDMA`, `0x9a60`) is recovered: RX status 0-3 -> reg44
  bits 4-7, 5-8 -> reg44 bits 8-11, 0x8000 suppresses reg44, 0x4000 does not,
  zero -> raw `0xbad00000`.
- Hook is reg44 bit 7, therefore RX status bit 3, as an inferred semantic.
- `slics_reset`, `slic_set_ring`, `Handle_Ints_FPGA`, and the
  `Set_POTS_Line_FPGA` 0..8 dispatch are reconstructed at the instruction
  level; numeric line-state names are not invented.
- A reference encoder/decoder and golden vectors are in
  `tools/fon-slot5-protocol/`.

## 2. What was not found

- No SC14448 slot-5/FON command handler in the resolved CR16 map.
- No resolved 16-bit PCM buffer indexed as slot 5.
- No proven `0x4000` or `0x5555` immediate in firmware.
- No proven PCM interrupt assigned to slot 5.
- No proof that `0x4000` = idle or `0x8000` = ring.
- No physical byte-order resolution of the `TxDMA` `EOR #2` writes.
- No high-voltage line/ring topology.

The firmware search is a bounded negative result, not proof of absence:
indirect calls, cross-block addresses and unresolved vectors remain.

## 3. Deliverables

```text
docs/fon-sc14448-pcmlink-protocol.md
docs/fon-e0-summary.md
docs/history/fon-e0-tx-control-reconstruction.md
docs/history/fon-e0-rx-status-reconstruction.md
docs/history/fon-e0-analog-state-machine.md
docs/history/fon-e0-sc14448-firmware-search.md
docs/history/fon-e0-protocol-confidence.md
tools/fon-slot5-protocol/
```

## 4. Question status

| Q | Status |
|---|---|
| Q16 TX slot-5 semantics | Linux-side mapping proven; SC14448 side **open** |
| Q17 RX slot-5 semantics | Linux-side mapping proven; physical bits **open** |
| Q30 FON without AVM stack | **open**; no alternate control path found |
| Q74 frame builder match | **partial**; logical values match, EOR byte order caveat |
| Q75 firmware consumer | **open**; bounded search found nothing |
| Q76 `fs_per_dma` | **open**; not recovered in E0 |

## 5. Next evidence

1. Cross-block CR16 dataflow or a table-aware analysis of indirect paths.
2. A future read-only trace of TX/RX slot 5 on a safe bench.
3. Electrical continuity/topology of the LM324/BCP53/line transformer.
4. Only then a reviewed standalone FON driver.  No DMA, reset, firmware or
   ringing is authorized by E0.
