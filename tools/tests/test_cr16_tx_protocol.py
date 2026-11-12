#!/usr/bin/env python3
"""TX versus unrelated event: no invented command-response link."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
fails=0
for n in ("normal","p2test"):
    tx=json.loads((ROOT/"tools/reports/cr16-e41-tx-buffer.json").read_text())["images"][n]
    resp=json.loads((ROOT/"tools/reports/cr16-e41-tx-responses.json").read_text())["images"][n]
    checks={"TX data architecture":tx["dataflow_evidence"]["RAM_byte_to_architectural_TX"].startswith("0x00ff4902"),
        "no command-response proof":resp["cfg_evidence"]["command_to_TX_buffer_proven"] is False,
        "response framing unknown":resp["dataflow_evidence"]["response_framing"]=="UNRESOLVED"}
    for label,ok in checks.items():
        print(("PASS" if ok else "FAIL")+f" {n}: {label}")
        fails+=not ok
print(f"{fails} failure(s), 0 skip(s)")
raise SystemExit(bool(fails))
