#!/usr/bin/env python3
"""Synthetic queue uncertainty plus fresh ten-report replay and rollback."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tools"))
import cr16_queue_trace as Q  # noqa: E402
import cr16_address_spaces as A  # noqa: E402

fails=skips=0
def ck(label,actual,expected):
    global fails
    if actual!=expected: print("FAIL",label,str(actual)[:100],str(expected)[:100]);fails+=1
    else:print("PASS",label)

ck("equal pointers local empty",Q.queue_status(0x2fd,0x2fd),"LOCALLY_EQUAL")
ck("different pointers local nonempty",Q.queue_status(0x2fd,0x305),"LOCALLY_NOT_EQUAL")
ck("unknown indirect writer invalidates empty",Q.queue_status(0x2fd,0x2fd,unknown_writer=True),"UNRESOLVED")
ck("DMA writer invalidates empty",Q.queue_status(None,0x2fd),"UNRESOLVED")
ck("item length unknown",Q.item_field(11,"pointer value")["bounds"],"LENGTH_UNRESOLVED")
ck("malformed short item",Q.item_field(11,"pointer value",known_size=8)["bounds"],"OUT_OF_BOUNDS")
ck("bounded field",Q.item_field(7,"pointer",known_size=12)["bounds"],"WITHIN_LOCAL_ALLOCATION")
if not A.OBJDUMP.is_file() or any(not p.is_file() for _,p in A.IMAGES):
    skips+=1;print("SKIP missing offline firmware/oracle")
else:
    with tempfile.TemporaryDirectory() as td:
        cmd=[sys.executable,str(ROOT/"tools/cr16_queue_trace.py"),"--out",td]
        p=subprocess.run(cmd,capture_output=True,text=True)
        ck("fresh replay",p.returncode,0)
        for fn in Q.FILES:
            ck("complete "+fn,(Path(td)/fn).is_file(),True)
            if (Path(td)/fn).is_file():
                ck("deterministic "+fn,json.loads((Path(td)/fn).read_text()),
                   json.loads((ROOT/"tools/reports"/fn).read_text()))
        original={fn:(Path(td)/fn).read_bytes() for fn in Q.FILES}
        ck("missing oracle fails",subprocess.run(cmd+["--objdump",td+"/absent"],
            capture_output=True).returncode!=0,True)
        with patch.object(Q.D,"run_image",return_value=({"converged":False},None,[])):
            ck("NON_CONVERGED fails",Q.main(["--out",td])!=0,True)
        with patch.object(A,"REFERENCE_SHA",{n:"0"*64 for n in ("normal","p2test")}):
            ck("SHA fails",Q.main(["--out",td])!=0,True)
        ck("previous bundle preserved",{fn:(Path(td)/fn).read_bytes() for fn in Q.FILES},original)
        ck("incomplete diagnostic",(Path(td)/"cr16-e41.incomplete.json").is_file(),True)
        for n in ("normal","p2test"):
            d=json.loads((Path(td)/Q.FILES[0]).read_text())["images"][n]
            ck(f"{n} init pointers equal",len(set(d["dataflow_evidence"]["initial_cells"].values())),1)
            ck(f"{n} full unresolved",d["dataflow_evidence"]["full_condition"],"UNRESOLVED")
            producer=json.loads((Path(td)/Q.FILES[1]).read_text())["images"][n]
            tags=[r["immediate_tag_from_adjacent_instruction"] for r in
                  producer["cfg_evidence"]["adjacent_immediate_caller_tags"]]
            ck(f"{n} no *adjacent* literal 0x23", "0x23" in tags,False)
            ck(f"{n} unknown caller tags retained",None in tags,True)
            fmt=json.loads((Path(td)/Q.FILES[2]).read_text())["images"][n]
            ck(f"{n} global state not confused with item tag",
               fmt["cfg_evidence"].get("marker_written_before_parser"),None)
print(f"{fails} failure(s), {skips} skip(s)")
raise SystemExit(bool(fails))
