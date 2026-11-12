#!/usr/bin/env python3
"""Offline bounded SC14448 runtime queue/command/TX provenance (E4.1)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import cr16_address_spaces as A
import cr16_architecture as E
import cr16_cfg as C
import cr16_dataflow as D
import cr16_dip_trace as T
from cr16_boot_memory_map import parse_ihex

ROOT = Path(__file__).resolve().parent.parent
FILES = tuple(f"cr16-e41-{x}.json" for x in (
    "queue-layout", "queue-producers", "item-format", "command-cases",
    "pointer-write", "tx-buffer", "tx-responses", "uart-rx-candidates",
    "subsystem-links", "proof-boundaries"))
S = {
    "normal": dict(alloc=0x386a, alloc_write=0x3888, read_cell=0x388a,
       alloc_header=(0x3920,0x3922,0x3928,0x392a), wrap=0x3896,
       base=0x2fd, limit=0xafb, alloc_copy=0x3934, copy_call=0x394a,
       producer_main=0x9f3a, item_len=0x3a74, dispatch=0x39d6,
       dispatch_global_base=0x39d8, dispatch_marker=0x39f0,
       dispatch_call=0x39f2, parser=0x9e68,
       item_payload=0x3aba, consume=0x3ad6, read_pointer=0xde,
       case13=(0x9ede,0x9ee2,0x9ee6), cases=(0x9ed0,0x9eea,0x9ef6,0x9ede),
       case_calls=(0x9ed8,0x9ef0,0x9efa),
       case7_build=(0x9e2a,0x9e3e,0x9e40,0x9e44,0x9e48),
       case7_stack=0x9e52, case7_copy=0x9e5c,
       case10_limits=(0x278b6,0x278c2),
       tx_base=0xafd, tx=0x9f84, tx_data=0x9fb8, tx_ack=0x9fc0,
       tx_status=0x9fd6, tx_read=0x9376, tx_write=0x9378,
       tx_index=0x937a, tx_buff_store=None, tx_length=0x7f0,
       rxvec=0x28dca),
    "p2test": dict(alloc=0x26f7c, alloc_write=0x26f9a, read_cell=0x26f9c,
       alloc_header=(0x27032,0x27034,0x2703a,0x2703c), wrap=0x26fa8,
       base=0x25d, limit=0xa5b, alloc_copy=0x27046, copy_call=0x2705c,
       producer_main=0x9b7e, item_len=0x27192, dispatch=0x270e8,
       dispatch_global_base=0x270ea, dispatch_marker=0x2710a,
       dispatch_call=0x2710c, parser=0x2746a,
       item_payload=0x271d8, consume=0x271f4, read_pointer=0xde,
       case13=(0x274e0,0x274e4,0x274e8), cases=(0x274d2,0x274ec,0x274f8,0x274e0),
       case_calls=(0x274da,0x274f2,0x274fc),
       case7_build=(0x2742c,0x27440,0x27442,0x27446,0x2744a),
       case7_stack=0x27454, case7_copy=0x2745e,
       case10_limits=(0x3700,0x3708),
       tx_base=0xa5d, tx=0x9bc8, tx_data=0x9bfc, tx_ack=0x9c04,
       tx_status=0x9c1a, tx_read=0x94ae, tx_write=0x94b0,
       tx_index=0x94b2, tx_buff_store=0x9c8c, tx_length=0x7f0,
       rxvec=0x9ffc),
}


def cite(fw, addr):
    return T.cite(fw, addr)


def base(name):
    return dict(image=name, firmware_sha256=A.REFERENCE_SHA[name],
        analysis_status="CONVERGED_BOUNDED_PATHS",instruction_provenance=[],
        cfg_evidence={},dataflow_evidence={},unresolved_indirect_paths=[
            "unresolved indirect entry/call and memory alias may change global coverage"],
        related_device_hypotheses={"SC14441 UART numbering":"RELATED_DEVICE_HINT"},
        confidence="PARTIALLY_PROVEN",unresolved_paths=[])


def call_edges(edges, dst):
    return sorted(e.src for e in edges if e.kind=="call" and e.dst==dst and
                  e.category==C.DIRECT_RESOLVED)


def conditional_value(writes, *, source_known=False, alias_changed=False):
    """Never promote symbolic pointer from an item to an arbitrary target."""
    if not source_known or alias_changed or len(writes)!=1:
        return "TARGET_RANGE_UNRESOLVED"
    return "LOCAL_SINGLE_SOURCE_ONLY"


def queue_status(read,write,*,unknown_writer=False):
    if unknown_writer or read is None or write is None:
        return "UNRESOLVED"
    return "LOCALLY_EQUAL" if read==write else "LOCALLY_NOT_EQUAL"


def item_field(offset, source, *, known_size=None):
    return {"offset":offset,"source":source,
        "bounds":"LENGTH_UNRESOLVED" if known_size is None else
            "WITHIN_LOCAL_ALLOCATION" if offset < known_size else "OUT_OF_BOUNDS"}


def validate(fw,name,edges,mem):
    s=S[name];p=fw.insns
    expected=[("movd",f"$0xda:l,(r13)"),
              ("stord","(r1,r0),0x0:s(r13)"),
              ("movd",f"$0xde:l,(r10,r9)"),
              ("movd",f"$0x{s['base']:x}:l,(r5,r4)"),
              ("cmpd",f"$0x{s['limit']:x}:l,(r1,r0)")]
    sites=[s["alloc"]+0x10,s["alloc_write"],s["read_cell"],s["read_cell"]+6,s["wrap"]]
    if [(p[a].mnemonic,p[a].operands) for a in sites]!=expected:
        raise ValueError(f"{name}: queue pointer/base arithmetic differs")
    if (p[s["alloc"]].mnemonic!="push" or
        [p[a].mnemonic for a in s["alloc_header"]]!=["storw","loadb","storb","storb"] or
        p[s["alloc_header"][0]].operands!="r8,0x0:s(r3,r2)" or
        p[s["alloc_header"][2]].operands!="r0,0x2:s(r3,r2)" or
        p[s["alloc_header"][3]].operands!="r11,0x3:s(r3,r2)" or
        not E.checked(fw,s["copy_call"],0x28cf4 if name=="normal" else 0x27c64,"call") or
        p[s["item_len"]].mnemonic!="loadw" or
        p[s["item_payload"]+2].operands!="$0x4:s,(r3,r2)" or
        p[s["dispatch_marker"]-4].operands!="$0x23:m,r5" or
        p[s["dispatch_global_base"]].operands!=
            f"$0x{E.S[name]['ram'][-1]:x}:l,(r1,r0)" or
        p[s["dispatch_marker"]].operands!="r5,0x0:s(r1,r0)" or
        not E.checked(fw,s["dispatch_call"],s["parser"],"call")):
        raise ValueError(f"{name}: allocator/header/dispatch chain differs")
    # Item header from image is *initial* state only; cannot assume no
    # loader/ISR writes before a selected consumer path.
    for a in (0xda,0xde):
        if any((a+i) not in mem for i in range(4)):
            raise ValueError(f"{name}: incomplete queue pointer initializer")
    if (p[s["case13"][0]].operands!="0x3:m(r1,r0),(r3,r2)" or
        p[s["case13"][1]].operands!="0x7:m(r1,r0),r0" or
        p[s["case13"][2]].operands!="r0,0x0:s(r3,r2)" or
        any(p[a].end!=b or not C.has_fallthrough(p[a])
            for a,b in zip(s["case13"],s["case13"][1:])) or
        not E.checked(fw,s["producer_main"],s["alloc"],"call") or
        p[s["tx_data"]].operands!="r0,0xf4902:m" or
        p[s["tx_ack"]].operands!="r0,0xf4904:m" or
        p[s["tx_status"]].operands!="$0x5:s,0xf4900:m"):
        raise ValueError(f"{name}: command13/TX evidence differs")
    if name=="p2test" and (p[0x9c82].operands!="$0xa5d:l,(r4,r3)" or
        p[s["tx_buff_store"]].operands!="r2,0x0:s(r4,r3)" or
        p[0x9c8e].operands!="r7,0x0:s(r1,r0)"):
        raise ValueError("p2test: TX byte producer/index changed")
    a,b,c,d,e=s["case7_build"]
    if (not E.checked(fw,a,s["alloc"],"call") or
        p[b].operands!="r2,0x0:s(r1,r0)" or
        p[c].operands!="$0x8:s,0x2:m(r1,r0)" or
        p[d].operands!="(r9,r8),0x3:m(r1,r0)" or
        p[e].operands!="r7,0x7:m(r1,r0)" or
        p[s["case7_stack"]].operands!="(r3,r2),0x0:s(sp)" or
        not E.checked(fw,s["case7_copy"],0x28cf4 if name=="normal" else 0x27c64,"call") or
        p[s["case10_limits"][0]].mnemonic!="cmpb" or
        p[s["case10_limits"][1]].mnemonic!="cmpb"):
        raise ValueError(f"{name}: case7 queue event / case10 limits differ")


def analyze(name,fw,rows,mem):
    s=S[name];p=fw.insns;edges=C.build(fw)
    validate(fw,name,edges,mem)
    initial={f"0x{a:02x}":f"0x{int.from_bytes(bytes(mem[a+k] for k in range(4)), 'little'):08x}"
             for a in (0xda,0xde)}
    if set(initial.values())!={f"0x{s['base']:08x}"}:
        raise ValueError(f"{name}: queue initializer differs")
    callers=call_edges(edges,s["alloc"])
    caller_inputs=[]
    for addr in callers:
        previous=next((a for a,i in p.items() if i.end==addr),None)
        insn=p.get(previous)
        match=re.fullmatch(r"\$0x([0-9a-f]+):[sm],r2",insn.operands) if (
            insn is not None and insn.mnemonic=="movb" and C.has_fallthrough(insn)) else None
        caller_inputs.append({"call":cite(fw,addr),
            "immediate_tag_from_adjacent_instruction":
                f"0x{int(match.group(1),16):02x}" if match else None,
            "tag_definition":cite(fw,previous) if match else None,
            "other_reg_sources":"UNRESOLVED"})
    alloc_ref=[cite(fw,a) for a in (s["alloc"],s["alloc"]+0x10,s["alloc_write"],
        s["read_cell"],s["wrap"],*s["alloc_header"])]
    layout=base(name)|dict(instruction_provenance=alloc_ref+[cite(fw,s["item_len"]),
        cite(fw,s["consume"])],cfg_evidence={"initializer_raw_bytes":{
            f"0x{a:02x}":bytes(mem[a+k] for k in range(4)).hex() for a in (0xda,0xde)},
            "queue_consumer":f"0x{E.S[name]['main']:06x}",
            "local_empty_test":"pointer values compared for equality"},
        dataflow_evidence={"initial_cells":initial,"0xda":"allocation/write cursor on checked path",
            "0xde":"consumption/read cursor on checked path",
            "pointer_width_bits":32,"base":f"0x{s['base']:08x}",
            "limit_comparison":f"0x{s['limit']:08x}",
            "buffer_span_candidate_bytes":0x800,
            "allocation_size":"zero_extend16(r3)+4; runtime-dependent",
            "wrap":"branch/reset to base on selected conditions; no all-path range proof",
            "full_condition":"UNRESOLVED", "synchronization":"di/ei seen in allocator and main"},
        unresolved_paths=["all-path overlap/full conditions and interrupt interleaving",
            "unknown aliases may write pointer cells or buffer"])
    producer=base(name)|dict(instruction_provenance=alloc_ref+
        [cite(fw,a) for a in callers]+[cite(fw,s["alloc_copy"]),cite(fw,s["copy_call"])],
        cfg_evidence={"allocator_entry":f"0x{s['alloc']:06x}",
            "direct_callers":[f"0x{x:06x}" for x in callers],
            "adjacent_immediate_caller_tags":caller_inputs,
            "wrapper_copy_call":f"0x{s['copy_call']:06x}",
            "direct_count":len(callers)},
        dataflow_evidence={"record_header":"length16, status8, tag8, payload from +4",
            "producer":"software allocator/writer identified",
            "selected_caller_of_allocator":f"0x{s['producer_main']:06x}",
            "external_or_internal_source_per_caller":"NOT_EXHAUSTIVELY_CLASSIFIED",
            "checked_writer_classes":["literal pointer base", "register-pair stord through 0xda",
                "direct callers of allocator", "wrapper with stack-passed copy count"],
            "uncovered_classes":["DMA", "unknown indirect pointers/calls",
                "interrupt-interleaved writes", "other register-pair aliases"]},
        unresolved_paths=["not every caller's input or queue item data source traced",
            "physical host ingress not proven"])
    fields=[item_field(0,"allocated payload length (r3)"),
            item_field(2,"state byte from image RAM status; exact semantics unknown"),
            item_field(3,"allocator r2 tag; dispatcher only changes separate global state"),
            item_field(4,"payload type word 0x0167 or 0xfff1 on parser branch"),
            item_field(6,"subcommand byte for 0xfff1 branch only"),
            item_field(7,"case13 pointer32 from payload+3"),
            item_field(11,"case13 stored word from payload+7")]
    fmt=base(name)|dict(instruction_provenance=[cite(fw,a) for a in
        (*s["alloc_header"],s["item_payload"],s["dispatch_global_base"],s["dispatch_marker"],
         s["dispatch_call"],E.S[name]["sync"],*s["case13"])],
        cfg_evidence={"global_state_write_before_parser":E.checked(fw,s["dispatch_call"],s["parser"],"call"),
            "parser_pointer":"item+4 passed via r3:r2 on selected main path"},
        dataflow_evidence={"fields":fields,"word_order":"CR16 little-endian memory for typed loads",
            "total_size":"payload length + 4 on allocated path; global length unresolved",
            "marker_0x23":"parser compares caller-supplied item+3 tag; dispatcher separately stores 0x23 in global RAM; NOT UART sync proof",
            "type_0x0167_0xfff1":"observed comparison, meaning unresolved",
            "nested_payload":"pointer and 16-bit value at +3/+7 relative to item+4"},
        unresolved_paths=["partial items and global buffer availability not proved",
            "other item types may use different offsets"])
    cmd_sites=[cite(fw,a) for a in (E.S[name]["parser"],*E.S[name]["types"],
                                *E.S[name]["sub"],*s["cases"],*s["case_calls"])]
    cases=[]
    for ident,target,call in zip((7,9,10),s["cases"][:3],s["case_calls"]):
        dest=next((e.dst for e in edges if e.src==call and e.kind=="call" and
                   e.category==C.DIRECT_RESOLVED),None)
        if dest is None:raise ValueError(f"{name}: case {ident} call changed")
        cases.append({"id":ident,"branch_target":cite(fw,target),
            "direct_call":cite(fw,call),"callee":f"0x{dest:06x}",
            "selected_fields":(["payload+3 pointer32", "payload+7 word16"] if ident==7 else
                              ["payload+3 pointer32"] if ident==9 else
                              ["payload+3 byte","payload+4 byte"]),
            "downstream_effects":"PARTIAL; callee/interprocedural aliases unresolved",
            "response_link":"UNRESOLVED"})
    cases[0]["bounded_internal_effect"]={
        "alloc_call":cite(fw,s["case7_build"][0]),
        "new_item_payload":"0xfff1 at +0; 0x08 at +2; source pointer at +3; length at +7",
        "output":"another software queue item, not a proven UART TX response",
        "instruction_provenance":[cite(fw,a) for a in
            (*s["case7_build"],s["case7_stack"],s["case7_copy"])]}
    cases[2]["helper_input_bounds_differ"]={
        "comparisons":[cite(fw,a) for a in s["case10_limits"]],
        "normal_p2test_equivalence":"NOT_PROVEN"}
    cases.append({"id":13,"branch_target":cite(fw,s["cases"][3]),
        "selected_fields":["payload+3 pointer32","payload+7 word16"],
        "effect":cite(fw,s["case13"][2]),"response_link":"UNRESOLVED"})
    commands=base(name)|dict(instruction_provenance=cmd_sites,
        cfg_evidence={"case_branches":E.parser(fw,name)["subcommand_targets"],
            "entry_requirements":"selected 0xfff1 branch, per-case byte comparison"},
        dataflow_evidence={"cases":cases,"unknown_command_id":"returns without a named handler",
            "type_0x0167":"other selected calls, semantics unresolved"},
        unresolved_paths=["callee effects/ABI and memory ranges not fully proved",
            "length validation and message origin unresolved"])
    pw=base(name)|dict(instruction_provenance=[cite(fw,a) for a in s["case13"]],
        cfg_evidence={"local_straight_line":E.checked(fw,s["case13"][2],s["case13"][2]+2),
            "case_target":f"0x{s['cases'][3]:06x}"},
        dataflow_evidence={"pointer_source":"POINTER_FROM_QUEUE_ITEM payload+3 (record+7)",
            "pointer_width_bits":32,"value_source":"loadw payload+7 (record+11)",
            "write_width_bits":16,"effect":"storw r0,0(r3,r2)",
            "byte_order":"CR16 typed loadd/loadw; external byte serialization unknown",
            "range_check_in_selected_block":False,
            "target_range":conditional_value(["item pointer"],source_known=False),
            "external_control":"EXTERNAL_CONTROL_NOT_PROVEN"},
        unresolved_paths=["queue item source and pointer alias/range unknown",
            "no MMIO/DIP/DSP target is proven reachable", "earlier checks on producer path not excluded"])
    tx=base(name)|dict(instruction_provenance=[cite(fw,a) for a in
        (s["tx"],s["tx_data"],s["tx_ack"],s["tx_status"])
        if a is not None]+([cite(fw,s["tx_buff_store"])] if s["tx_buff_store"] is not None else []),
        cfg_evidence={"main_to_tx":E.checked(fw,E.S[name]["tx_call"],s["tx"],"call")},
        dataflow_evidence={"buffer_base":f"0x{s['tx_base']:04x}",
            "read_cursor":f"0x{s['tx_read']:04x}",
            "write_cursor_candidate":f"0x{s['tx_write']:04x}",
            "buffer_length_candidate":f"0x{s['tx_length']:x}",
            "RAM_byte_to_architectural_TX":"0x00ff4902 then 0x00ff4904, bit5 0x00ff4900",
            "p2test_local_buffer_producer":f"0x{s['tx_buff_store']:06x}" if s["tx_buff_store"] is not None else None},
        unresolved_paths=["normal buffer producers via unknown aliases",
            "complete TX queue full/empty/error paths and physical wire order"])
    responses=base(name)|dict(instruction_provenance=[cite(fw,a) for a in
        (*s["case_calls"],s["producer_main"],s["tx_data"])],
        cfg_evidence={"command_to_TX_buffer_proven":False},
        dataflow_evidence={"TX_event_from_queue_path":f"0x{s['producer_main']:06x}",
            "selected_command_to_response":"UNRESOLVED",
            "response_framing":"UNRESOLVED"},
        unresolved_paths=["response constructor to TX RAM byte source not traced",
            "asynchronous TX events may be unrelated to commands"])
    uart_reads=[r for r in rows if r["operation"]=="READ" and
        r.get("effective_address") in {f"0x{a:08x}" for a in
        (0xff4900,0xff4902,0xff4904,0xff4960,0xff4966,0xff497a)}]
    rx=base(name)|dict(instruction_provenance=[cite(fw,int(r["instruction"],16)) for r in uart_reads]
        +[cite(fw,s["rxvec"]),cite(fw,s["rxvec"]+2)],
        cfg_evidence={"reference_UART_RX_vector_stub":True},
        dataflow_evidence={"architectural_register_reads":[{
            "instruction":cite(fw,int(r["instruction"],16)),
            "effective_address":r["effective_address"],"width_bits":r["width_bits"]}
            for r in uart_reads],"runtime_RX_data_to_queue":"UNRESOLVED"},
        unresolved_paths=["no resolved second-level read at 0x00ff4902 in listed rows",
            "other addresses, indirect reads, DMA and hardware sources unexcluded"])
    links=base(name)|dict(instruction_provenance=[cite(fw,a) for a in
        (s["alloc"],s["copy_call"],s["dispatch_call"],s["case13"][2])],
        cfg_evidence={"confirmed_local_edges":["allocator→queue cell 0xda",
            "main queue item→dispatcher→parser", "case13 pointer load→storw"],
            "host_UART_to_queue":"UNRESOLVED"},
        dataflow_evidence={"DSP_DIP_PCM_GPIO_from_cases":"UNRESOLVED"},
        unresolved_paths=["case7/9/10 callee downstream not fully traced",
            "case13 target range unknown", "indirect and asynchronous effects"])
    bounds=base(name)|dict(instruction_provenance=[cite(fw,s["alloc"]),
        cite(fw,s["dispatch_marker"]),cite(fw,s["case13"][2])],
        cfg_evidence={"producer_to_queue":"LOCAL_PROVEN_UNDER_CFG_MODEL",
            "queue_to_parser":"LOCAL_PROVEN_UNDER_CFG_MODEL",
            "host_to_producer":"UNRESOLVED", "command_to_TX":"UNRESOLVED"},
        dataflow_evidence={"main_blocker":"which callers fill producer input and how/if external bytes arrive",
            "marker_correction":"dispatcher writes global RAM, not item+3; item tag supplied by allocator caller",
            "pointer_write_target":"TARGET_RANGE_UNRESOLVED"},
        unresolved_paths=["external host transport and permissions",
            "all-path queue full/wrap and element length", "TX response provenance"])
    return layout,producer,fmt,commands,pw,tx,responses,rx,links,bounds


def build(objdump):
    A._validate_inputs(objdump)
    reports=[{} for _ in FILES]
    for name,path in A.IMAGES:
        df,fw,rows=D.run_image(name,path,objdump)
        if df.get("converged") is not True or df.get("analysis_status")!="CONVERGED":
            raise ValueError(f"{name}: NON_CONVERGED")
        mem,*_=parse_ihex(path,strict=True)
        for dst,src in zip(reports,analyze(name,fw,rows,mem)):
            dst[name]=src
    if any(set(r)!=set(A.REFERENCE_SHA) for r in reports):
        raise ValueError("incomplete E4.1 bundle")
    return {fn:{"tool":"cr16-queue-trace/1","images":data}
            for fn,data in zip(FILES,reports)}


def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--objdump",default=str(A.OBJDUMP))
    ap.add_argument("--out",default=str(ROOT/"tools/reports"))
    args=ap.parse_args(argv)
    try:
        T.publish(Path(args.out),build(args.objdump))
    except (OSError,ValueError,KeyError,TypeError) as exc:
        out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
        (out/"cr16-e41.incomplete.json").write_text(json.dumps({
            "analysis_status":"INCOMPLETE","reason":str(exc)},indent=1)+"\n")
        print(f"INCOMPLETE E4.1: {exc}",file=sys.stderr)
        return 1
    return 0


if __name__=="__main__":
    raise SystemExit(main())
