#!/usr/bin/env python3
"""Offline bounded SC14448 function/ISR/command architecture evidence.

Direct call targets seed function CANDIDATES; branch targets do not. A
single-entry closed local region can have a locally confirmed boundary, but
indirect entries and runtime hardware behavior are never inferred away.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import cr16_address_spaces as A
import cr16_cfg as C
import cr16_dataflow as D
import cr16_dip_trace as T

ROOT = Path(__file__).resolve().parent.parent
NAMES = tuple("cr16-e4-" + name + ".json" for name in (
    "function-map", "normal-p2test-matches", "uart-runtime",
    "command-dispatch", "state-variables", "interrupt-architecture",
    "shared-memory", "subsystem-graph", "unresolved-boundaries"))
S = {
    "normal": dict(start=0x15aa, main=0x39f8, dispatch=0x39d6,
        dispatch_call=0x39f2, parser=0x9e68, sync=0x9e76,
        types=(0x9e94, 0x9e9a), sub=(0x9ebc, 0x9ec0, 0x9ec6, 0x9eca),
        sub_edges=((0x9ebe,0x9ed0),(0x9ec4,0x9eea),
                   (0x9ec8,0x9ef6),(0x9ecc,0x9ede)),
        tx=0x9f84, tx_call=0x3a62, tx_data=0x9fb8,
        tx_ack=0x9fc0, tx_status=0x9fd6,
        rx_vector=0x28dca, dsp=0x28a94, dip=0x28cd0,
        timer=0x28996, queue=(0xda, 0xde),
        queue_base_sites=(0x3a42,0x3a48),
        ram=(0x9374, 0x9376, 0x9378, 0x937a, 0x93cb),
        queue_poll=0x3a6a, queue_dispatch=0x3abe, queue_pop=0x3ad6,
        dsp_helper=(0x3b28,0x3b38), dip_writer=0x2618),
    "p2test": dict(start=0x1026, main=0x27112, dispatch=0x270e8,
        dispatch_call=0x2710c, parser=0x2746a, sync=0x27478,
        types=(0x27496, 0x2749c), sub=(0x274be,0x274c2,0x274c8,0x274cc),
        sub_edges=((0x274c0,0x274d2),(0x274c6,0x274ec),
                   (0x274ca,0x274f8),(0x274ce,0x274e0)),
        tx=0x9bc8, tx_call=0x27180, tx_data=0x9bfc,
        tx_ack=0x9c04, tx_status=0x9c1a,
        rx_vector=0x9ffc, dsp=0x27914, dip=0x27c88,
        timer=0x2772a, queue=(0xda,0xde),
        queue_base_sites=(0x27160,0x27166),
        ram=(0x94ac,0x94ae,0x94b0,0x94b2,0x9512),
        queue_poll=0x27188, queue_dispatch=0x271dc, queue_pop=0x271f4,
        dsp_helper=(0x27744,0x27754), dip_writer=0x1ed4),
}
VECTOR_REPORT = ROOT / "tools/reports/cr16-vector-map.json"


def cite(fw, a):
    return T.cite(fw, a)


def report_base(name):
    return dict(image=name, firmware_sha256=A.REFERENCE_SHA[name],
        analysis_status="CONVERGED_BOUNDED_PATHS", instruction_provenance=[],
        cfg_evidence={}, dataflow_evidence={}, confidence="PARTIALLY_PROVEN",
        unresolved_paths=[])


def function_seed(edge):
    return edge.kind == "call" and edge.category == C.DIRECT_RESOLVED and edge.dst is not None


def region(entry, fw, by_src, seeds, limit=1200):
    """Traverse local CFG, skipping call edges but retaining return sites."""
    reached, todo, exits, unknown, overlaps = set(), [entry], set(), set(), set()
    while todo and len(reached) < limit:
        a = todo.pop()
        if a in reached:
            continue
        if a != entry and a in seeds:
            overlaps.add(a)
            continue
        if a not in fw.insns:
            unknown.add(a)
            continue
        reached.add(a)
        i = fw.insns[a]
        if i.mnemonic in C.RETS or (i.mnemonic == "jump" and i.operands == "(ra)"):
            exits.add(a)
            continue
        outs = [e for e in by_src.get(a, ()) if e.kind != "call"]
        if not outs:
            unknown.add(a)
        for e in outs:
            if e.category != C.DIRECT_RESOLVED or e.dst is None:
                unknown.add(a)
            else:
                todo.append(e.dst)
    if todo:
        unknown.add("BOUND_EXCEEDED")
    return reached, exits, unknown, overlaps


def discover(fw, rows, edges, vectors, name):
    by_src = defaultdict(list)
    callers = defaultdict(set)
    for e in edges:
        by_src[e.src].append(e)
        if function_seed(e):
            callers[e.dst].add(e.src)
    vector_entries = {int(v["handler_address"], 16) for v in vectors
                      if v["handler"]["in_image"]}
    seeds = set(callers) | vector_entries | {S[name]["main"]}
    rows_by_site = defaultdict(list)
    for r in rows:
        rows_by_site[int(r["instruction"], 16)].append(r)
    funcs = []
    for entry in sorted(seeds):
        if entry not in fw.insns:
            continue
        reached, exits, unknown, overlap = region(entry, fw, by_src, seeds)
        if not reached:
            continue
        insn = fw.insns[entry]
        local = [r for a in reached for r in rows_by_site[a]
                 if r["operation"] in ("READ", "WRITE", "RMW")]
        callees = sorted({e.dst for a in reached for e in by_src[a]
                          if function_seed(e)})
        indirect = sorted({a for a in reached for e in by_src[a]
                            if e.category in (C.INDIRECT_REGISTER, C.INDIRECT_UNRESOLVED)})
        # A prologue and *closed* local CFG are necessary, not sufficient
        # for global function identity. All candidates retain unknown entries.
        closed = bool(exits) and not unknown and not overlap and not indirect
        status = ("CONFIRMED_FUNCTION" if closed and insn.mnemonic == "push"
                  and entry in callers else "OVERLAPPING_CODE" if overlap
                  else "CFG_FUNCTION_CANDIDATE")
        clusters=[]
        if entry in vector_entries:
            clusters.append({"group":"INTERRUPT_HANDLING",
                "basis":"verified vector target only; source trigger unresolved"})
        if entry==S[name]["parser"] or entry==S[name]["dispatch"]:
            clusters.append({"group":"COMMAND_DISPATCH",
                "basis":"selected direct call and command comparisons"})
        if entry==S[name]["tx"]:
            clusters.append({"group":"UART_COMMUNICATION",
                "basis":"bounded byte store at architectural 0x00ff4902"})
        if entry==S[name]["main"]:
            clusters.append({"group":"INITIALIZATION",
                "basis":"startup-linked main entry with initialization calls"})
        if not clusters:
            clusters.append({"group":"UNKNOWN","basis":"no instruction-level role proof"})
        funcs.append(dict(entry=f"0x{entry:06x}",
            estimated_end=f"0x{max(reached):06x}",
            boundary_status=status, boundary_scope="LOCAL_CFG_ONLY",
            first_instruction=cite(fw, entry),
            callers=[f"0x{x:06x}" for x in sorted(callers[entry])],
            callees=[f"0x{x:06x}" for x in callees],
            indirect_calls=[f"0x{x:06x}" for x in indirect],
            memory_reads=[r["instruction"] for r in local if r["operation"] == "READ"],
            memory_writes=[r["instruction"] for r in local if r["operation"] in ("WRITE","RMW")],
            mmio_accesses=[{"site": r["instruction"], "address": r["effective_address"],
                "operation":r["operation"]} for r in local if r["effective_address"] and
                r["effective_address"].startswith("0x00ff")],
            interrupt_context=[v["index"] for v in vectors
                if int(v["handler_address"],16)==entry],
            stack_usage="prologue push" if insn.mnemonic=="push" else "UNKNOWN",
            clusters=clusters,
            cfg_instruction_count=len(reached),
            exits=[f"0x{x:06x}" for x in sorted(exits)],
            unknown_exits=[str(x) for x in sorted(unknown, key=str)],
            overlapping_entries=[f"0x{x:06x}" for x in sorted(overlap)],
            confidence="PROVEN_UNDER_CFG_MODEL" if status=="CONFIRMED_FUNCTION" else "CANDIDATE"))
    return funcs


def fingerprint(fw, addr, count=12):
    """Structural candidate only: never equate functions on a short prefix."""
    items = [i for a, i in sorted(fw.insns.items()) if a >= addr][:count]
    if len(items) != count or any(items[j].end != items[j+1].addr for j in range(count-1)):
        return None
    return tuple((i.mnemonic, re.sub(r"(?:0x[0-9a-f]+|\$-?\d+)", "#", i.operands))
                 for i in items)


def match(f1, f2, funcs1, funcs2):
    def index(fw, funcs):
        m=defaultdict(list)
        for r in funcs:
            key=fingerprint(fw,int(r["entry"],16))
            if key:m[key].append(r["entry"])
        return m
    x,y=index(f1,funcs1),index(f2,funcs2)
    return [{"normal":x[k][0],"p2test":y[k][0],"confidence":"CFG_PREFIX_CANDIDATE",
             "note":"12-instruction structural prefix only; not semantic equivalence"}
            for k in sorted(x) if len(x[k])==len(y.get(k,[]))==1]


def verified_vectors(fw, name, record):
    if record.get("parse_errors"):
        raise ValueError(f"{name}: invalid vector source")
    vectors=record["vectors"]
    if len(vectors)!=31:
        raise ValueError(f"{name}: incomplete vectors")
    for v in vectors:
        off=int(v["table_address"],16)
        run=fw.run_of(off)
        if not run or off+4>run[0]+len(run[1]):
            raise ValueError(f"{name}: vector not in image")
        raw=run[1][off-run[0]:off-run[0]+4]
        if (raw.hex()!=v["raw"] or int.from_bytes(raw,"little")*2!=
                int(v["handler_address"],16)):
            raise ValueError(f"{name}: vector {v['index']} raw mismatch")
    return vectors


def checked(fw, src, dst, kind=None):
    return any(e.dst==dst and e.category==C.DIRECT_RESOLVED and
               (kind is None or e.kind==kind) for e in C.classify_insn(fw.insns[src],fw))


def parser(fw,name):
    s=S[name];p=fw.insns
    if (p[s["parser"]].mnemonic!="push" or
        p[s["sync"]].operands!="$0x23:m,r5" or
        [p[a].operands for a in s["types"]]!=["$0x167:m,r2","$0xfff1:m,r2"] or
        [p[a].operands for a in s["sub"]]!=
            ["$0x7:s,r2","$0x9:m,r2","$0xa:s,r2","$0xd:s,r2"] or
        not checked(fw,s["dispatch_call"],s["parser"],"call") or
        not checked(fw,s["types"][0]+4,s["types"][1]+8,"cond") or
        not all(checked(fw,a,b,"cond") for a,b in s["sub_edges"])):
        raise ValueError(f"{name}: command comparisons/edges changed")
    return {"entry":cite(fw,s["parser"]),
        "direct_caller":cite(fw,s["dispatch_call"]),
        "sync_byte_comparison":cite(fw,s["sync"]),
        "type_comparisons":[cite(fw,a) for a in s["types"]],
        "subcommand_comparisons":[cite(fw,a) for a in s["sub"]],
        "subcommand_targets":[{"id":n,"branch":cite(fw,src),
            "target":cite(fw,dst),"label":"UNNAMED_COMMAND"}
            for n,(src,dst) in zip((7,9,10,13),s["sub_edges"])],
        "type_values":["0x0167","0xfff1"],"subcommand_values":[7,9,10,13],
        "payload_offsets":["type @ +0; subcommand @ +2; arguments @ +3/+4/+7 on selected paths"],
        "source":"queue item pointer from main loop; UART RX provenance UNKNOWN",
        "command_semantics":"UNRESOLVED"}


def one_image(name,fw,rows,vectors,edges):
    s=S[name];p=fw.insns
    functions=discover(fw,rows,edges,vectors,name)
    ps=parser(fw,name)
    v20,v21=vectors[20],vectors[21]
    if (int(v20["handler_address"],16)!=s["rx_vector"] or
        v20["handler_address"]!=v21["handler_address"] or
        [p[a].mnemonic for a in (s["rx_vector"],s["rx_vector"]+2)]!=["nop","retx"] or
        not checked(fw,s["tx_call"],s["tx"],"call") or
        p[s["tx_data"]].operands!="r0,0xf4902:m" or
        p[s["tx_ack"]].operands!="r0,0xf4904:m" or
        p[s["tx_status"]].operands!="$0x5:s,0xf4900:m" or
        not checked(fw,s["queue_dispatch"],s["dispatch"],"call")):
        raise ValueError(f"{name}: UART/vector/main queue chain differs")
    if ([p[a].operands for a in s["queue_base_sites"]] !=
        ["$0xda:l,(r12)","$0xde:l,(r10,r9)"] or
        [p[a].mnemonic for a in (s["queue_poll"],s["queue_pop"])]!=
        ["loadd","stord"]):
        raise ValueError(f"{name}: queue base/poll/pop chain differs")
    func=report_base(name)|dict(instruction_provenance=[cite(fw,s["main"]),
        cite(fw,s["parser"]),cite(fw,s["tx"])],
        cfg_evidence={"function_candidates":len(functions),
            "closed_local_boundaries":sum(f["boundary_status"]=="CONFIRMED_FUNCTION" for f in functions),
            "direct_call_targets_only":True},
        dataflow_evidence={"functions":functions},
        unresolved_paths=["entry from indirect call/table may overlap local regions",
            "estimated_end is last reached address, not layout boundary",
            "call return/clobber paths not interprocedurally closed"])
    uart=report_base(name)|dict(instruction_provenance=[cite(fw,a) for a in
        (s["rx_vector"],s["rx_vector"]+2,s["tx"],s["tx_data"],s["tx_ack"],s["tx_status"])],
        cfg_evidence={"vector_RX":v20,"vector_TX":v21,
            "uart_rx_tx_vectors_point_to_same_nop_retx":True,
            "main_to_tx": [f"0x{s['tx_call']:06x}",f"0x{s['tx']:06x}"],
            "first_level_uart_boot_protocol_separate":True},
        dataflow_evidence={"tx_queue_index_cells": [f"0x{x:04x}" for x in s["ram"][1:4]],
            "tx_byte_source":"indexed RAM buffer; byte -> zero extend -> storw 0x00ff4902",
            "tx_registers_architectural":["0x00ff4900","0x00ff4902","0x00ff4904"],
            "rx_peripheral_read_into_runtime_parser":"NOT_ESTABLISHED",
            "runtime_UART_frame":"NOT_ESTABLISHED"},
        unresolved_paths=["UART vectors stubbed; no ISR RX byte path",
            "queue producer is not proved to be UART", "UART boot framing must not transfer to runtime"])
    command=report_base(name)|dict(instruction_provenance=[ps["entry"],
        ps["direct_caller"],ps["sync_byte_comparison"],*ps["type_comparisons"],
        *ps["subcommand_comparisons"]],
        cfg_evidence={"queue_to_dispatch_call":checked(fw,s["queue_dispatch"],s["dispatch"],"call"),
            "dispatch_to_parser_call":True,
            "parser_type_edges":"DIRECT_RESOLVED_SELECTED",
            "parser_input_from_UART":"UNRESOLVED"},dataflow_evidence={"parser":ps},
        unresolved_paths=["parser message length and validation not globally proved",
            "source queue producer/host transport unknown",
            "other handlers, responses and indirect effects unresolved"])
    # selected shared state; global writer/reader inventory uses the
    # converged dataflow rows and does not assert unknown alias exclusion.
    state_rows={}
    for addr in (*s["ram"],*s["queue"]):
        rr=[r for r in rows if r.get("effective_address")==f"0x{addr:08x}" and
            r["operation"] in ("READ","WRITE","RMW")]
        state_rows[f"0x{addr:08x}"]={"readers":[cite(fw,int(r["instruction"],16)) for r in rr if r["operation"]=="READ"],
            "writers":[cite(fw,int(r["instruction"],16)) for r in rr if r["operation"] in ("WRITE","RMW")],
            "initial_value":"UNKNOWN", "indirect_aliases":"NOT_EXCLUDED"}
    state=report_base(name)|dict(instruction_provenance=[cite(fw,a) for a in
        (*s["queue_base_sites"],s["queue_poll"],s["queue_pop"])],
        cfg_evidence={"main_loop":f"0x{s['main']:06x}"},
        dataflow_evidence={"selected_RAM_variables":state_rows,
            "state_transitions":"queue pointers compared; dequeue after callback success on selected path"},
        unresolved_paths=["indirect writers and interrupts not exhaustively resolved"])
    irqs=[]
    for v in vectors:
        a=int(v["handler_address"],16)
        irqs.append({"index":v["index"],"reference_name_candidate":v["reference_name"],
            "handler":v["handler_address"], "vector_raw":v["raw"],
            "first_instruction":cite(fw,a) if a in p else None,
            "actual_hardware_source":"UNRESOLVED",
            "known_stub":a==s["rx_vector"]})
    intr=report_base(name)|dict(instruction_provenance=[cite(fw,a) for a in
        (s["rx_vector"],s["timer"],s["dip"],s["dsp"])],
        cfg_evidence={"vectors_verified_against_raw_image":True,"vectors":irqs},
        dataflow_evidence={"DSP_helpers":[f"0x{x:06x}" for x in s["dsp_helper"]],
            "DIP_indexed_writer":f"0x{s['dip_writer']:06x}",
            "UART_vectors_are_stubs":True},
        unresolved_paths=["timer/dip/dsp numbering is reference analogy",
            "interrupt interleavings and exact scheduling not reconstructed"])
    shared=report_base(name)|dict(instruction_provenance=[cite(fw,a) for a in
        (*s["queue_base_sites"],s["queue_poll"],s["queue_pop"],s["dispatch_call"])],
        cfg_evidence={"main_queue_pointer_pair":[f"0x{x:04x}" for x in s["queue"]],
            "local_dispatch_call":True},
        dataflow_evidence={"selected_cells":state_rows,
            "queue_head_tail":"RAM [0xda] / [0xde] on selected main-loop path",
            "mailbox_or_hardware_DMA":"UNRESOLVED"},
        unresolved_paths=["queue producer and hardware transport unproved",
            "RAM address aliasing/interrupt writers not excluded"])
    graph_edges=[
        {"source":f"0x{s['main']:06x}","destination":f"0x{s['dispatch']:06x}",
         "interaction_type":"DIRECT_CALL","instruction_provenance":cite(fw,s["queue_dispatch"]),
         "confidence":"PROVEN_UNDER_CFG_MODEL"},
        {"source":f"0x{s['dispatch']:06x}","destination":f"0x{s['parser']:06x}",
         "interaction_type":"DIRECT_CALL","instruction_provenance":cite(fw,s["dispatch_call"]),
         "confidence":"PROVEN_BY_SC14448_FIRMWARE"},
        {"source":f"0x{s['main']:06x}","destination":f"0x{s['tx']:06x}",
         "interaction_type":"DIRECT_CALL","instruction_provenance":cite(fw,s["tx_call"]),
         "confidence":"PROVEN_BY_SC14448_FIRMWARE"},
        {"source":f"0x{s['tx']:06x}","destination":"0x00ff4902",
         "interaction_type":"PERIPHERAL_ACCESS","instruction_provenance":cite(fw,s["tx_data"]),
         "confidence":"PROVEN_BY_SC14448_FIRMWARE"}]
    graph=report_base(name)|dict(instruction_provenance=[e["instruction_provenance"] for e in graph_edges],
        cfg_evidence={"edges":graph_edges},
        dataflow_evidence={"DIP_DSP_PCM_UART_RX_links":"UNRESOLVED"},
        unresolved_paths=["main queue producer to host UART not proven",
            "no proven main/parser -> DSP/DIP/PCM/analog FON edge"])
    boundaries=report_base(name)|dict(instruction_provenance=[cite(fw,s["parser"]),
        cite(fw,s["rx_vector"])],cfg_evidence={"confirmed_first_level_handoff":
            "static first-level 0x10284 -> second-level 0x8; runtime unobserved",
            "second_level_start":f"0x{s['start']:06x}",
            "main_loop_entry":f"0x{s['main']:06x}"},
        dataflow_evidence={"primary_blockers":["runtime UART RX vectors are nop/retx",
            "queue producer/host ingress to parser not identified",
            "indirect aliases and cross-subsystem effects incomplete"]},
        unresolved_paths=["0x8 entry has overlapping linear decode; use isolated instruction evidence",
            "runtime physical host link unknown", "FON slot-5 consumer Q75 still open"])
    return func,uart,command,state,intr,shared,graph,boundaries,functions


def build(objdump):
    A._validate_inputs(objdump)
    raw=json.loads(VECTOR_REPORT.read_text())
    images={n:{} for n in NAMES};cache={}
    for name,path in A.IMAGES:
        df,fw,rows=D.run_image(name,path,objdump)
        if df.get("converged") is not True or df.get("analysis_status")!="CONVERGED":
            raise ValueError(f"{name}: NON_CONVERGED")
        vec=verified_vectors(fw,name,raw["images"][name]);edges=C.build(fw)
        f,u,c,st,irq,sh,g,b,functions=one_image(name,fw,rows,vec,edges)
        cache[name]=(fw,functions)
        for fn,part in zip((NAMES[0],*NAMES[2:]),(f,u,c,st,irq,sh,g,b)):
            images[fn][name]=part
    matched=match(cache["normal"][0],cache["p2test"][0],
                  cache["normal"][1],cache["p2test"][1])
    for name,(fw,functions) in cache.items():
        images[NAMES[1]][name]=report_base(name)|dict(
            instruction_provenance=[cite(fw,int(m[name],16)) for m in matched],
            cfg_evidence={"unique_12_instruction_prefix_matches":len(matched),
                "matches":matched},
            dataflow_evidence={"selected_correspondence":{
                "main":f"0x{S[name]['main']:06x}",
                "parser":f"0x{S[name]['parser']:06x}",
                "TX":f"0x{S[name]['tx']:06x}"}},
            confidence="CANDIDATE",
            unresolved_paths=["prefix similarity does not prove semantic equivalence",
                "unique-prefix filtering excludes changed implementations"])
    if any(set(v)!=set(A.REFERENCE_SHA) for v in images.values()):
        raise ValueError("incomplete E4 bundle")
    return {fn:{"tool":"cr16-architecture/1","images":v} for fn,v in images.items()}


def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--objdump",default=str(A.OBJDUMP))
    ap.add_argument("--out",default=str(ROOT/"tools/reports"))
    args=ap.parse_args(argv)
    try:
        T.publish(Path(args.out),build(args.objdump))
    except (OSError,ValueError,KeyError,TypeError) as exc:
        out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
        (out/"cr16-e4.incomplete.json").write_text(json.dumps({
            "analysis_status":"INCOMPLETE","reason":str(exc)},indent=1)+"\n")
        print(f"INCOMPLETE E4: {exc}",file=sys.stderr)
        return 1
    return 0


if __name__=="__main__":
    raise SystemExit(main())
