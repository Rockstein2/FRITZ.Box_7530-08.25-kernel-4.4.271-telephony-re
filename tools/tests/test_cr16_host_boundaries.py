#!/usr/bin/env python3
"""No resolved RX-to-queue or command-to-TX path is promoted from proximity."""
import json
from pathlib import Path

root=Path(__file__).resolve().parents[2];fails=0
for name in ("normal","p2test"):
    def load(part):return json.loads((root/"tools/reports"/f"cr16-e44-{part}.json").read_text())["images"][name]
    rx=load("rx-candidates");edge=load("host-boundaries");layout=load("buffer-layout");tx=load("tx-producers")
    checks={"no 0xff4902 read":rx["cfg_evidence"]["direct_resolved_data_register_0x00ff4902_reads"]==0,
        "arch register access exists":any(x["architectural_address"]=="0x00ff4902" and
             x["operation"]=="WRITE" for x in rx["dataflow_evidence"]["register_access_inventory"]),
        "physical UART not observed":rx["dataflow_evidence"]["physical_UART"]=="PHYSICAL_UART_NOT_OBSERVED",
        "no invented host ingress":edge["cfg_evidence"]["peripheral_to_software_queue"]=="UNRESOLVED",
        "no command-to-TX":edge["cfg_evidence"]["parser_to_TX"]=="UNRESOLVED",
        "no all-path nonoverlap":layout["dataflow_evidence"]["geometry"]["runtime_overlap"].startswith("UNRESOLVED"),
        "TX bytes linked locally":tx["dataflow_evidence"]["selected_TX"].startswith("RAM byte")}
    for label,ok in checks.items():
        print(("PASS" if ok else "FAIL")+f" {name}: {label}");fails+=not ok
print(f"{fails} failure(s), 0 skip(s)")
raise SystemExit(bool(fails))
