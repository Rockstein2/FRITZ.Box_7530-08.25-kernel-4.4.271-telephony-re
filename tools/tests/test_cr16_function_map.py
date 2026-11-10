#!/usr/bin/env python3
"""Synthetic local boundaries: call seed != arbitrary branch target."""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import cr16_architecture as E  # noqa: E402
import cr16_cfg as C  # noqa: E402

errors=0
def ck(label,x,w):
    global errors
    print(("PASS" if x==w else "FAIL")+" "+label)
    errors+=x!=w

fw=C.Firmware(runs=[(0x100,bytes(16))],insns={
    0x100:C.Insn(0x100,2,"push","RA",b"\0\0"),
    0x102:C.Insn(0x102,2,"bal","target",b"\0\0"),
    0x104:C.Insn(0x104,2,"popret","RA",b"\0\0"),
    0x108:C.Insn(0x108,2,"push","RA",b"\0\0"),
    0x10a:C.Insn(0x10a,2,"popret","RA",b"\0\0")})
def edge(src,dst,kind,cat=C.DIRECT_RESOLVED):return C.Edge(src,dst,kind,cat)
calls=[edge(0x102,0x108,"call"),edge(0x102,0x104,"fallthrough")]
ck("call target seeds function",E.function_seed(calls[0]),True)
ck("fallthrough is not a function seed",E.function_seed(calls[1]),False)
ck("unresolved indirect call not a proven function entry",
   E.function_seed(edge(0x102,None,"indirect",C.INDIRECT_REGISTER)),False)
g=defaultdict(list)
for e in calls:g[e.src].append(e)
reached,exits,unknown,overlap=E.region(0x100,fw,g,{0x100,0x108})
ck("without entry predecessor CFG is incomplete",bool(unknown),True)
g[0x100].append(edge(0x100,0x102,"fallthrough"))
reached,exits,unknown,overlap=E.region(0x100,fw,g,{0x100,0x108})
ck("call continues at return site",reached,{0x100,0x102,0x104})
ck("callee is not swallowed by caller",0x108 in reached,False)
ck("callee boundary stops at return",exits,{0x104})
g[0x102].append(edge(0x102,0x108,"jump"))
ck("overlapping candidate entry flagged",E.region(0x100,fw,g,{0x100,0x108})[3],{0x108})
fw.insns[0x104]=C.Insn(0x104,2,"jump","(r10)",b"\0\0")
g[0x104].append(edge(0x104,None,"indirect",C.INDIRECT_REGISTER))
ck("unknown indirect exit blocks closed boundary",bool(E.region(0x100,fw,g,{0x100,0x108})[2]),True)
ck("different prefixes cannot match",
   E.fingerprint(fw,0x100,2)==E.fingerprint(fw,0x108,2),False)
print(f"{errors} failure(s), 0 skip(s)")
raise SystemExit(bool(errors))
