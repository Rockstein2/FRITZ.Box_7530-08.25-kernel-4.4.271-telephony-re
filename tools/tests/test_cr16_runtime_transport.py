#!/usr/bin/env python3
"""E4.4 fresh replay, fail-closed baseline/oracle and bounded buffer tests."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tools"))
import cr16_address_spaces as A  # noqa: E402
import cr16_runtime_transport as R  # noqa: E402

fails=skips=0
def ck(label,got,want):
    global fails
    print(("PASS" if got==want else "FAIL")+" "+label)
    if got!=want: print("got",str(got)[:200],"want",str(want)[:200]);fails+=1

for base,limit,tx in ((0x2fd,0xafb,0xafd),(0x25d,0xa5b,0xa5d)):
    geo=R.geometry(base,limit,tx,0x7f0)
    ck("base+0x800",geo["queue_base_plus_0x800_equals_tx_base"],True)
    ck("2-byte layout gap",geo["tx_base_minus_queue_limit"],2)
    ck("no invented non-overlap",geo["runtime_overlap"].startswith("UNRESOLVED"),True)
ck("changed base rejected",R.geometry(0x2fc,0xafb,0xafd,0x7f0)[
    "queue_base_plus_0x800_equals_tx_base"],False)
if not A.OBJDUMP.is_file() or any(not path.is_file() for _,path in A.IMAGES):
    skips+=1;print("SKIP oracle/firmware")
else:
    with tempfile.TemporaryDirectory() as td:
        cmd=[sys.executable,str(ROOT/"tools/cr16_runtime_transport.py"),"--out",td]
        ck("fresh run",subprocess.run(cmd,capture_output=True).returncode,0)
        for fn in R.NAMES:
            ck("complete "+fn,(Path(td)/fn).is_file(),True)
            if (Path(td)/fn).is_file() and (ROOT/"tools/reports"/fn).is_file():
                ck("replay "+fn,json.loads((Path(td)/fn).read_text()),
                   json.loads((ROOT/"tools/reports"/fn).read_text()))
        old={fn:(Path(td)/fn).read_bytes() for fn in R.NAMES}
        ck("oracle missing fails",subprocess.run(cmd+["--objdump",td+"/none"],capture_output=True).returncode!=0,True)
        with patch.object(R.D,"run_image",return_value=({"converged":False},None,[])):
            ck("NON_CONVERGED",R.main(["--out",td]),1)
        with patch.object(A,"REFERENCE_SHA",{"normal":"0"*64,"p2test":"0"*64}):
            ck("SHA mismatch",R.main(["--out",td]),1)
        with patch.object(R,"baseline",side_effect=ValueError("missing E4.3 report")):
            ck("missing baseline",R.main(["--out",td]),1)
        ck("rollback",{fn:(Path(td)/fn).read_bytes() for fn in R.NAMES},old)
        ck("incomplete diagnostic",(Path(td)/"cr16-e44.incomplete.json").is_file(),True)
print(f"{fails} failure(s), {skips} skip(s)")
raise SystemExit(bool(fails or skips))
