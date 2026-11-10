#!/usr/bin/env python3
"""Fresh E4 bundle replay and fail-closed integrity tests."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tools"))
import cr16_architecture as E  # noqa: E402
import cr16_address_spaces as A  # noqa: E402

fail=skip=0
def ck(label,a,b):
    global fail
    if a!=b:print("FAIL",label,str(a)[:100],str(b)[:100]);fail+=1
    else:print("PASS",label)

if not A.OBJDUMP.is_file() or any(not p.is_file() for _,p in A.IMAGES):
    skip+=1
    print("SKIP missing offline oracle/firmware")
else:
    with tempfile.TemporaryDirectory() as td:
        run=[sys.executable,str(ROOT/"tools/cr16_architecture.py"),"--out",td]
        p=subprocess.run(run,capture_output=True,text=True)
        ck("fresh replay exit",p.returncode,0)
        for fn in E.NAMES:
            ck("report exists "+fn,(Path(td)/fn).is_file(),True)
            if (Path(td)/fn).is_file():
                ck("deterministic "+fn,json.loads((Path(td)/fn).read_text()),
                   json.loads((ROOT/"tools/reports"/fn).read_text()))
        old={fn:(Path(td)/fn).read_bytes() for fn in E.NAMES}
        ck("missing oracle fails",subprocess.run(run+["--objdump",td+"/missing"],
           capture_output=True).returncode!=0,True)
        with patch.object(E.D,"run_image",return_value=({"converged":False},None,[])):
            ck("NON_CONVERGED fails",E.main(["--out",td])!=0,True)
        with patch.object(A,"REFERENCE_SHA",{n:"0"*64 for n in ("normal","p2test")}):
            ck("wrong SHA fails",E.main(["--out",td])!=0,True)
        ck("old reports preserved",{fn:(Path(td)/fn).read_bytes() for fn in E.NAMES},old)
        for n in ("normal","p2test"):
            d=json.loads((Path(td)/E.NAMES[3]).read_text())["images"][n]
            ck(f"{n} command IDs",d["dataflow_evidence"]["parser"]["subcommand_values"],[7,9,10,13])
            ck(f"{n} source unknown",d["cfg_evidence"]["parser_input_from_UART"],"UNRESOLVED")
print(f"{fail} failure(s), {skip} skip(s)")
raise SystemExit(bool(fail))
