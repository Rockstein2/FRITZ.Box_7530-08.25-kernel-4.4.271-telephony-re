#!/usr/bin/env python3
"""Offline, bounded writer/loop/program reconstruction; never execute firmware."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cr16_address_spaces as A
import cr16_cfg as C
import cr16_dataflow as D
import cr16_dip_trace as T

ROOT = Path(__file__).resolve().parent.parent
NAMES = tuple("cr16-e34-" + x + ".json" for x in (
    "dip-writers", "dip-memory-model", "loop-proof", "dip-instructions",
    "dip-bringup", "event-dispatch", "fon-relevance"))
SITES = {
    "normal": {"restore": 0x3704, "counter_load": 0x25fa2,
               "static_call": 0x25fd4, "static_init": (0x25fca, 0x25fcc, 0x25fd0),
               "static_entry": 0x25fb8, "prepare_call": 0x25fba,
               "save_load": 0x36cc, "save_cell": 0x2434,
               "word_begin": 0x2604, "index_begin": 0x260a,
               "high": (0x2610, 0x2612), "low": (0x2614, 0x2616),
               "stop_func": 0x2558, "bmc": (0x255e, 0x2566),
               "stop_base": 0x2582, "stop_value": 0x2588,
               "stop_store": 0x258c, "release": 0x25b4,
               "gate": 0x28ad0, "skip": 0x28afa, "or": 0x28ad8,
               "bit3": (0x28aea, 0x28aec, 0x28aee, 0x3b28),
               "bit2": (0x28af2, 0x28af4, 0x28af6, 0x3b38),
               "dip_branches": (0x28742,)},
    "p2test": {"restore": 0x3456, "counter_load": 0x26758,
               "static_call": 0x2678a, "static_init": (0x26780, 0x26782, 0x26786),
               "static_entry": 0x2676e, "prepare_call": 0x26770,
               "save_load": 0x341e, "save_cell": 0x1c8a,
               "word_begin": 0x1ec0, "index_begin": 0x1ec6,
               "high": (0x1ecc, 0x1ece), "low": (0x1ed0, 0x1ed2),
               "stop_func": 0x1e0c, "bmc": (0x1e12, 0x1e1a),
               "stop_base": 0x1e3e, "stop_value": 0x1e44,
               "stop_store": 0x1e48, "release": 0x1e70,
               "gate": 0x27950, "skip": 0x2797a, "or": 0x27958,
               "bit3": (0x2796a, 0x2796c, 0x2796e, 0x27744),
               "bit2": (0x27972, 0x27974, 0x27976, 0x27754),
               "dip_branches": (0x25d86, 0x25db4, 0x25db8, 0x25dba)},
}
EXTERNAL = {
    "cr16b_manual": "https://my.eng.utah.edu/~cs3710/handouts/cr16.pdf",
    "cr16b_sha256": "3d6b25b5a0ab9949ebe4b540cdfc093d71f8fad91cf075d1d9b6306b09fb6a94",
    "gcc_cr16": "https://git.raptorcs.com/git/ppe42-gcc/plain/gcc/config/cr16/cr16.c",
    "gcc_sha256": "37aecb4c744cbf47be3143a1c7df85cad7ad91259bb6a947204d56e5985dcd4c",
}


def cite(fw, a):
    return T.cite(fw, a)


def next_edge(fw, src, dst):
    i = fw.insns[src]
    return i.end == dst and C.has_fallthrough(i) and dst in fw.insns


def checked_sequence(fw, addresses):
    """No intervening instruction or branch within one straight-line segment."""
    return all(next_edge(fw, a, b) for a, b in zip(addresses, addresses[1:]))


def loop_iterations(start, limit, *, compare="SOURCE_GREATER", clobber=False,
                    conditional_store=False):
    """Model the decoded local do/while: increment then compare $limit,r0."""
    if (compare != "SOURCE_GREATER" or clobber or conditional_store or
            not 0 < start <= limit < 65536):
        return None
    return max(1, limit - start)


def memory_cell(writes):
    """Possible values; no last-writer claim absent ordered compatible paths."""
    candidates = sorted({w["value"] for w in writes})
    definite = (len(writes) == 1 and writes[0].get("all_paths", False))
    return {"possible_values": candidates or ["UNKNOWN"],
            "final_value": candidates[0] if definite else None,
            "write_order_proven": definite,
            "writer_instructions": [w["instruction"] for w in writes],
            "candidate_writes": [{"candidate_value": w["value"],
                "writer_instruction": w["instruction"],
                "writer_function": w.get("function", "UNRESOLVED"),
                "write_order": w.get("order", "UNRESOLVED"),
                "path_condition": w.get("path", "UNRESOLVED"),
                "confidence": w.get("confidence", "UNRESOLVED")}
                for w in writes]}


def base(name):
    return dict(image=name, firmware_sha256=A.REFERENCE_SHA[name],
                analysis_status="CONVERGED_BOUNDED_PATHS",
                instruction_provenance=[], cfg_provenance={},
                dataflow_provenance={},
                related_device_evidence={"SC14480": "RELATED_DEVICE_HYPOTHESIS",
                    "DIP_RAM": "512 x 16-bit, printed pp. 131-132; not proved for SC14448"},
                unknown_entries=["unresolved indirect entry/call target"],
                unknown_writers=["unresolved register-pair aliases/copies/DMA"],
                unresolved_paths=[], confidence="PARTIALLY_PROVEN")


def analyze(name, fw, rows):
    t, s, p = T.SITES[name], SITES[name], fw.insns
    valid, literal, backedge = T.fill_check(fw, t)
    if not (valid and literal and backedge):
        raise ValueError(f"{name}: E3.3 fill chain changed")
    # Re-observe the actual writer operands; don't infer byte order from the
    # related-device DIP manual.
    sequence = [s["word_begin"], s["index_begin"],
                s["index_begin"] + 2, s["index_begin"] + 4,
                *s["high"], *s["low"], t["writer"]]
    if not checked_sequence(fw, sequence) or [p[a].mnemonic for a in sequence] != [
            "movd", "movzw", "ashud", "addd", "movzb", "ashuw",
            "movzb", "orw", "storw"]:
        raise ValueError(f"{name}: indexed writer sequence changed")
    if (p[s["word_begin"]].operands != "$0x1000000:l,(r1,r0)" or
        p[s["index_begin"]].operands != "r4,(r5,r4)" or
        p[s["high"][0]].operands != "r2,r2" or
        p[s["high"][1]].operands != "$8:s,r2" or
        p[s["low"][0]].operands != "r3,r3" or
        p[s["low"][1]].operands != "r2,r3" or
        p[t["writer"]].operands != "r3,0x0:s(r1,r0)"):
        raise ValueError(f"{name}: indexed writer value/address mismatch")
    edges = C.build(fw)
    callers = sorted(e.src for e in edges if e.kind == "call" and
                     e.dst == s["word_begin"] and e.category == C.DIRECT_RESOLVED)
    base_sites = [cite(fw, a) for a in sorted(p) if p[a].mnemonic == "movd"
                  and p[a].operands.startswith("$0x1000000:l,")]
    unresolved_accesses = sum(r.get("operation") in ("WRITE", "RMW") and
                              r.get("effective_address") is None for r in rows)
    static = [*s["static_init"], s["static_call"]]
    post_fill = sorted(a for a in p if s["static_entry"] <= a <= s["static_call"])
    if (not checked_sequence(fw, static) or
        not checked_sequence(fw, post_fill) or
        not T.edge(fw, s["prepare_call"], t["entry"]) or
        any(p[a].mnemonic in C.COND | C.JUMPS for a in post_fill) or
        [p[a].operands for a in s["static_init"]] != [
            "$0x2:s,r4", "$0xaa:m,r3", "$0x12:m,r2"] or
        not T.edge(fw, s["static_call"], s["word_begin"])):
        raise ValueError(f"{name}: static post-fill writer changed")
    writer_rows = [{"writer_instruction": cite(fw, t["store"]),
                    "source": "r2 <- caller 0x1001", "address_formula":
                    "0x01000000+2*zero_extend16(counter)",
                    "value_formula": "0x1001 on selected call path",
                    "range": "indices 1..511 on local closed loop", "confidence": "LOCAL_CFG_MODEL"},
                   {"writer_instruction": cite(fw, t["writer"]),
                    "source": "caller r2 (high byte), r3 (low byte), r4 (index)",
                    "address_formula": "0x01000000+2*zero_extend16(r4)",
                    "value_formula": "(zero_extend8(r2)<<8)|zero_extend8(r3)",
                    "range": "r4 runtime-dependent; known call: index 2",
                    "confidence": "LOCAL_INSTRUCTION_PROVEN"},
                   {"writer_instruction": cite(fw, s["restore"]),
                    "source": f"RAM word at 0x{s['save_cell']:04x}",
                    "address_formula": "0x01000000+2*zero_extend16(index from helper)",
                    "value_formula": f"loadw [0x{s['save_cell']:04x}]",
                    "range": "runtime-dependent", "confidence": "PARTIALLY_PROVEN"}]
    writers = base(name) | dict(instruction_provenance=[cite(fw, a) for a in
                 sequence + static + [s["save_load"], s["restore"]]],
        cfg_provenance={"direct_callers_indexed_writer": [f"0x{c:06x}" for c in callers],
            "static_caller": f"0x{s['static_call']:06x}",
            "static_call_edge_verified": True,
            "post_fill_caller_linear_except_calls": True,
            "fill_call_edge": [f"0x{s['prepare_call']:06x}", f"0x{t['entry']:06x}"],
            "intervening_callee_returns": "ASSUMED",
            "byte_input_definitions_immediately_precede_call": True},
        dataflow_provenance={"writers": writer_rows,
            "literal_base_load_sites_not_necessarily_writers": base_sites,
            "unresolved_write_addresses_in_dataflow": unresolved_accesses,
            "static_call": {"word_index": 2, "high_input": "0x12",
                            "low_input": "0xaa", "word": "0x12aa",
                            "address": "0x01000004"},
            "caller_bytes_other_paths": "RUNTIME_DEPENDENT"},
        unresolved_paths=["callers of dynamic writer have further calls/conditions",
                          "all aliases, indirect stores, memory copy and DMA not exhausted"])

    # The caller loads r0 from the counter *after* return: no ABI return-value
    # premise. The only instruction between cmp and branch must be none.
    caller_load = p[s["counter_load"]]
    if (caller_load.mnemonic != "loadw" or
        caller_load.operands != "0x0:s(r8,r7),r0" or
        not checked_sequence(fw, [t["call"], s["counter_load"], t["compare"],
                                  t["branch"]]) or
        p[t["compare"]].operands != "$0x200:m,r0" or
        p[t["branch"]].mnemonic != "bhi"):
        raise ValueError(f"{name}: loop r0/flags chain changed")
    helper_segment = sorted(a for a in p if t["helper"] <= a <= t["store"] + 6)
    if (not checked_sequence(fw, helper_segment) or
        any(p[a].mnemonic in C.COND | C.CALLS | C.JUMPS
            for a in helper_segment) or
        p[t["entry"] + 2].operands != f"$0x{t['cell']:x}:l,(r8,r7)" or
        p[t["init"]].operands != "$0x1:s,0x0:s(r8,r7)" or
        p[t["helper"] + 2].operands != f"$0x{t['cell']:x}:l,(r1,r0)" or
        p[t["helper"]].operands != "$0x1,r7" or
        p[t["store"]].mnemonic != "storw" or
        p[t["store"]+2].mnemonic != "addw" or
        p[t["store"]+2].operands != "$0x1:s,r3" or
        p[t["store"]+4].mnemonic != "storw" or
        p[t["store"]+4].operands != "r3,0x0:s(r1,r0)" or
        p[t["store"] + 6].operands != "$0x1,r7" or
        p[t["store"] + 6].mnemonic != "popret"):
        raise ValueError(f"{name}: helper cell/register restoration differs")
    count = loop_iterations(1, 512)
    loop = base(name) | dict(instruction_provenance=[cite(fw, a) for a in
        (t["entry"]+2, t["init"], t["literal"], t["call"], t["helper"],
         t["helper"]+2, t["store"], t["store"]+2,
         t["store"]+4, t["store"]+6, s["counter_load"], t["compare"],
         t["branch"])],
        cfg_provenance={"helper_direct_call": T.edge(fw, t["call"], t["helper"]),
                        "backedge": backedge,
                        "no_instruction_between_cmp_and_bhi": True,
                        "global_entry_coverage": False},
        dataflow_provenance={"r0_definition": cite(fw, s["counter_load"]),
            "r0_is_abi_return": False, "counter_initial_value": 1,
            "r8_r7_cell_address": f"0x{t['cell']:04x}",
            "r7_saved_and_restored_in_helper": True,
            "counter_step": 1, "compare_immediate": 512,
            "condition": "first operand 512 > second operand r0 (unsigned)",
            "local_loop_count": count, "all_path_loop_count": None,
            "local_index_range": [1, 511],
            "local_last_counter_after_increment": 512,
            "local_last_written_address": "0x010003fe",
            "flag_source": "CR16B manual CMPi PSR.L; GCC CR16 condition LTU->hi",
            "reference_identifiers": EXTERNAL},
        unresolved_paths=["SC14448 CR16Cplus-specific flag differences not ruled out",
          "external writes to counter cell / interrupt interleaving",
          "unresolved indirect entries and unknown calls"],
        confidence="PROVEN_UNDER_LOCAL_CFG_MODEL")

    # A 512-cell array of *possible* values; no global last-writer claim.
    cells = []
    for i in range(512):
        if i == 0:
            ws = [{"instruction": "UNKNOWN_INDIRECT", "value": "UNKNOWN",
                   "path": "unresolved alias may target this index"}]
        elif i == 2:
            ws = [{"instruction": f"0x{t['store']:06x}", "value": "0x1001",
                   "function": f"0x{t['helper']:06x}", "order": "local_fill",
                   "path": "local loop; no external writer", "confidence": "LOCAL_CFG_MODEL"},
                  {"instruction": f"0x{t['writer']:06x}", "value": "0x12aa",
                   "function": f"0x{s['word_begin']:06x}",
                   "order": "after_fill_call_if_returns",
                   "path": "static caller; intervening calls return",
                   "confidence": "LOCAL_CALL_PATH"},
                  {"instruction": f"0x{s['restore']:06x}",
                   "value": f"RAM[0x{s['save_cell']:04x}]",
                   "path": "only if runtime index equals 2"},
                  {"instruction": "UNKNOWN_INDIRECT", "value": "UNKNOWN",
                   "path": "unresolved alias may target this index"}]
        else:
            ws = [{"instruction": f"0x{t['store']:06x}", "value": "0x1001",
                   "function": f"0x{t['helper']:06x}", "order": "local_fill",
                   "path": "local loop; no external writer", "confidence": "LOCAL_CFG_MODEL"},
                  {"instruction": f"0x{t['writer']:06x}",
                   "value": "((r2&0xff)<<8)|(r3&0xff)",
                   "function": f"0x{s['word_begin']:06x}",
                   "path": f"only if runtime index equals {i}"},
                  {"instruction": f"0x{s['restore']:06x}",
                   "value": f"RAM[0x{s['save_cell']:04x}]",
                   "path": f"only if runtime index equals {i}"},
                  {"instruction": "UNKNOWN_INDIRECT", "value": "UNKNOWN",
                   "path": "unresolved alias may target this index"}]
        cells.append(dict(word_index=i, address=f"0x{0x1000000+2*i:08x}",
            **memory_cell(ws)))
    mem = base(name) | dict(instruction_provenance=[cite(fw, a) for a in
        (t["store"], t["writer"], s["restore"], s["static_call"])],
        cfg_provenance={"fill_then_static_caller": "CALL_RETURN_MODEL_ONLY",
            "final_order_global": "UNRESOLVED"},
        dataflow_provenance={"static_word_index_2": "0x12aa",
            "runtime_word": "((r2&0xff)<<8)|(r3&0xff)"},
        initial_fill={"indices": [1, 511], "word": "0x1001",
                      "status": "LOCAL_CFG_MODEL"},
        subsequent_writes=[writer_rows[1], writer_rows[2]],
        possible_final_values=cells, unknown_indices=[0, "runtime indices"],
        write_order_constraints=["local fill call before stop/release call",
            "static index-2 call after fill call if intervening calls return",
            "save/restore and dynamic writers may run later: no global order"],
        unresolved_paths=["all 512 final words unknown on all paths",
          "runtime input bytes and index values", "indirect writers not exhausted"],
        confidence="PARTIALLY_PROVEN")

    instr = base(name) | dict(instruction_provenance=[cite(fw, a) for a in
        (t["literal"], *s["static_init"], t["writer"])],
        cfg_provenance={"exact_SC14448_instruction_stream": False},
        dataflow_provenance={"fill_word": "0x1001",
            "local_post_fill_word_index_2": "0x12aa",
            "runtime_word": "((r2&0xff)<<8)|(r3&0xff)"},
        related_device_evidence={"status": "RELATED_DEVICE_HYPOTHESIS",
            "SC14480_table10": "0x01 BR, 0x10 BR_B0, 0xaa M_CON, 0x12 JMPF",
            "OsmocomDECT_SC14421": "BR=0x01; not an SC14448 encoding proof",
            "AN_D_140": "NOT_FOUND"},
        pseudo_disassembly=[{"index": 1, "raw_word": "0x1001",
            "opcode": "UNKNOWN_BYTE_ORDER", "branch_target": None},
            {"index": 2, "raw_word": "0x12aa on local later path",
             "opcode": "UNKNOWN_BYTE_ORDER", "branch_target": None}],
        unresolved_paths=["opcode position, branch parameter, bank and target",
            "SC14448 instruction-set compatibility", "runtime DIP program contents"],
        confidence="CANDIDATE")
    return writers, mem, loop, instr


def build(objdump):
    A._validate_inputs(objdump)
    images = [dict() for _ in NAMES]
    for name, path in A.IMAGES:
        df, fw, rows = D.run_image(name, path, objdump)
        if df.get("converged") is not True or df.get("analysis_status") != "CONVERGED":
            raise ValueError(f"{name}: NON_CONVERGED")
        for d, r in zip(images, analyze(name, fw, rows)):
            d[name] = r
        for slot, report in zip(images[4:], extra_reports(name, fw, rows)):
            slot[name] = report
    if any(set(d) != set(A.REFERENCE_SHA) for d in images):
        raise ValueError("incomplete E3.4 image bundle")
    return {fn: {"tool": fn.removesuffix(".json") + "/1", "images": data}
            for fn, data in zip(NAMES, images)}


def extra_reports(name, fw, rows):
    s, t, p = SITES[name], T.SITES[name], fw.insns
    # Sequence between BMC control and release: verify every decoded
    # fallthrough instruction, and require no conditional/jump detours.
    segment = sorted(a for a in p if s["bmc"][0] <= a <= s["release"])
    if (not checked_sequence(fw, segment) or
        any(p[a].mnemonic in C.COND | C.JUMPS for a in segment) or
        not T.edge(fw, t["after"], s["stop_func"]) or
        p[s["bmc"][0]].operands != "$0x0:s,0xf6400:m" or
        p[s["bmc"][1]].operands != "r0,0xf6402:m" or
        p[s["stop_base"]].operands != "$0xff6006:l,(r1,r0)" or
        p[s["stop_value"]].operands != "$0x80:m,r2" or
        p[s["stop_store"]].operands != "r2,0x0:s(r1,r0)" or
        p[s["release"]].operands != "$0x0:s,0x0:s(r1,r0)"):
        raise ValueError(f"{name}: DIP bring-up CFG/value checks failed")
    bringup = base(name) | dict(instruction_provenance=[cite(fw, a) for a in
        (t["after"], *s["bmc"], s["stop_base"], s["stop_value"],
         s["stop_store"], s["release"])],
        cfg_provenance={"fill_exit_call_to_bmc": [f"0x{t['after']:06x}",
            f"0x{s['stop_func']:06x}"], "entire_callee_segment_fallthrough": True,
            "callee_segment_conditional_jumps": 0,
            "call_returns_assumed": True, "global_order_proven": False},
        dataflow_provenance={"bmc0": "immediate 0",
            "bmc2": "movw 0xf0 -> r0 -> storw",
            "control_stop": "movd 0xff6006 -> r1:r0; movw 0x80 -> r2; storw",
            "control_release": "same r1:r0; storw immediate 0",
            "sc14448_URST_semantics": "UNRESOLVED"},
        unresolved_paths=["call returns/interleavings and prior control state",
            "other callers can modify the same registers", "physical map unknown"])
    gate, skip, or_site = s["gate"], s["skip"], s["or"]
    b3, b2 = s["bit3"], s["bit2"]
    gate_to_or = sorted(a for a in p if gate <= a <= or_site)
    required = (p[gate-4].mnemonic == "movb" and
                p[gate-4].operands == "r10,r2" and
                p[gate-2].mnemonic == "andb" and
                p[gate-2].operands == "$0xe:s,r2" and
                checked_sequence(fw, [gate-4, gate-2, gate]) and
                p[gate].mnemonic == "bne0b" and
                p[gate].operands.startswith("r2,") and
                T.edge(fw, gate, skip) and
                checked_sequence(fw, gate_to_or) and
                p[or_site].operands == "$0xc:s,r10" and
                p[or_site+2].operands == "$0xf:s,r10" and
                T.edge(fw, or_site+4, b3[0]) and
                checked_sequence(fw, sorted(a for a in p
                    if or_site <= a <= b3[0])) and
                checked_sequence(fw, list(b3[:3])) and
                checked_sequence(fw, list(b2[:3])) and
                next_edge(fw, b3[2], b2[0]) and
                next_edge(fw, b2[2], skip) and
                p[b3[0]].operands == "$0x3:s,r10" and
                p[b2[0]].operands == "$0x2:s,r10" and
                T.edge(fw, b3[1], b2[0]) and T.edge(fw, b2[1], skip) and
                T.edge(fw, b3[2], b3[3]) and T.edge(fw, b2[2], b2[3]))
    if not required:
        raise ValueError(f"{name}: DSP gate/bit-test CFG mismatch")
    dip_sources = ((0x2873e, 0x28742, 0x2878e) if name == "normal" else
                   (0x25d84, 0x25d86, 0x26514))
    if not T.edge(fw, dip_sources[1], dip_sources[2]):
        raise ValueError(f"{name}: DIP event gate mismatch")
    if name == "normal" and (not checked_sequence(fw, [0x2873c,
                0x2873e, 0x28740, 0x28742]) or
            p[0x2873e].operands != "$0xe:s,r0"):
        raise ValueError(f"{name}: DIP mask/compare chain differs")
    dip_targets = []
    if name == "p2test":
        for addr, dst in zip((0x25db4, 0x25db8, 0x25dba),
                             (0x25dbe, 0x25e2a, 0x2658a)):
            if not T.edge(fw, addr, dst):
                raise ValueError(f"{name}: DIP event branch {addr:#x} mismatch")
            dip_targets.append([cite(fw, addr), f"0x{dst:06x}"])
        if (not checked_sequence(fw, [0x25db2, 0x25db4, 0x25db6,
                                         0x25db8, 0x25dba]) or
                p[0x25db2].operands != "$0xe:s,r9" or
                p[0x25db6].operands != "$0xf:s,r9"):
            raise ValueError(f"{name}: DIP event comparisons differ")
    events = base(name) | dict(instruction_provenance=[cite(fw, a) for a in
        (gate-4, gate-2, gate, or_site, or_site+2, or_site+4,
         *b3[:3], *b2[:3], *dip_sources[:2])],
        cfg_provenance={"dsp_nonzero_gate_target": f"0x{skip:06x}",
            "bit3_false_target": f"0x{b2[0]:06x}",
            "bit2_false_target": f"0x{skip:06x}",
            "bit3_true_direct_helper": f"0x{b3[3]:06x}",
            "bit2_true_direct_helper": f"0x{b2[3]:06x}",
            "selected_edges_verified": required,
            "dip_gate": [cite(fw, dip_sources[1]), f"0x{dip_sources[2]:06x}"],
            "p2test_dip_branches": dip_targets},
        dataflow_provenance={"dsp": "r10 low-byte & 0x0e; nonzero skips; zero ORs 0x0c into r10 then tests bits 3/2",
            "normal_dip": "r9 & 0x0e -> r0; beq on zero" if name == "normal" else None,
            "p2test_dip": "[0x953e] gate; r9 == 0x0e/0x0f/other" if name == "p2test" else None},
        unresolved_paths=["indirect downstream calls and event meaning",
            "bit-test/branch instruction semantics on SC14448 not emulated",
            "complete register-clobber proof across helper calls"],
        confidence="PARTIALLY_PROVEN")
    fon = base(name) | dict(instruction_provenance=[cite(fw, a) for a in
        (t["writer"], s["restore"], gate)],
        cfg_provenance={"only_new_DIP_writer_and_bounded_event_paths": True,
                        "slot5_source_to_sink": False},
        dataflow_provenance={"no_slot5_consumer_proven": True,
            "no_register_name_inferred_from_SC14480": True},
        unresolved_paths=["slot-5 hardware ingress and data transformation",
            "indirect memory aliases, unknown callbacks and register identity"],
        confidence="UNRESOLVED")
    return bringup, events, fon


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--objdump", default=str(A.OBJDUMP))
    ap.add_argument("--out", default=str(ROOT / "tools" / "reports"))
    args = ap.parse_args(argv)
    try:
        T.publish(Path(args.out), build(args.objdump))
    except (OSError, ValueError, KeyError, TypeError, NotImplementedError) as exc:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "cr16-e34.incomplete.json").write_text(json.dumps(
            {"analysis_status": "INCOMPLETE", "reason": str(exc)}, indent=1) + "\n")
        print(f"INCOMPLETE E3.4: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
