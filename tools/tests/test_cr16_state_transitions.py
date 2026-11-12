#!/usr/bin/env python3
"""E4.3 conditional edges must not masquerade as runtime transitions."""
import json
from pathlib import Path

root=Path(__file__).resolve().parents[2];fails=0
for name in ("normal","p2test"):
    def load(suffix):return json.loads((root/"tools/reports"/f"cr16-e43-{suffix}.json").read_text())["images"][name]
    states=load("state-transitions");ind=load("case9-indirect");ptr=load("case13-pointer-targets")
    checks={"no producer-backed effects":not states["dataflow_evidence"]["producer_backed_edges"],
        "case9 later targets unresolved":all(x["target"]=="UNRESOLVED_CLOBBER_AFTER_PRIOR_CALL"
            for x in ind["cfg_evidence"]["later_sites"]),
        "first indirect conditional":ind["cfg_evidence"]["first_target_confidence"]=="PROVEN_UNDER_LOCAL_CFG_MODEL",
        "no MMIO fabrication":ptr["dataflow_evidence"]["physical_MMIO_effect"]=="NOT_PROVEN",
        "no pointer range fabrication":ptr["dataflow_evidence"]["reachable_address_range"]=="TARGET_RANGE_UNRESOLVED"}
    for label,ok in checks.items():
        print(("PASS" if ok else "FAIL")+f" {name}: {label}");fails+=not ok
print(f"{fails} failure(s), 0 skip(s)")
raise SystemExit(bool(fails))
