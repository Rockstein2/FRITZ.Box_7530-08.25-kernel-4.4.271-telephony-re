#!/usr/bin/env python3
"""E4.4 offline bounded queue/TX adjacency, register inventory and boundaries."""
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
from cr16_boot_memory_map import parse_ihex

ROOT=Path(__file__).resolve().parent.parent
NAMES=tuple("cr16-e44-"+x+".json" for x in (
    "tx-producers","buffer-layout","rx-candidates","host-boundaries",
    "subsystem-graph","normal-p2test-differences","unresolved-paths"))
S={"normal":dict(tx_flags=0x9f86,tx_start=0x9f9a,tx_readbyte=0x9fa4,
                 tx_increment=0x9fa8,tx_wrap_cmp=0x9fb0,tx_wrap=0x9fb4,
                 tx_pre=0x9fb6,tx_eq=0x9fd2,idx_base=0x9fca,
                 queue_state=0x93cb,producer=None,producer_call=None),
   "p2test":dict(tx_flags=0x9bca,tx_start=0x9bde,tx_readbyte=0x9be8,
                 tx_increment=0x9bec,tx_wrap_cmp=0x9bf4,tx_wrap=0x9bf8,
                 tx_pre=0x9bfa,tx_eq=0x9c16,idx_base=0x9c0e,
                 queue_state=0x9512,producer=0x9c34,producer_call=0x9ca6,
                 prod_flag=0x9c36,prod_read=0x9c56,prod_full=0x9c64,
                 prod_idx=0x9c68,prod_bytes=0x9c8c,prod_inc=0x9c8e,
                 prod_wrap=0x9c9a)}


def geometry(qbase,qlimit,txbase,txlen):
    return {"queue_base":f"0x{qbase:04x}","queue_limit_comparison":f"0x{qlimit:04x}",
            "tx_base":f"0x{txbase:04x}","candidate_tx_end_exclusive":f"0x{txbase+txlen:04x}",
            "queue_base_plus_0x800_equals_tx_base":qbase+0x800==txbase,
            "tx_base_minus_queue_limit":txbase-qlimit,
            "runtime_overlap":"UNRESOLVED; queue allocation bounds/overflows/interrupts not all-path closed"}


def baseline(name):
    for suffix,field,expected in (("e42-parser-reachability","specific_allocator_generation_to_parser_tag_23","UNRESOLVED"),
         ("e43-state-transitions","producer_backed_edges",[])):
        fn=ROOT/"tools/reports"/f"cr16-{suffix}.json"
        value=json.loads(fn.read_text())["images"][name]
        if (value["firmware_sha256"]!=A.REFERENCE_SHA[name] or
            value["dataflow_evidence"].get(field)!=expected):
            raise ValueError(f"{name}: invalid previous baseline {suffix}")


def analyze(name,fw,rows,mem):
    baseline(name);q=Q.S[name];s=S[name];p=fw.insns;edges=C.build(fw)
    E.parser(fw,name)
    if (p[s["tx_start"]].operands!=f"$0x{q['tx_base']:x}:l,(r5,r4)" or
        p[s["tx_readbyte"]].operands!="0x0:s(r5,r4),r2" or
        p[s["tx_pre"]].operands!="r2,r0" or
        p[q["tx_data"]].operands!="r0,0xf4902:m" or
        p[q["tx_ack"]].operands!="r0,0xf4904:m" or
        p[q["tx_status"]].operands!="$0x5:s,0xf4900:m" or
        p[s["tx_wrap_cmp"]].operands!="r4,r3" or
        p[s["tx_increment"]].operands!="r3,0x0:s(r1,r0)" or
        p[s["tx_eq"]].operands!="r3,r2"):
        raise ValueError(f"{name}: TX pump instruction model changed")
    prod_sites=[]
    if s["producer"] is not None:
        prod_sites=[s[x] for x in ("producer","prod_flag","prod_read","prod_full",
                            "prod_idx","prod_bytes","prod_inc","prod_wrap","producer_call")]
        if (p[s["prod_bytes"]].operands!="r2,0x0:s(r4,r3)" or
            p[s["prod_inc"]].operands!="r7,0x0:s(r1,r0)" or
            p[s["prod_flag"]].operands!="$0x9515:l,(r4,r3)" or
            not E.checked(fw,s["producer_call"],s["producer"],"call") or
            len(Q.call_edges(edges,s["producer"]))!=1):
            raise ValueError("p2test: TX byte producer changed")
    geom=geometry(q["base"],q["limit"],q["tx_base"],q["tx_length"])
    if geom["tx_base_minus_queue_limit"]!=2 or not geom["queue_base_plus_0x800_equals_tx_base"]:
        raise ValueError(f"{name}: buffer adjacency changed")
    init={f"0x{x:04x}":f"0x{mem[x]:02x}" if x in mem else "NOT_IN_IMAGE"
          for x in range(q["limit"],q["tx_base"]+2)}
    limits=["parser tag-0x23 producer path unproved (E4.2)",
         "unknown indirect memory aliases, DMA and interrupt writers",
         "physical bus/UART activity not observed"]
    def b(sites,cfg,flow,unknown=None):
        return Q.base(name)|dict(instruction_provenance=[T.cite(fw,x) for x in sites],
            cfg_evidence=cfg,dataflow_evidence=flow,unresolved_paths=limits if unknown is None else unknown)
    tx=b([s["tx_flags"],s["tx_start"],s["tx_readbyte"],s["tx_increment"],
          s["tx_wrap_cmp"],s["tx_wrap"],s["tx_eq"],q["tx_data"],q["tx_ack"],
          q["tx_status"],*prod_sites],
         {"main_calls_TX":E.checked(fw,E.S[name]["tx_call"],q["tx"],"call"),
          "direct_p2test_writer_call":[T.cite(fw,x) for x in Q.call_edges(edges,s["producer"])]
                if s["producer"] is not None else [],
          "normal_resolved_direct_buffer_writer":"UNRESOLVED" if name=="normal" else None},
         {"selected_TX":"RAM byte base+read_index → zero_extend → 0x00ff4902 storw → 0x00ff4904 storw",
          "cursor_cells":[f"0x{x:04x}" for x in (q["tx_read"],q["tx_write"],q["tx_index"])],
          "candidate_length_cell":"0x00e8 (image 0x07f0)",
          "p2test_writer": "r2 → RAM[0x0a5d+write_index]; advance cursor; selected full checks and PSR save/restore"
                     if name=="p2test" else "NOT_RESOLVED",
          "response_link":"UNRESOLVED"},limits+["complete TX full/empty/wrap and normal byte producers not exhaustively covered"])
    layout=b([q["alloc"],q["wrap"],s["tx_start"],s["tx_wrap_cmp"],
              q["tx_data"]],
         {"queue_and_TX_base_instructions_distinct":True},
         {"geometry":geom,"image_bytes_at_transition":init,
          "allocation_end_all_paths":"UNRESOLVED",
          "distinct_data_structure_identity":"CANDIDATE (different cursors and base literals; no all-path non-overlap proof)"})
    register_set={0xff4900,0xff4902,0xff4904,0xff4906,0xff4966,0xff497a}
    read=[r for r in rows if r["operation"]=="READ" and r.get("effective_address") and
           r["address_kind"]=="RESOLVED" and int(r["effective_address"],16) in register_set]
    access=[r for r in rows if r["operation"] in ("READ","WRITE","RMW") and r.get("effective_address") and
            r["address_kind"]=="RESOLVED" and int(r["effective_address"],16) in register_set]
    rx=b([int(r["instruction"],16) for r in access]+[q["rxvec"],q["rxvec"]+2],
         {"second_level_vector_20_21":"same nop; retx stub; reference numbering only",
          "direct_resolved_data_register_0x00ff4902_reads":sum(r["effective_address"]=="0x00ff4902" for r in read)},
         {"register_access_inventory":[{"site":T.cite(fw,int(r["instruction"],16)),
                 "architectural_address":r["effective_address"],
                 "operation":r["operation"],"width_bits":r["width_bits"],
                 "status":"REGISTER_ACCESS_PROVEN"} for r in access],
          "RX_data_to_queue":"UNRESOLVED", "related_device_UART_name":"RELATED_DEVICE_HYPOTHESIS",
          "physical_UART":"PHYSICAL_UART_NOT_OBSERVED"})
    boundaries=b([q["alloc"],q["dispatch_call"],s["tx_start"],q["tx_data"]],
         {"software_queue_to_parser":"local direct path, conditional tag",
          "parser_to_TX":"UNRESOLVED", "peripheral_to_software_queue":"UNRESOLVED"},
         {"bootloader_0x02_0x01_handshake":"SEPARATE_FIRST_LEVEL",
          "runtime_UART_RX":"UNRESOLVED", "DMA_or_polling_ingress":"UNRESOLVED",
          "runtime_TX":"architectural writes proven; physical transmission not observed"})
    graph=b([E.S[name]["queue_dispatch"],q["dispatch_call"],E.S[name]["tx_call"],
             q["tx_data"],E.S[name]["dip_writer"],*E.S[name]["dsp_helper"]],
        {"direct_software_edges":[{"source":f"0x{E.S[name]['main']:06x}",
                   "via":T.cite(fw,E.S[name]["queue_dispatch"]),
                   "destination":f"0x{q['dispatch']:06x}"},
                  {"source":f"0x{E.S[name]['main']:06x}",
                   "via":T.cite(fw,E.S[name]["tx_call"]),
                   "destination":f"0x{q['tx']:06x}"}],
         "independent_DSP_DIP_candidate_sites":[T.cite(fw,E.S[name]["dip_writer"]),
             *[T.cite(fw,x) for x in E.S[name]["dsp_helper"]]]},
        {"verified_shared_RAM":"item+3 ↔ global state byte via main and dispatcher; TX indices separate",
         "parser_to_DSP_DIP_GPIO_PCM":"UNRESOLVED",
         "independent_subsystem_sites_are_not_parser_links":True},
        limits+["no command→peripheral edge proved even where independent firmware effects exist"])
    diffs=b([q["alloc"],q["tx"],s["tx_start"],*prod_sites],
        {"semantic_equivalence_of_97_prefix_matches":"NOT_PROVEN"},
        {"queue_base":geom["queue_base"],"TX_base":geom["tx_base"],
         "TX_writer":"p2test local writer and direct call" if name=="p2test" else "normal writer unresolved",
         "case10_bounds":"0x0c/0x11" if name=="p2test" else "0x12/0x17",
         "case9_table_base":"0x00000" if name=="p2test" else "0x11dda",
         "confirmed_pair_equivalence":"only local byte-pump instruction shape; full function paths unproved"})
    uns=b([s["tx_start"],q["tx_data"],q["rxvec"]],
        {"no_all_path_ingress_claim":True},
        {"host_RX":"UNRESOLVED","command_to_TX":"UNRESOLVED",
         "normal_TX_writers":"UNRESOLVED","buffer_overlap":"UNRESOLVED",
         "DSP_DIP_PCM_GPIO_command_links":"UNRESOLVED"},limits)
    return tx,layout,rx,boundaries,graph,diffs,uns


def build(objdump):
    A._validate_inputs(objdump)
    data=[{} for _ in NAMES]
    for name,path in A.IMAGES:
        df,fw,rows=D.run_image(name,path,objdump)
        if df.get("converged") is not True or df.get("analysis_status")!="CONVERGED":
            raise ValueError(f"{name}: NON_CONVERGED")
        mem,*_=parse_ihex(path,strict=True)
        for d,v in zip(data,analyze(name,fw,rows,mem)):d[name]=v
    if any(set(d)!=set(A.REFERENCE_SHA) for d in data):raise ValueError("incomplete E4.4 bundle")
    return {fn:{"tool":"cr16-runtime-transport/1","images":d} for fn,d in zip(NAMES,data)}


def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument("--objdump",default=str(A.OBJDUMP))
    ap.add_argument("--out",default=str(ROOT/"tools/reports"));args=ap.parse_args(argv)
    try:T.publish(Path(args.out),build(args.objdump))
    except (OSError,ValueError,KeyError,TypeError) as exc:
        out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
        (out/"cr16-e44.incomplete.json").write_text(json.dumps({"analysis_status":"INCOMPLETE",
            "reason":str(exc)},indent=2)+"\n")
        print(f"INCOMPLETE E4.4: {exc}",file=sys.stderr);return 1
    return 0


if __name__=="__main__":raise SystemExit(main())
