#!/usr/bin/env python3
"""E4.3 synthetic indirect target clobbers and fresh atomic reports."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tools"))
import cr16_cfg as C  # noqa: E402
import cr16_address_spaces as A  # noqa: E402
import cr16_command_effects as E  # noqa: E402

fail=skip=0
def ck(label,got,want):
    global fail
    print(("PASS" if got==want else "FAIL")+" "+label)
    if got!=want: print(" got",got,"want",want);fail+=1

ck("normal CR16B word PC",E.indirect_pc_word(0x13c59),0x278b2)
ck("p2test CR16B word PC",E.indirect_pc_word(0x1b7e),0x36fc)
ck("out-of-range pair rejected",E.indirect_pc_word(1<<20),None)
fw=C.Firmware([])
fw.insns={0x278b2:C.Insn(0x278b2,2,"push","",b'\0\0')}
def insn(mn,op):return C.Insn(0,2,mn,op,b'\0\0')
ck("first call target under isolated pair",E.indirect_status(0x13c59,
    [insn("movb","$0x15:m,r3")],fw,0x278b2),"PROVEN_UNDER_LOCAL_CFG_MODEL")
ck("indirect call clobber",E.indirect_status(0x13c59,
    [insn("jal","(r11,r10)")],fw,0x278b2),"UNRESOLVED_CLOBBER")
ck("pair register rewrite",E.indirect_status(0x13c59,
    [insn("movw","$0x1:s,r10")],fw,0x278b2),"UNRESOLVED_CLOBBER")
ck("unknown target isn't proved",E.indirect_status(0x13c59,[],fw,0x36fc),"UNRESOLVED")
if not A.OBJDUMP.is_file() or any(not path.is_file() for _,path in A.IMAGES):
    skip+=1;print("SKIP oracle/firmware")
else:
    with tempfile.TemporaryDirectory() as td:
        cmd=[sys.executable,str(ROOT/"tools/cr16_command_effects.py"),"--out",td]
        ck("fresh run",subprocess.run(cmd,capture_output=True).returncode,0)
        for fn in E.NAMES:
            ck("exists "+fn,(Path(td)/fn).exists(),True)
            if (Path(td)/fn).exists() and (ROOT/"tools/reports"/fn).exists():
                ck("replay " +fn,json.loads((Path(td)/fn).read_text()),
                   json.loads((ROOT/"tools/reports"/fn).read_text()))
        old={fn:(Path(td)/fn).read_bytes() for fn in E.NAMES}
        ck("oracle missing",subprocess.run(cmd+["--objdump",td+"/none"],capture_output=True).returncode!=0,True)
        with patch.object(E.D,"run_image",return_value=({"converged":False},None,[])):
            ck("NON_CONVERGED",E.main(["--out",td]),1)
        with patch.object(A,"REFERENCE_SHA",{"normal":"0"*64,"p2test":"0"*64}):
            ck("wrong SHA",E.main(["--out",td]),1)
        with patch.object(E,"e42_check",side_effect=ValueError("E4.2 report corrupted")):
            ck("bad E4.2 baseline",E.main(["--out",td]),1)
        ck("rollback preserves bundle",{fn:(Path(td)/fn).read_bytes() for fn in E.NAMES},old)
        ck("diagnostic retained",(Path(td)/"cr16-e43.incomplete.json").exists(),True)
print(f"{fail} failure(s), {skip} skip(s)")
raise SystemExit(bool(fail or skip))
