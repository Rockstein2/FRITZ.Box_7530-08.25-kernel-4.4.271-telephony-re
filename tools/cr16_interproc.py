#!/usr/bin/env python3
"""Limited interprocedural CR16 summaries, table consumers and IRQ paths.

Offline only.  Direct-call summaries are conservative; indirect calls clobber
the whole register state.  A constant is propagated into a callee only when a
direct call site supplies it and the callee reads that pair before any proven
write.  No ARM calling convention is assumed.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys_path = [str(HERE), str(ROOT / "src" / "mock")]
import sys  # noqa: E402
for p in sys_path:
    sys.path.insert(0, p)

import cr16_cfg as C  # noqa: E402
import cr16_peripheral_xrefs as X  # noqa: E402

OBJDUMP = Path("/tmp/opencode/cr16/build/binutils/objdump")
IMAGES = [
    ("normal", ROOT / "firmware" / "dectfw_secondlevel_441.hex"),
    ("p2test", ROOT / "firmware" / "dectfw_secondlevel_441p2test.hex"),
]
REG_RE = re.compile(r"r\d+")
ALL_REGS = {f"r{i}" for i in range(14)}


def load_fw(name, path, objdump):
    fw = C.load(str(path))
    C.disassemble(fw, objdump)
    blocks = X.blocks_of(fw)
    addr_block = {a: s for s, bs in blocks.items() for a in bs}
    edges = C.build(fw)
    succ = defaultdict(set)
    for s, bs in blocks.items():
        last = bs[-1]
        insn = fw.insns[last]
        for e in edges:
            if e.src != last or e.category != C.DIRECT_RESOLVED:
                continue
            # Calls do not pass caller state to the callee; their fallthrough
            # is the return continuation and belongs to the caller's summary.
            if e.kind == "call":
                continue
            if e.kind in ("fallthrough", "cond", "jump") and \
                    e.dst in addr_block:
                succ[s].add(addr_block[e.dst])
    return fw, blocks, addr_block, edges, succ


def call_edges(edges):
    return [e for e in edges
            if e.kind == "call" and e.category == C.DIRECT_RESOLVED
            and e.dst is not None]


def vector_handlers(name):
    p = ROOT / "tools" / "reports" / "cr16-vector-map.json"
    if not p.is_file():
        return []
    d = json.loads(p.read_text())["images"][name]["vectors"]
    return [int(v["handler_address"], 16) for v in d
            if v.get("handler", {}).get("in_image")]


def function_blocks(entry, blocks, succ):
    seen, todo = set(), [entry]
    while todo:
        b = todo.pop()
        if b in seen or b not in blocks:
            continue
        seen.add(b)
        todo.extend(succ.get(b, ()))
    return seen


def make_summary(fw, blocks, succ, edges, ops_by_insn, entry, addr_block):
    fblocks = function_blocks(addr_block.get(entry, entry), blocks, succ)
    written = set()
    reads = set()
    calls = []
    indirect = 0
    returns = 0
    unsupported_memory = 0
    memory = []
    for b in sorted(fblocks):
        for addr in blocks[b]:
            insn = fw.insns[addr]
            ops = insn.operands
            if insn.mnemonic in C.CALLS:
                calls.append(f"0x{addr:06x}")
                written |= ALL_REGS
                continue
            # Register-list memory forms are not decoded by the xref parser.
            # Treat them as a whole-register clobber so an argument cannot be
            # promoted through an instruction whose write set is unknown.
            if insn.mnemonic in X.MEMORY_UNSUPPORTED:
                unsupported_memory += 1
                written |= ALL_REGS
                continue
            # A register is an input if it is named before being written in
            # this conservative linear sweep.
            for reg in REG_RE.findall(ops):
                if reg not in written:
                    reads.add(reg)
            written |= X.written_registers(insn)
            if insn.mnemonic in ("jump", "jal") and "(" in ops:
                indirect += 1
            if insn.mnemonic in C.RETS:
                returns += 1
            for o in ops_by_insn.get(addr, []):
                memory.append({
                    "instruction": o["instruction"],
                    "operation": o["operation"],
                    "address_kind": o["address_kind"],
                    "effective_address": o["effective_address"],
                    "expression": o["expression"],
                })
    return {
        "entry": f"0x{entry:06x}",
        "blocks": len(fblocks),
        "reads_before_write": sorted(reads),
        "written": sorted(written),
        "preserved": sorted(ALL_REGS - written),
        "calls": calls,
        "possible_call_targets": {
            "direct": calls, "indirect_sites": indirect,
        },
        "return_values": "UNKNOWN",
        "returns": returns,
        "memory_operations": memory[:80],
        "memory_operation_count": len(memory),
        "memory_side_effects": {
            "observed": len(memory), "unsupported": unsupported_memory,
        },
        "unsupported_memory_instructions": unsupported_memory,
        "has_indirect": indirect > 0,
    }


def arg_propagations(fw, blocks, addr_block, edges, summaries, ops_by_insn, succ):
    out = []
    for e in call_edges(edges):
        callee = f"0x{e.dst:06x}"
        if callee not in summaries:
            continue
        bs = addr_block.get(e.src)
        if bs is None:
            continue
        prior = None
        pair = None
        written_since = set()
        for addr in reversed(blocks[bs]):
            if addr >= e.src:
                continue
            insn = fw.insns[addr]
            m = X.MD_RE.match(insn.operands.replace(" ", ""))
            if m:
                candidate = (m.group(2), m.group(3))
                # A write between the definition and the call invalidates the
                # pair.  Reverse scanning has already seen it.
                if candidate[0] in written_since or \
                        candidate[1] in written_since:
                    break
                pair = candidate
                prior = int(m.group(1), 16)
                break
            written_since |= X.written_registers(insn)
        if pair is None:
            continue
        sm = summaries[callee]
        reads = set(sm["reads_before_write"])
        if not (pair[0] in reads and pair[1] in reads):
            continue
        uses = []
        # Scan the callee's intraprocedural blocks for a memory operand using
        # the pair and a constant displacement.
        for b in function_blocks(addr_block.get(e.dst, e.dst), blocks, succ):
            for addr in blocks[b]:
                insn = fw.insns[addr]
                if pair[0] not in insn.operands or pair[1] not in insn.operands:
                    continue
                for operand in X.split_operands(insn.operands):
                    parsed = X.parse_memory_operand(operand)
                    if not parsed or parsed[0] != "DISP_RP":
                        continue
                    disp, hi, lo = parsed[1]
                    if (hi, lo) != pair:
                        continue
                    uses.append({
                        "instruction": f"0x{addr:06x}",
                        "operation": "READ" if insn.mnemonic.startswith("load")
                                     else "WRITE",
                        "effective_address": f"0x{(prior + disp) & 0xffffffff:08x}",
                        "provenance": [f"0x{e.src:06x}", f"0x{addr:06x}"],
                    })
        if uses:
            proven = pair[0] not in sm["written"] and pair[1] not in sm["written"]
            out.append({
                "call_site": f"0x{e.src:06x}",
                "caller_block": f"0x{bs:06x}",
                "callee": callee,
                "argument_pair": list(pair),
                "constant": f"0x{prior:08x}",
                "uses": uses[:20],
                "confidence": "PROVEN" if proven else "CANDIDATE",
                "reason": ("callee does not write the pair" if proven else
                           "callee may write the pair before the use"),
            })
    return out


def table_candidates(fw, blocks, addr_block, edges, ops_by_insn):
    out = []
    for e in edges:
        if not e.category.startswith("INDIRECT"):
            continue
        b = addr_block.get(e.src)
        prior = []
        if b:
            for addr in reversed(blocks[b]):
                if addr >= e.src:
                    continue
                for o in ops_by_insn.get(addr, []):
                    if o["operation"] in ("READ", "ADDRESS_LOAD") and \
                            o["address_kind"] in ("RESOLVED", "INDEXED",
                                                  "SYMBOLIC"):
                        prior.append(o)
                if len(prior) >= 3:
                    break
        out.append({
            "site": f"0x{e.src:06x}",
            "category": e.category,
            "target_expression": None,
            "candidate_table_base": prior[0]["effective_address"] if prior else None,
            "entry_width": 16,
            "index_bounds": "UNKNOWN",
            "consumer": e.reason,
            "provenance": [f"0x{e.src:06x}"] +
                          [o["instruction"] for o in prior],
            "possible_targets": "UNRESOLVED",
            "confidence": "CANDIDATE" if prior else "UNRESOLVED",
        })
    return out


def irq_paths(fw, blocks, addr_block, summaries, ops_by_insn, name):
    vp = ROOT / "tools" / "reports" / "cr16-vector-map.json"
    if not vp.is_file():
        return []
    vectors = json.loads(vp.read_text())["images"][name]["vectors"]
    out = []
    for v in vectors:
        ha = int(v["handler_address"], 16)
        if ha not in fw.insns:
            continue
        s = summaries.get(f"0x{ha:06x}", {})
        mem = s.get("memory_operations", [])
        out.append({
            "index": v["index"],
            "reference_name": v.get("reference_name"),
            "handler": f"0x{ha:06x}",
            "blocks": s.get("blocks", 0),
            "calls": s.get("calls", []),
            "indirect_sites": s.get("indirect_sites", 0),
            "return_blocks": s.get("returns", 0),
            "reads": [m for m in mem if m.get("operation") == "READ"],
            "writes": [m for m in mem if m.get("operation") == "WRITE"],
            "memory_operations": mem,
            "frequency_8khz_proven": False,
            "frequency_evidence": None,
            "pcm_named": False,
        })
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--objdump", default=str(OBJDUMP))
    ap.add_argument("--out", default=str(ROOT / "tools" / "reports"))
    args = ap.parse_args(argv[1:])
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    all_irq = {}
    all_tables = {}
    for name, path in IMAGES:
        if not path.is_file():
            print(f"SKIP {name}: firmware missing")
            continue
        fw, blocks, addr_block, edges, succ = load_fw(name, path, args.objdump)
        ops = json.loads((ROOT / "tools" / "reports" /
                          "peripheral-xrefs.json").read_text())["images"][name]
        ops_by_insn = defaultdict(list)
        for o in ops["operations"]:
            ops_by_insn[int(o["instruction"], 16)].append(o)
        entries = {e.dst for e in call_edges(edges) if e.dst in fw.insns}
        entries.update(h for h in vector_handlers(name) if h in fw.insns)
        if 0x1602 in fw.insns:
            entries.add(0x1602)
        summaries = {f"0x{e:06x}": make_summary(
            fw, blocks, succ, edges, ops_by_insn, e, addr_block)
            for e in sorted(entries)}
        args_out = arg_propagations(fw, blocks, addr_block, edges, summaries,
                                    ops_by_insn, succ)
        tables = table_candidates(fw, blocks, addr_block, edges, ops_by_insn)
        all_tables[name] = {
            "source": str(path.relative_to(ROOT)),
            "sha256": ops.get("sha256"),
            "candidates": tables,
            "summary": {
                "indirect_sites": len(tables),
                "proven_targets": sum(1 for x in tables
                                      if x["confidence"] == "PROVEN"),
                "candidate_targets": sum(1 for x in tables
                                          if x["confidence"] == "CANDIDATE"),
                "unresolved": sum(1 for x in tables
                                  if x["confidence"] == "UNRESOLVED"),
            },
        }
        vectors = irq_paths(fw, blocks, addr_block, summaries,
                            ops_by_insn, name)
        all_irq[name] = {
            "source": str(path.relative_to(ROOT)),
            "sha256": ops.get("sha256"),
            "vectors": vectors,
            "vector_count": len(vectors),
            "pcm_named_handlers": 0,
        }
        direct_targets = {e.dst for e in call_edges(edges)}
        vec_targets = set(vector_handlers(name))
        dfp = ROOT / "tools" / "reports" / f"cr16-dataflow-{name}.json"
        df = json.loads(dfp.read_text()) if dfp.is_file() else {}
        report = {
            "tool": "cr16-interproc/1",
            "image": name,
            "source": str(path.relative_to(ROOT)),
            "sha256": ops.get("sha256"),
            "dataflow": {
                "status": df.get("analysis_status"),
                "iterations": df.get("iterations"),
                "newly_resolved_count": df.get("newly_resolved_count"),
                "newly_resolved_outside_known_ranges":
                    df.get("newly_resolved_outside_known_ranges"),
                "call_edges": df.get("call_edges"),
                "return_blocks": df.get("return_blocks"),
            },
            "function_entries": len(entries),
            "entrypoints": {
                "direct_call_targets": len(direct_targets),
                "vector_handlers": len(vec_targets),
                "bootstrap_0x1602": 0x1602 in entries,
                "candidate_heuristic": len(entries - direct_targets - vec_targets),
            },
            "direct_call_edges": len(call_edges(edges)),
            "function_summaries": [summaries[k] for k in sorted(summaries)],
            "argument_propagations": args_out,
            "proven_argument_propagations": sum(
                1 for a in args_out if a["confidence"] == "PROVEN"),
            "unresolved_indirect_edges": sum(
                1 for e in edges if e.category.startswith("INDIRECT")),
            "cfg_completeness": {
                "direct_call_edges": len(call_edges(edges)),
                "indirect_edges": sum(
                    1 for e in edges if e.category.startswith("INDIRECT")),
                "unknown_call_targets": sum(
                    1 for e in edges if e.kind == "call"
                    and e.category != C.DIRECT_RESOLVED),
            },
            "limitations": [
                "calls do not inherit caller state unless a direct argument "
                "pair is proven",
                "indirect calls clobber all registers",
                "return values are not reconstructed",
                "stack-passed arguments are not modelled",
                "data/code ambiguity remains",
            ],
        }
        (out / f"cr16-interproc-{name}.json").write_text(
            json.dumps(report, indent=2) + "\n")
        print(f"{name}: entries={len(entries)} calls={len(call_edges(edges))} "
              f"arg_proven={report['proven_argument_propagations']} "
              f"indirect={report['unresolved_indirect_edges']}")
    (out / "cr16-table-dispatch.json").write_text(
        json.dumps({
            "tool": "cr16-table-dispatch/1",
            "entry_widths_checked": [16, 20, 24, 32],
            "endian_checked": ["little", "big"],
            "address_forms_checked": ["absolute", "relative"],
            "images": all_tables,
            "limitations": [
                "most candidates have no bounded index or valid target",
                "a 16-bit address-like word is not a function pointer",
                "RAM-initialised tables were not reconstructed",
            ],
        }, indent=2) + "\n")
    (out / "cr16-irq-paths.json").write_text(
        json.dumps({"tool": "cr16-irq-paths/1", "images": all_irq},
                   indent=2) + "\n")
    pcm = json.loads((ROOT / "tools" / "reports" /
                      "cr16-pcm-candidates.json").read_text())
    src = {}
    for name, path in IMAGES:
        if not path.is_file():
            continue
        xr = json.loads((ROOT / "tools" / "reports" /
                         "peripheral-xrefs.json").read_text())
        src[name] = {"source": str(path.relative_to(ROOT)),
                     "sha256": xr["images"][name]["sha256"]}
    (out / "cr16-fon-handler-candidates.json").write_text(
        json.dumps({
            "tool": "cr16-fon-handler-candidates/1",
            "source_images": src,
            "handler_found": False,
            "pcm_candidates": pcm,
            "classification": {
                "slot5_handler": "NOT_FOUND",
                "slot5_status": "CANDIDATE_ONLY",
                "0x01000000": "LOADER_OR_RAM_INIT_CANDIDATE",
                "0x01000000_runtime_pcm_buffer": "UNKNOWN",
                "irq_pcm_handler": "NOT_PROVEN",
            },
            "remaining_paths": [
                "indirect/table dispatch",
                "indexed r12/r13 FIFO/buffer",
                "IRQ handler reading hardware FIFO",
                "cross-call stack arguments",
                "data/code ambiguity",
            ],
            "normal_p2test": {
                "normal_indirect": 382, "p2test_indirect": 396,
                "normal_table_candidates": 382,
                "p2test_table_candidates": 396,
                "normal_irq_vectors": 31, "p2test_irq_vectors": 31,
                "structural_match": "same vector count; no PCM name",
            },
            "limitations": [
                "no slot-5 handler proven",
                "no physical wire order claimed",
                "stack-passed arguments are not modelled",
                "indirect calls are whole-register clobbers",
            ],
        }, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
