#!/usr/bin/env python3
"""E4.2 synthetic register slices and complete fresh-directory replay."""
from __future__ import annotations

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
import cr16_queue_provenance as P  # noqa: E402

fails=skips=0
def ck(label,got,want):
    global fails
    print(("PASS" if got==want else "FAIL")+" "+label)
    if got!=want:print(" got:",str(got)[:300],"want:",str(want)[:300]);fails+=1

def fixture(items, links, site, summaries=None):
    fw=C.Firmware([])
    fw.insns={a:C.Insn(a,2,m,op,b'\0\0') for a,m,op in items}
    edges=[C.Edge(a,b,"fallthrough" if kind=="ft" else kind,C.DIRECT_RESOLVED)
           for a,b,kind in links]
    return P.slice_reg(fw,P.predecessors(edges),site,summaries=summaries)

def line(items,site):
    return [(x,x+2,"ft") for x,_,_ in items if x+2<=site]

direct=[(0,"movb","$0x23:m,r2"),(2,"nop","")]
ck("direct r2=0x23",P.classify(fixture(direct,line(direct,2),2)),"TAG_23_PROVEN")
ck("prior block r2=0x23",P.classify(fixture(direct,[(0,2,"jump")],2)),"TAG_23_PROVEN")
arg=[(0,"movb","r4,r2"),(2,"nop","")]
ck("caller argument remains unknown",P.classify(fixture(arg,line(arg,2),2)),"TAG_SOURCE_UNKNOWN")
ram=[(0,"loadb","0x100:l,r2"),(2,"nop","")]
ck("RAM tag remains unknown",P.classify(fixture(ram,line(ram,2),2)),"TAG_SOURCE_UNKNOWN")
ck("copied element unknown",P.classify(fixture([(0,"loadb","0x3:s(r8,r7),r2"),(2,"nop","")],
    [(0,2,"ft")],2)),"TAG_SOURCE_UNKNOWN")
const=[(0,"movb","$0x14:m,r2"),(2,"nop","")]
ck("excluded tag under model",P.classify(fixture(const,line(const,2),2)),"TAG_23_EXCLUDED_UNDER_MODEL")
two=[(0,"movb","$0x23:m,r2"),(2,"movb","$0x14:m,r2"),(4,"nop","")]
ck("conditional paths possible",P.classify(fixture(two,[(0,4,"cond"),(2,4,"ft")],4)),"TAG_23_POSSIBLE")
call=[(0,"movb","$0x23:m,r2"),(2,"jal","(r4,r3)"),(4,"nop","")]
ck("indirect call clobber",P.classify(fixture(call,[(0,2,"ft"),(2,4,"ft")],4)),"TAG_SOURCE_UNKNOWN")
ck("unknown indirect caller",P.classify(fixture([(4,"nop","")],[],4)),"TAG_SOURCE_UNKNOWN")
ck("broken CFG cannot exclude",P.classify(fixture([(0,"movb","$0x14:m,r2"),(4,"nop","")],[],4)),"TAG_SOURCE_UNKNOWN")
ck("unknown overwrite at header invalidates parser",P.classify([]),"TAG_SOURCE_UNKNOWN")
ck("proven call tag is not parser reachability",P.classify(fixture(direct,line(direct,2),2)),
   "TAG_23_PROVEN")  # 'PROVEN' is narrowly at allocator entry only.
ident=dict(same_generation=True,known_consumer=True,complete_aliases=True)
ck("header item+2 state rewrite leaves tag intact",P.tag_at_parser(0x22,
    [{"offset":2,"byte":0x23}],**ident),"TAG_23_EXCLUDED_UNDER_MODEL")
ck("independent global 0x23 leaves tag intact",P.tag_at_parser(0x22,
    [{"scope":"global","offset":3,"byte":0x23}],**ident),"TAG_23_EXCLUDED_UNDER_MODEL")
ck("real item+3 alias changes tag",P.tag_at_parser(0x22,
    [{"offset":3,"byte":0x23}],**ident),"TAG_23_PROVEN")
ck("unknown alias forbids exclusion",P.tag_at_parser(0x22,
    [{"offset":None,"byte":None}],**ident),"UNRESOLVED")
ck("overlapping word forbids exclusion",P.tag_at_parser(0x22,
    [{"offset":2,"width":2,"byte":None}],**ident),"UNRESOLVED")
ck("interrupt writer forbids exclusion",P.tag_at_parser(0x22,
    [{"scope":"item","offset":None}],**ident),"UNRESOLVED")
ck("wrap generation reuse forbids proof",P.tag_at_parser(0x23,[],
    same_generation=False,known_consumer=True,complete_aliases=True),"UNRESOLVED")
ck("incomplete aliases forbid proof",P.tag_at_parser(0x23,[],
    same_generation=True,known_consumer=True,complete_aliases=False),"UNRESOLVED")

if not A.OBJDUMP.is_file() or any(not p.is_file() for _,p in A.IMAGES):
    skips+=1;print("SKIP offline oracle/firmware unavailable")
else:
    with tempfile.TemporaryDirectory() as td:
        cmd=[sys.executable,str(ROOT/"tools/cr16_queue_provenance.py"),"--out",td]
        ck("fresh replay process",subprocess.run(cmd,capture_output=True).returncode,0)
        for fn in P.NAMES:
            generated=Path(td)/fn;committed=ROOT/"tools/reports"/fn
            ck("complete "+fn,generated.is_file(),True)
            if generated.is_file() and committed.is_file():
                ck("fresh JSON equals committed "+fn,json.loads(generated.read_text()),json.loads(committed.read_text()))
        before={fn:(Path(td)/fn).read_bytes() for fn in P.NAMES}
        ck("missing oracle fails",subprocess.run(cmd+["--objdump",td+"/missing"],capture_output=True).returncode!=0,True)
        with patch.object(P.D,"run_image",return_value=({"converged":False},None,[])):
            ck("NON_CONVERGED fails",P.main(["--out",td]),1)
        with patch.object(A,"REFERENCE_SHA",{"normal":"0"*64,"p2test":"0"*64}):
            ck("bad SHA fails",P.main(["--out",td]),1)
        ck("failed replay did not overwrite bundle",{fn:(Path(td)/fn).read_bytes() for fn in P.NAMES},before)
        ck("incomplete diagnostic",(Path(td)/"cr16-e42.incomplete.json").is_file(),True)
        for name,expected in (("normal",(21,1)),("p2test",(18,1))):
            d=json.loads((Path(td)/P.NAMES[1]).read_text())["images"][name]["dataflow_evidence"]["at_allocator_entry"]
            ck(name+" excluded/unknown",(d["TAG_23_EXCLUDED_UNDER_MODEL"],d["TAG_SOURCE_UNKNOWN"]),expected)
            reach=json.loads((Path(td)/P.NAMES[3]).read_text())["images"][name]
            ck(name+" no false parser proof",reach["dataflow_evidence"]["specific_allocator_generation_to_parser_tag_23"],"UNRESOLVED")
            typ=json.loads((Path(td)/P.NAMES[4]).read_text())["images"][name]
            ck(name+" case7 tag/state separate",typ["dataflow_evidence"]["case7_new_type"].find("tag 0x22 and state 0x23")>=0,True)
print(f"{fails} failure(s), {skips} skip(s)")
raise SystemExit(bool(fails or skips))
