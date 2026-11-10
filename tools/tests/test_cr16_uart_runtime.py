#!/usr/bin/env python3
"""Offline vector/command/raw-byte replay is covered by architecture test."""
import json
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[2]
bad=0
for n in ("normal","p2test"):
    report=json.loads((root/"tools/reports/cr16-e4-uart-runtime.json").read_text())["images"][n]
    c=report["cfg_evidence"]
    good=(c["uart_rx_tx_vectors_point_to_same_nop_retx"] and
          c["vector_RX"]["raw"]==c["vector_TX"]["raw"] and
          report["dataflow_evidence"]["rx_peripheral_read_into_runtime_parser"]=="NOT_ESTABLISHED")
    print(("PASS" if good else "FAIL")+f" {n}: UART vector stub, not inferred RX parser")
    bad+=not good
print(f"{bad} failure(s), 0 skip(s)")
raise SystemExit(bool(bad))
