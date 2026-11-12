#!/usr/bin/env python3
"""E4.2: bounded offline backward slice of allocator r2; no firmware execution.

Constants at a call are *not* a proof that the same item reaches the parser:
an unknown writer, wrap, failed allocation or an alternate parser entry kills
that inference. Branch predicates are not interpreted by this slicer.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import cr16_address_spaces as A
import cr16_architecture as E
import cr16_cfg as C
import cr16_dataflow as D
import cr16_dip_trace as T
import cr16_queue_trace as Q
import cr16_peripheral_xrefs as X

ROOT=Path(__file__).resolve().parent.parent
NAMES=tuple("cr16-e42-"+x+".json" for x in (
    "allocator-callers", "tag-provenance", "header-aliases",
    "parser-reachability", "type-producers", "unresolved-paths"))
LEAF={"p2test": 0x2327a}


def predecessors(edges):
    pred=defaultdict(list)
    for e in edges:
        if e.dst is not None and e.kind in ("fallthrough","cond","jump") and e.category==C.DIRECT_RESOLVED:
            pred[e.dst].append(e)
    return pred


def slice_reg(fw, pred, site, reg="r2", *, summaries=None, max_states=2000):
    """May-path backward proof; unmodelled flags/entries cannot prove absence.

    Summaries are explicit checked leaf stubs, not a guessed ABI. A real
    branch path without a matching definition returns an unknown origin.
    """
    summaries=summaries or {}
    todo=[(site,reg,())];seen=set();results=[]
    while todo:
        addr,wanted,trail=todo.pop()
        if (addr,wanted) in seen:
            results.append(("UNKNOWN_CYCLE",None,trail));continue
        seen.add((addr,wanted))
        if len(seen)>max_states:
            results.append(("UNKNOWN_LIMIT",None,trail));break
        incoming=pred.get(addr,())
        if not incoming:
            results.append(("UNKNOWN_ENTRY",None,trail));continue
        for edge in incoming:
            a=edge.src;i=fw.insns[a];path=trail+(a,)
            if i.mnemonic in C.CALLS:
                matched=next((e.dst for e in C.classify_insn(i,fw) if e.kind=="call" and e.category==C.DIRECT_RESOLVED),None)
                summ=summaries.get((matched,wanted))
                if summ is not None:
                    results.append(("CONST_LEAF_RETURN",summ,path+(matched,)))
                else:
                    results.append(("UNKNOWN_CALL_CLOBBER",None,path))
                continue
            if i.mnemonic in X.MEMORY_UNSUPPORTED or i.mnemonic in ("pop","popret"):
                results.append(("UNKNOWN_CLOBBER",None,path));continue
            if wanted not in X.written_registers(i):
                todo.append((a,wanted,path));continue
            m=re.fullmatch(r"\$(-?0x[0-9a-f]+|-?\d+):?[sm]?,(r\d+)",i.operands)
            if i.mnemonic in ("movb","movw") and m and m.group(2)==wanted:
                results.append(("CONST",int(m.group(1),0)&0xff,path));continue
            m=re.fullmatch(r"(r\d+),(r\d+)",i.operands)
            if i.mnemonic in ("movb","movw") and m and m.group(2)==wanted:
                todo.append((a,m.group(1),path));continue
            if i.mnemonic.startswith("load"):
                results.append(("UNKNOWN_MEMORY_SOURCE",None,path));continue
            results.append(("UNKNOWN_COMPUTATION",None,path))
    return results


def classify(origins):
    if not origins:return "TAG_SOURCE_UNKNOWN"
    constants=[v for kind,v,_ in origins if kind.startswith("CONST")]
    unknown=len(constants)!=len(origins)
    if unknown:
        return "TAG_23_POSSIBLE" if 0x23 in constants else "TAG_SOURCE_UNKNOWN"
    if 0x23 in constants:
        return "TAG_23_PROVEN" if set(constants)=={0x23} else "TAG_23_POSSIBLE"
    return "TAG_23_EXCLUDED_UNDER_MODEL"


def tag_at_parser(allocator_tag, writes, *, same_generation=False,
                  known_consumer=False, complete_aliases=False):
    """Fixture/proof gate: never upgrade an allocator tag without item identity.

    Each write carries an offset relative to the *item* (or None if an alias
    is unknown) and an optional byte. Global RAM writes have scope='global'.
    Unknown DMA/IRQ writers must be supplied as item-scope unknown aliases.
    """
    if not (same_generation and known_consumer and complete_aliases):
        return "UNRESOLVED"
    tag=allocator_tag
    for w in writes:
        if w.get("scope")=="global":continue
        if w.get("offset") is None or w.get("width",1)>1 and w.get("offset",0)<=3<w.get("offset",0)+w["width"]:
            return "UNRESOLVED"
        if w["offset"]==3:
            tag=w.get("byte")
    if tag is None:return "UNRESOLVED"
    return "TAG_23_PROVEN" if tag==0x23 else "TAG_23_EXCLUDED_UNDER_MODEL"


def leaf_summary(fw,edges,name):
    """Only this explicit three-instruction leaf may define r2 across a call."""
    if name not in LEAF:return {},[]
    a=LEAF[name];sites=(a,a+2,a+6)
    p=fw.insns
    if ([p[x].mnemonic for x in sites]!=["movw","movb","jump"] or
        p[a].operands!="$0xf:s,r3" or p[a+2].operands!="$0x14:m,r2" or
        p[a+6].operands!="(ra)" or any(p[x].end!=y for x,y in zip(sites,sites[1:])) or
        any(e.dst in sites[1:] and e.category==C.DIRECT_RESOLVED and e.src not in sites
            for e in edges)):
        raise ValueError("p2test: candidate leaf r2 return not isolated")
    return {(a,"r2"):0x14},[T.cite(fw,x) for x in sites]


def report(name,fw,rows):
    s=Q.S[name];p=fw.insns;edges=C.build(fw);pred=predecessors(edges)
    # No promotion if any of E4.1's checked queue or parser bytes changed.
    E.parser(fw,name)
    sources,leaf=leaf_summary(fw,edges,name)
    sites=Q.call_edges(edges,s["alloc"])
    if len(sites)!=(22 if name=="normal" else 19):
        raise ValueError(f"{name}: direct allocator caller inventory changed")
    calls=[];local_refs=[]
    for site in sites:
        origins=slice_reg(fw,pred,site,summaries=sources)
        if not origins:raise ValueError(f"{name}: empty tag slice at {site:x}")
        refs=sorted({a for _,_,trail in origins for a in trail if a in p})
        local_refs.extend(refs)
        calls.append({"call":T.cite(fw,site),"tag_status_at_allocator_entry":classify(origins),
            "possible_constant_values":[f"0x{x:02x}" for x in sorted({v for k,v,_ in origins if v is not None})],
            "definitions":[{"kind":k,"value":f"0x{v:02x}" if v is not None else None,
                "path_reversed":[T.cite(fw,a) for a in trail if a in p]}
                for k,v,trail in origins],
            "conditions":"BRANCH_CONSTRAINTS_UNMODELLED",
            "header_to_parser":"UNRESOLVED"})
    if len({c["call"]["instruction"] for c in calls})!=len(sites):
        raise ValueError("duplicate caller sites")
    # Crucial field distinction: case7 writes payload-2 => item+2, NOT tag.
    new_item=s["case7_build"][0];field_write=new_item+0xa
    if not (p[new_item-4].operands=="$0x22:m,r2" and
        E.checked(fw,new_item,s["alloc"],"call") and
        [p[a].operands for a in (new_item+4,new_item+6,field_write)]==[
            "(r1,r0),(r3,r2)","$0xfffe:m,(r3,r2)","$0x23:m,r4"] and
        p[field_write+4].operands=="r4,0x0:s(r3,r2)"):
        raise ValueError(f"{name}: case7 item+2 rewrite model changed")
    # Also verify the ordinary queue tag copy into global state, distinct
    # from a store into the queued header.
    main_tag=s["item_len"]+2
    global_write=main_tag+2
    if (p[main_tag].operands!="0x3:s(r8,r7),r0" or
        p[global_write].operands!=f"r0,0x{E.S[name]['ram'][-1]:x}:l"):
        raise ValueError(f"{name}: main global-tag copy changed")
    by_tags=defaultdict(list)
    for c in calls:
        for val in c["possible_constant_values"]:
            by_tags[val].append(c["call"]["instruction"])
    common=Q.base(name)
    common["analysis_status"]="CONVERGED_BOUNDED_PATHS"
    unres=["indirect caller and non-adjacent input paths not globally enumerated",
        "branch conditions, unknown calls and unsupported memory aliases",
        "queue wrap/overwrite/interrupt generation prevents record identity proof"]
    make=lambda refs,cfg,flow,limits: common|dict(instruction_provenance=[T.cite(fw,x) for x in sorted(set(refs))],
        cfg_evidence=cfg,dataflow_evidence=flow,unresolved_paths=limits)
    callers=make([s["alloc"],s["alloc_header"][-1],*sites,*local_refs,*[int(x["instruction"],16) for x in leaf]],
        {"direct_callers":len(sites),"parser_direct_callers":
            [T.cite(fw,x) for x in Q.call_edges(edges,s["parser"])],
            "leaf_summary_site":leaf},
        {"entry_abi":"r2 low byte -> r11 at allocator+4; r3 word -> r8 payload length",
            "callers":calls},unres)
    tags=make([s["alloc"]+4,s["alloc_header"][-1],main_tag,global_write,*local_refs],
        {"all_direct_callers_sliced":len(calls)==len(sites)},
        {"at_allocator_entry":{x:sum(c["tag_status_at_allocator_entry"]==x for c in calls)
             for x in ("TAG_23_PROVEN","TAG_23_POSSIBLE","TAG_23_EXCLUDED_UNDER_MODEL","TAG_SOURCE_UNKNOWN")},
         "constant_tag_sites":dict(sorted(by_tags.items())),"branch_predicates":"UNMODELLED",
         "global_state":"main copies item+3 -> global; dispatcher may write 0x23 to global, not item"},unres)
    # A broad candidate inventory (not an alias proof): stores to +2/+3 of
    # arbitrary pointer pairs; aliases and typed overlapping writes remain.
    candidates=[r for r in rows if r["operation"] in ("WRITE","RMW") and
        re.search(r"0x[23]:[sm]\(r\d+,r\d+\)",p[int(r["instruction"],16)].operands)]
    aliases=make([s["alloc_header"][2],s["alloc_header"][3],field_write+4,
        main_tag,global_write,*[int(r["instruction"],16) for r in candidates]],
        {"candidate_store_displacements_2_or_3":len(candidates),
         "candidate_stores": [{"site":T.cite(fw,int(r["instruction"],16)),
                "effective_address":r["effective_address"],"address_kind":r["address_kind"]}
                for r in candidates]},
        {"case7_store":"payload-2=item+2 (state); tag item+3 remains allocator r2=0x22 on this selected path",
         "dispatcher_store":"separate global RAM",
         "header_tag_post_allocation":"UNKNOWN_ALL_PATHS"},
        ["candidate stores not equated to item+3 without pair/alias and lifetime proof",
         "unresolved memcpy, wider overlapping writes, interrupts and DMA"])
    parsed=Q.call_edges(edges,s["parser"])
    reach=make([s["alloc_header"][-1],main_tag,global_write,s["dispatch_call"],E.S[name]["sync"],
        field_write+4],
        {"parser_direct_callers":[T.cite(fw,a) for a in parsed],
         "direct_call_site_to_parser":E.checked(fw,s["dispatch_call"],s["parser"],"call"),
         "tag_23_branch":T.cite(fw,E.S[name]["sync"]+4)},
        {"allocator_to_item_tag":"PROVEN_UNDER_LOCAL_CFG_MODEL",
         "item_to_main_tag_global":"PROVEN_UNDER_LOCAL_CFG_MODEL",
         "main_to_dispatch_to_parser":"PROVEN_UNDER_LOCAL_CFG_MODEL",
         "specific_allocator_generation_to_parser_tag_23":"UNRESOLVED",
         "case7_subtype8_entry_tag":"0x22 (not 0x23) on selected construction path",
         "alternative_parser_entry":"no other resolved direct caller; indirect callers not excluded",
         "global_0x23_is_not_item_tag":True},unres)
    types=make([new_item-4,new_item,field_write+4,*s["case7_build"][1:],
        E.S[name]["types"][0],E.S[name]["types"][1]],
        {"selected_internal_type_constructor":T.cite(fw,new_item),
         "type_consumption_requires_tag_0x23":True},
        {"case7_new_type":"0xfff1, subtype 8, tag 0x22 and state 0x23 on selected path",
         "case7_to_parser_type_branch":"UNRESOLVED; tag 0x22 fails selected 0x23 comparison absent rewrite",
         "0x0167_producer":"UNRESOLVED", "0xfff1_parser_input":"UNRESOLVED",
         "unsupported_subtype":"parser takes default return on selected branch; subtype 8 not a named case"},
        ["global type producer/writer coverage incomplete", "parser subtype 8 cannot be assumed processed"])
    boundaries=make([s["alloc"],s["alloc_header"][-1],main_tag,E.S[name]["sync"],
        field_write+4],{"no_global_unreachability_claim":True},
        {"parser_tag_23_status":"NOT_PROVEN; NOT_EXCLUDED",
         "record_identity_through_wrap":"UNRESOLVED",
         "new_indirect_targets_resolved":0},unres)
    return callers,tags,aliases,reach,types,boundaries


def build(objdump):
    A._validate_inputs(objdump)
    data=[{} for _ in NAMES]
    for name,path in A.IMAGES:
        df,fw,rows=D.run_image(name,path,objdump)
        if df.get("analysis_status")!="CONVERGED" or df.get("converged") is not True:
            raise ValueError(f"{name}: NON_CONVERGED")
        for d,v in zip(data,report(name,fw,rows)):
            d[name]=v
    if any(set(d)!=set(A.REFERENCE_SHA) for d in data):raise ValueError("incomplete E4.2 bundle")
    return {fn:{"tool":"cr16-queue-provenance/1","images":d} for fn,d in zip(NAMES,data)}


def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--objdump",default=str(A.OBJDUMP))
    ap.add_argument("--out",default=str(ROOT/"tools/reports"))
    args=ap.parse_args(argv)
    try:T.publish(Path(args.out),build(args.objdump))
    except (OSError,KeyError,ValueError,TypeError) as exc:
        out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
        (out/"cr16-e42.incomplete.json").write_text(json.dumps({"analysis_status":"INCOMPLETE",
             "reason":str(exc)},indent=2)+"\n")
        print(f"INCOMPLETE E4.2: {exc}",file=sys.stderr)
        return 1
    return 0


if __name__=="__main__":raise SystemExit(main())
