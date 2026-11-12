#!/usr/bin/env python3
"""E4.3 offline conditional command effects; parser producer path unresolved."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cr16_address_spaces as A
import cr16_architecture as E
import cr16_cfg as C
import cr16_dataflow as D
import cr16_dip_trace as T
import cr16_queue_trace as Q
import cr16_peripheral_xrefs as X

ROOT=Path(__file__).resolve().parent.parent
NAMES=tuple("cr16-e43-"+x+".json" for x in (
    "command-effects","case7-nested-item","case9-indirect",
    "case10-version-delta","case13-pointer-targets","state-transitions",
    "unresolved-paths"))
S={
 "normal":dict(c9=0x27fb4,literal=0x27fba,first=0x27fda,
    later=(0x27fe2,0x2800a,0x28014),table=0x27fc0,
    c10=0x278b2,cmp1=0x278b6,cmp2=0x278c2,gate=0x278ca,
    helper=0x2788a,helper_store=0x278ae,lookup=0x2773a,
    case7_tag=0x9e26,case7_state=0x9e38,case7_type=0x9e3e,
    case7_sub=0x9e40,case7_copy=0x9e5c),
 "p2test":dict(c9=0x3c72,literal=0x3c78,first=0x3c98,
    later=(0x3ca0,0x3cc6,0x3cce),table=0x3c7e,
    c10=0x36fc,cmp1=0x3700,cmp2=0x3708,gate=0x3710,
    helper=0x36d4,helper_store=0x36f8,lookup=0x35de,
    case7_tag=0x27428,case7_state=0x2743a,case7_type=0x27440,
    case7_sub=0x27442,case7_copy=0x2745e),
}


def indirect_pc_word(pair):
    """CR16B JAL (rp): low16 -> PC[1:16], high4 -> PC[17:20]."""
    if not 0<=pair<=0xfffff:return None
    return ((pair&0xffff)<<1) | (((pair>>16)&0xf)<<17)


def indirect_status(pair, writes,fw, target):
    if any(i.mnemonic in C.CALLS or
           {'r10','r11'} & X.written_registers(i) or
           i.mnemonic in X.MEMORY_UNSUPPORTED for i in writes):
        return "UNRESOLVED_CLOBBER"
    return "PROVEN_UNDER_LOCAL_CFG_MODEL" if indirect_pc_word(pair)==target and target in fw.insns else "UNRESOLVED"


def e42_check(name):
    p=ROOT/"tools/reports/cr16-e42-parser-reachability.json"
    data=json.loads(p.read_text())
    d=data["images"][name]
    if (d["firmware_sha256"]!=A.REFERENCE_SHA[name] or
        d["dataflow_evidence"]["specific_allocator_generation_to_parser_tag_23"]!="UNRESOLVED"):
        raise ValueError(f"{name}: E4.2 provenance baseline invalid")
    return d


def analyze(name,fw,rows):
    e42_check(name)
    s=S[name];q=Q.S[name];p=fw.insns;edges=C.build(fw)
    E.parser(fw,name)
    text=p[s["literal"]].operands
    import re
    m=re.fullmatch(r"\$0x([0-9a-f]+):l,\(r11,r10\)",text)
    if m is None:raise ValueError("case9 indirect register definition changed")
    pair=int(m.group(1),16)
    if (indirect_pc_word(pair)!=s["c10"] or
        p[s["first"]].operands!="(r11,r10)" or
        p[s["first"]].mnemonic!="jal" or
        p[s["table"]].mnemonic!="movd" or
        p[s["case7_tag"]].operands!="$0x22:m,r2" or
        p[s["case7_state"]].operands!="r4,0x0:s(r3,r2)" or
        p[s["case7_type"]].operands!="r2,0x0:s(r1,r0)" or
        p[s["case7_sub"]].operands!="$0x8:s,0x2:m(r1,r0)" or
        not E.checked(fw,s["case7_copy"],0x28cf4 if name=="normal" else 0x27c64,"call") or
        not E.checked(fw,s["gate"],s["lookup"],"call") or
        p[s["helper_store"]].operands!="r0,0x0:s(r8,r7)"):
        raise ValueError(f"{name}: command effects bytes differ")
    between=[i for a,i in sorted(p.items()) if p[s["literal"]].end<=a<s["first"]]
    if any(b.end!=c.addr for b,c in zip([p[s["literal"]],*between],[*between,p[s["first"]]])):
        raise ValueError("case9 instruction gap before first indirect call")
    incoming=[e for e in edges if e.dst==s["first"] and e.kind!="call"]
    if len(incoming)!=1 or incoming[0].src!=s["first"]-2 or incoming[0].kind!="fallthrough":
        raise ValueError("case9 first indirect call has unexpected direct entry")
    status=indirect_status(pair,between,fw,s["c10"])
    if status!="PROVEN_UNDER_LOCAL_CFG_MODEL":
        raise ValueError(f"{name}: case9 first target lost")
    later=[]
    for addr in s["later"]:
        if p[addr].mnemonic!="jal" or p[addr].operands!="(r11,r10)":
            raise ValueError("later indirect site changed")
        later.append({"site":T.cite(fw,addr),"target":"UNRESOLVED_CLOBBER_AFTER_PRIOR_CALL"})
    limits=["E4.2: no producer-backed parser tag-0x23 path proved",
        "indirect entries and queue/header aliases unexcluded",
        "unknown external control, memory target range, interrupt interleaving"]
    def base(sites,cfg,flow,unknown=None):
        return Q.base(name)|dict(instruction_provenance=[T.cite(fw,a) for a in sites],
            cfg_evidence=cfg,dataflow_evidence=flow,unresolved_paths=unknown or limits)
    c7=base([q["cases"][0],s["case7_tag"],q["case7_build"][0],s["case7_state"],
             s["case7_type"],s["case7_sub"],s["case7_copy"]],
        {"selected_case":T.cite(fw,q["cases"][0]),
         "helper":f"0x{q['case7_build'][0]-0x1a:06x}"},
        {"incoming_pointer":"payload+3, producer unknown", "incoming_length":"payload+7, producer unknown",
         "outgoing_header_tag":"0x22", "outgoing_state":"0x23 at item+2",
         "new_payload":"0xfff1 subtype 8, pointer and length, then copied bytes",
         "next_consumer":"UNRESOLVED; not proved parser's 0x23 branch",
         "recursive_parser_entry":"NOT_PROVEN"})
    c9=base([q["cases"][1],q["case_calls"][1],s["c9"],s["literal"],
             s["table"],s["first"],*s["later"],s["c10"]],
        {"first_indirect_site":T.cite(fw,s["first"]),
         "source_literal":T.cite(fw,s["literal"]),
         "first_target":T.cite(fw,s["c10"]),
         "first_target_confidence":status,
         "ISA_basis":"CR16B Programmer's Reference Manual §JAL (PC bit0=0, pair low16→bits1..16, high4→bits17..20); SC14448 compatibility assumption",
         "later_sites":later},
        {"pair_word_address":f"0x{pair:05x}",
         "pc_byte_address":f"0x{indirect_pc_word(pair):06x}",
         "first_call_register_preservation":"no r10/r11 write or call between literal and first JAL",
         "table_base":p[s["table"]].operands,
         "input_from_case9":"load pointer32 from payload+3; use low word as helper index",
         "first_target_effect":"case10 helper conditional effects; source table/data pointers unresolved"},
        limits+["r10:r11 preservation after first JAL not proved; no subsequent target promoted"])
    bounds=[p[s["cmp1"]].operands,p[s["cmp2"]].operands]
    if bounds!=(["$0x12:m,r7","$0x17:m,r3"] if name=="normal" else
                ["$0xc:s,r7","$0x11:m,r3"]):
        raise ValueError(f"{name}: case10 comparisons differ")
    # The helper's final write is to an indexed in-image RAM candidate,
    # but a call can change r0 and other registers before it reaches store.
    c10=base([q["cases"][2],q["case_calls"][2],s["cmp1"],s["cmp2"],
              s["gate"],s["lookup"],s["helper"],s["helper_store"]],
        {"bounds_comparisons":[T.cite(fw,a) for a in (s["cmp1"],s["cmp2"])],
         "lookup_call":T.cite(fw,s["gate"]),
         "helper_call_after_lookup":"0x278e8" if name=="normal" else "0x00372e"},
        {"first_comparison":bounds[0],"second_comparison":bounds[1],
         "local_direct_calls":[f"0x{s['lookup']:06x}",f"0x{s['helper']:06x}"],
         "selected_helper_store":T.cite(fw,s["helper_store"]),
         "state_effect":"conditional indexed RAM store only; actual address/value need callee and branch proof",
         "version_equivalence":"NOT_PROVEN"})
    c13=base([q["cases"][3],*q["case13"]],
        {"conditional_case":T.cite(fw,q["cases"][3]),"parser_producer_path":"UNRESOLVED"},
        {"pointer_source":"payload+3 from unproved parser input",
         "value_source":"payload+7, 16-bit", "selected_store":T.cite(fw,q["case13"][2]),
         "candidate_targets":[],"reachable_address_range":"TARGET_RANGE_UNRESOLVED",
         "physical_MMIO_effect":"NOT_PROVEN","external_control":"NOT_PROVEN"})
    effect=base([*q["cases"],s["first"],s["helper_store"],q["case13"][2]],
        {"handler_entry_condition":"item+3==0x23 and payload+0==0xfff1; producer path UNRESOLVED",
         "cases_conditional":True},
        {"case7":"new item tag0x22/state0x23",
         "case9_first_indirect_target":f"0x{s['c10']:06x} under CR16B model",
         "case10":"bounded compare/lookup and conditional RAM store helper",
         "case13":"symbolic pointer16 store; target unresolved",
         "command_to_TX":"UNRESOLVED","DSP_DIP_PCM_GPIO":"UNRESOLVED"})
    states=base([q["cases"][0],s["case7_state"],s["helper_store"],q["case13"][2]],
        {"conditional_edges":["case7→new queue item", "case9→case10 helper (first indirect call)",
              "case10→lookup/helper RAM store candidate", "case13→pointer write"]},
        {"producer_backed_edges":[],"known_RAM_transition":"case7 writes item+2=0x23 (local, conditional)",
         "unknown_state_destinations":["case10 helper indexed RAM", "case13 pointer"],
         "DSP_DIP_PCM_GPIO_link":"UNRESOLVED"})
    unresolved=base([s["first"],*s["later"],q["case13"][2]],
        {"first_case9_target_under_model":f"0x{s['c10']:06x}"},
        {"later_indirect":"UNRESOLVED_CLOBBER","case13_target":"UNRESOLVED",
         "runtime_command_reachability":"UNRESOLVED","new_indirect_targets_under_model":1},limits)
    return effect,c7,c9,c10,c13,states,unresolved


def build(objdump):
    A._validate_inputs(objdump)
    data=[{} for _ in NAMES]
    for name,path in A.IMAGES:
        df,fw,rows=D.run_image(name,path,objdump)
        if df.get("converged") is not True or df.get("analysis_status")!="CONVERGED":
            raise ValueError(f"{name}: NON_CONVERGED")
        for d,v in zip(data,analyze(name,fw,rows)):d[name]=v
    if any(set(d)!=set(A.REFERENCE_SHA) for d in data):raise ValueError("incomplete E4.3 bundle")
    return {fn:{"tool":"cr16-command-effects/1","images":d} for fn,d in zip(NAMES,data)}


def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument("--objdump",default=str(A.OBJDUMP))
    ap.add_argument("--out",default=str(ROOT/"tools/reports"));args=ap.parse_args(argv)
    try:T.publish(Path(args.out),build(args.objdump))
    except (OSError,ValueError,KeyError,TypeError) as exc:
        out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
        (out/"cr16-e43.incomplete.json").write_text(json.dumps({"analysis_status":"INCOMPLETE",
             "reason":str(exc)},indent=2)+"\n")
        print(f"INCOMPLETE E4.3: {exc}",file=sys.stderr);return 1
    return 0


if __name__=="__main__":raise SystemExit(main())
