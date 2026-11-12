#!/usr/bin/env python3
"""Selected parser cases and fail-closed pointer provenance fixtures."""
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tools"))
import cr16_queue_trace as Q  # noqa: E402

fails=0
def ck(label,actual,want):
    global fails
    print(("PASS" if actual==want else "FAIL")+" "+label)
    fails+=actual!=want

ck("item pointer does not imply MMIO",Q.conditional_value(["item"],source_known=False),
   "TARGET_RANGE_UNRESOLVED")
ck("clobber kills local pointer",Q.conditional_value(["item"],source_known=True,alias_changed=True),
   "TARGET_RANGE_UNRESOLVED")
ck("multiple aliases forbid range proof",Q.conditional_value(["a","b"],source_known=True),
   "TARGET_RANGE_UNRESOLVED")
for n in ("normal","p2test"):
    commands=json.loads((ROOT/"tools/reports/cr16-e41-command-cases.json").read_text())["images"][n]
    cases=commands["dataflow_evidence"]["cases"]
    ck(f"{n} case IDs",[x["id"] for x in cases],[7,9,10,13])
    ck(f"{n} unknown ID unclassified",commands["dataflow_evidence"]["unknown_command_id"],
       "returns without a named handler")
    pw=json.loads((ROOT/"tools/reports/cr16-e41-pointer-write.json").read_text())["images"][n]
    ck(f"{n} pointer from item",pw["dataflow_evidence"]["pointer_source"].startswith("POINTER_FROM_QUEUE_ITEM"),True)
    ck(f"{n} no target proof",pw["dataflow_evidence"]["target_range"],"TARGET_RANGE_UNRESOLVED")
    ck(f"{n} no external control claim",pw["dataflow_evidence"]["external_control"],"EXTERNAL_CONTROL_NOT_PROVEN")
print(f"{fails} failure(s), 0 skip(s)")
raise SystemExit(bool(fails))
