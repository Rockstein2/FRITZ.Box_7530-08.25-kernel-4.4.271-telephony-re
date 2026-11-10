#!/usr/bin/env python3
"""No invented UART→DSP edge, direct graph provenance only."""
import json
from pathlib import Path

root=Path(__file__).resolve().parents[2]
d=json.loads((root/"tools/reports/cr16-e4-subsystem-graph.json").read_text())
fails=0
for name,image in d["images"].items():
    edges=image["cfg_evidence"]["edges"]
    good=(all(e["interaction_type"] in ("DIRECT_CALL","PERIPHERAL_ACCESS")
              and e["instruction_provenance"]["raw_bytes"] for e in edges)
          and image["dataflow_evidence"]["DIP_DSP_PCM_UART_RX_links"]=="UNRESOLVED")
    print(("PASS" if good else "FAIL")+f" {name}: no speculative cross-subsystem edge")
    fails+=not good
print(f"{fails} failure(s), 0 skip(s)")
raise SystemExit(bool(fails))
