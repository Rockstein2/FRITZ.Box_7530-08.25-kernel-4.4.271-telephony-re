#!/usr/bin/env python3
"""Conservative CR16 interprocedural summaries and E3 soundness primitives.

Offline only.  The analysis deliberately proves only properties that are true
on every modelled CFG path:

* a register is preserved until a use only if no instruction on any path from
  the function entry writes it before that use;
* a caller constant reaches a call only if the block-entry dataflow and the
  instruction prefix agree on that constant;
* an indirect call or a register-list memory form clobbers the whole modelled
  register set;
* a table candidate is not a table target unless a nearby load defines the
  register actually consumed by the indirect instruction.  Even then it is a
  CANDIDATE unless the full consumer chain is proven.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
import sys  # noqa: E402
for p in (str(HERE), str(ROOT / "src" / "mock")):
    sys.path.insert(0, p)

import cr16_cfg as C  # noqa: E402
import cr16_dataflow as D  # noqa: E402
import cr16_peripheral_xrefs as X  # noqa: E402

OBJDUMP = Path("/tmp/opencode/cr16/build/binutils/objdump")
IMAGES = [
    ("normal", ROOT / "firmware" / "dectfw_secondlevel_441.hex"),
    ("p2test", ROOT / "firmware" / "dectfw_secondlevel_441p2test.hex"),
]
REG_RE = re.compile(r"r\d+")
ALL_REGS = {f"r{i}" for i in range(14)}
MAX_FUNCTION_ITERS = 1000


def load_fw(name, path, objdump):
    """Load one image and expose both global and intraprocedural CFG views."""
    (fw, blocks, _starts, addr_block, _succ_full, _preds_full,
     states, provs, converged, iterations) = D.compute_states(
        name, path, objdump)
    edges = C.build(fw)
    succ = defaultdict(set)
    preds = defaultdict(set)
    for s, bs in blocks.items():
        last = bs[-1]
        for e in edges:
            if e.src != last or e.category != C.DIRECT_RESOLVED:
                continue
            if e.kind == "call":
                continue
            if e.kind in ("fallthrough", "cond", "jump") and \
                    e.dst in addr_block:
                succ[s].add(addr_block[e.dst])
    for s, ds in succ.items():
        for d in ds:
            preds[d].add(s)
    return (fw, blocks, addr_block, edges, succ, preds, states, provs,
            converged, iterations)


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


def _writes_at(insn):
    """Conservative set of registers an instruction may write.

    Register-list memory forms and calls are treated as full clobbers.  `pop`
    and `popret` write their register list; `push` does not.
    """
    mn = insn.mnemonic
    if mn in C.CALLS or mn in X.MEMORY_UNSUPPORTED:
        return set(ALL_REGS)
    if mn in ("pop", "popret"):
        return set(REG_RE.findall(insn.operands))
    return set(X.written_registers(insn))


def _read_regs(insn):
    """Registers named as inputs; destination-only operands are removed.

    This is intentionally conservative for arithmetic forms: even a register
    that is both read and written is reported as an input candidate.  The
    argument proof does not rely on this set alone; it uses the path-sensitive
    may-write map and the exact memory operand in the callee.
    """
    mn = insn.mnemonic
    if mn in C.CALLS or mn in ("pop", "popret"):
        return set()
    ops = insn.operands.replace(" ", "")
    regs = set(REG_RE.findall(insn.operands))
    if mn in X.MEMORY_UNSUPPORTED:
        return regs
    if mn in X.ACCESS:
        if mn.startswith("load"):
            return regs - _writes_at(insn)
        return regs
    if mn == "movd" and ops.startswith("$"):
        return set()
    if mn in ("movw", "movb") and ops.startswith("$"):
        return regs - _writes_at(insn)
    return regs


def _may_written(entry, fw, blocks, preds, succ, addr_block,
                 max_iters=MAX_FUNCTION_ITERS):
    """Path-sensitive may-write analysis for a single function.

    `before[addr]` is the union of registers possibly written on any modelled
    path from the function entry to `addr`.  If a pair is absent from that set,
    no modelled path wrote it before the use.  External predecessors make the
    incoming set UNKNOWN (all registers), never an invented empty path.
    """
    start = addr_block.get(entry, entry)
    fblocks = function_blocks(start, blocks, succ)
    if not fblocks:
        return {
            "blocks": set(), "before": {}, "converged": False,
            "entry_mid": entry not in blocks, "external_preds": True,
            "complete": False,
        }
    entry_mid = entry not in blocks
    local_preds = {b: {p for p in preds.get(b, ()) if p in fblocks}
                   for b in fblocks}
    external = {b: any(p not in fblocks for p in preds.get(b, ()))
                for b in fblocks}
    may_in = {b: set() for b in fblocks}
    may_out = {b: set() for b in fblocks}
    converged = False
    iterations = 0

    def block_writes(b):
        out = set()
        for addr in blocks[b]:
            if b == start and entry_mid and addr < entry:
                continue
            out |= _writes_at(fw.insns[addr])
        return out

    for iterations in range(1, max_iters + 1):
        changed = False
        for b in fblocks:
            if b == start:
                incoming = set()
                if external[b] and not entry_mid:
                    # An external edge into the nominal entry block is an
                    # alternate entry whose incoming registers are unknown.
                    incoming = set(ALL_REGS)
            elif external[b]:
                incoming = set(ALL_REGS)
            else:
                incoming = set()
                for p in local_preds[b]:
                    incoming |= may_out[p]
            out = incoming | block_writes(b)
            if incoming != may_in[b] or out != may_out[b]:
                may_in[b] = incoming
                may_out[b] = out
                changed = True
        if not changed:
            converged = True
            break

    before = {}
    for b in fblocks:
        cur = set(may_in[b])
        for addr in blocks[b]:
            if b == start and entry_mid and addr < entry:
                continue
            before[addr] = set(cur)
            cur |= _writes_at(fw.insns[addr])
    complete = (converged and not entry_mid and
                not any(external[b] for b in fblocks))
    return {
        "blocks": fblocks,
        "before": before,
        "converged": converged,
        "iterations": iterations,
        "entry_mid": entry_mid,
        "external_preds": any(external[b] for b in fblocks),
        "complete": complete,
    }


def make_summary(fw, blocks, succ, preds, edges, ops_by_insn, entry,
                 addr_block, may_cache):
    start = addr_block.get(entry, entry)
    fblocks = function_blocks(start, blocks, succ)
    may = _may_written(entry, fw, blocks, preds, succ, addr_block)
    may_cache[entry] = may
    written = set()
    inputs = set()
    calls = []
    direct_call_targets = []
    returns = 0
    unsupported_memory = 0
    memory = []
    block_starts = set(fblocks)
    for b in sorted(fblocks):
        for addr in blocks[b]:
            if may["entry_mid"] and b == start and addr < entry:
                continue
            insn = fw.insns[addr]
            if insn.mnemonic in C.CALLS:
                written |= ALL_REGS
            elif insn.mnemonic in X.MEMORY_UNSUPPORTED:
                unsupported_memory += 1
                written |= ALL_REGS
            else:
                before = may["before"].get(addr, set(ALL_REGS))
                for reg in _read_regs(insn):
                    if reg not in before:
                        inputs.add(reg)
                written |= _writes_at(insn)
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
    for e in edges:
        if e.kind != "call" or e.category != C.DIRECT_RESOLVED:
            continue
        if e.src in {a for b in fblocks for a in blocks[b]}:
            calls.append(f"0x{e.src:06x}")
            direct_call_targets.append({
                "site": f"0x{e.src:06x}",
                "target": f"0x{e.dst:06x}" if e.dst is not None else None,
                "confidence": "DIRECT_RESOLVED",
                "provenance": [f"0x{e.src:06x}"],
            })
    indirect = [
        e for e in edges
        if e.category.startswith("INDIRECT")
        and e.src in {a for b in fblocks for a in blocks[b]}
    ]
    return {
        "entry": f"0x{entry:06x}",
        "blocks": len(fblocks),
        "entry_confidence": (
            "CONFIRMED_BLOCK_START" if not may["entry_mid"] else
            "INFERRED_MID_BLOCK"),
        "reachable_under_current_cfg": bool(fblocks),
        "cfg_completeness": {
            "may_analysis_converged": may["converged"],
            "iterations": may.get("iterations"),
            "entry_mid_block": may["entry_mid"],
            "external_predecessors": may["external_preds"],
            "complete": may["complete"],
        },
        "reads_before_write": sorted(inputs),
        "reads_before_write_semantics":
            "must-not-write-on-any-modelled-path",
        "written": sorted(written),
        "preserved": sorted(ALL_REGS - written),
        "calls": calls,
        "possible_call_targets": {
            "direct": calls,
            "direct_edges": direct_call_targets,
            "indirect_sites": len(indirect),
        },
        "return_values": "UNKNOWN",
        "returns": returns,
        "memory_operations": memory[:80],
        "memory_operation_count": len(memory),
        "memory_side_effects": {
            "observed": len(memory), "unsupported": unsupported_memory,
        },
        "unsupported_memory_instructions": unsupported_memory,
        "has_indirect": len(indirect) > 0,
    }


def _callee_uses(fw, blocks, succ, addr_block, entry, may):
    out = defaultdict(list)
    fblocks = function_blocks(addr_block.get(entry, entry), blocks, succ)
    for b in fblocks:
        for addr in blocks[b]:
            insn = fw.insns[addr]
            for operand in X.split_operands(insn.operands):
                parsed = X.parse_memory_operand(operand)
                if not parsed or parsed[0] != "DISP_RP":
                    continue
                disp, hi, lo = parsed[1]
                pair = (hi, lo)
                if pair[0] not in insn.operands or \
                        pair[1] not in insn.operands:
                    continue
                if insn.mnemonic in X.ACCESS:
                    operation = X.ACCESS[insn.mnemonic][0]
                elif insn.mnemonic in X.BIT_TEST:
                    operation = "READ"
                else:
                    operation = "READ"
                out[pair].append({
                    "instruction": f"0x{addr:06x}",
                    "operation": operation,
                    "displacement": disp,
                    "before": sorted(may["before"].get(
                        addr, set(ALL_REGS))),
                })
    return out


def arg_propagations(fw, blocks, addr_block, edges, summaries, ops_by_insn,
                     succ, preds, states, provs, owners, may_cache,
                     global_converged):
    out = []
    for e in call_edges(edges):
        callee_key = f"0x{e.dst:06x}"
        if callee_key not in summaries:
            continue
        bs = addr_block.get(e.src)
        if bs is None or e.src not in blocks.get(bs, ()):
            continue
        owner_set = owners.get(bs, set())
        caller_complete = (
            global_converged and len(owner_set) == 1
            and summaries.get(f"0x{next(iter(owner_set)):06x}", {})
            .get("cfg_completeness", {}).get("complete", False))
        caller_entry = (f"0x{next(iter(owner_set)):06x}"
                        if len(owner_set) == 1 else None)
        # Replay the caller block prefix, using the shared block-entry state.
        prefix = [a for a in blocks[bs] if a < e.src]
        _r, _u, st, pv = D.transfer(
            fw, {bs: prefix}, states.get(bs, {}), provs.get(bs, {}),
            "interproc", bs, set(), set())
        may = may_cache.get(e.dst)
        if may is None:
            may = _may_written(e.dst, fw, blocks, preds, succ, addr_block)
            may_cache[e.dst] = may
        uses_by_pair = _callee_uses(fw, blocks, succ, addr_block, e.dst, may)
        for pair, uses in uses_by_pair.items():
            key = ("P", pair[0], pair[1])
            stv = st.get(key)
            if not stv or stv[0] != "KNOWN32":
                continue
            value = stv[1]
            callee_complete = may.get("complete", False)
            out_uses = []
            for u in uses:
                clobbered = set(pair) & set(u["before"])
                preserved = not clobbered
                confidence = ("PROVEN" if caller_complete and
                              callee_complete and preserved else
                              "CANDIDATE")
                out_uses.append({
                    "instruction": u["instruction"],
                    "operation": u["operation"],
                    "effective_address":
                        f"0x{(value + u['displacement']) & 0xffffffff:08x}",
                    "clobbered_before_use": sorted(clobbered),
                    "preserved_to_use": preserved,
                    "confidence": confidence,
                })
            if not out_uses:
                continue
            proven = all(u["confidence"] == "PROVEN" for u in out_uses)
            reasons = []
            if not global_converged:
                reasons.append("global dataflow NON_CONVERGED")
            if not caller_complete:
                reasons.append("caller entry/path not complete")
            if not callee_complete:
                reasons.append("callee path analysis incomplete")
            if any(not u["preserved_to_use"] for u in out_uses):
                reasons.append("callee may write the pair before use")
            out.append({
                "call_site": f"0x{e.src:06x}",
                "caller_block": f"0x{bs:06x}",
                "caller_entry": caller_entry,
                "callee": callee_key,
                "argument_pair": list(pair),
                "constant": f"0x{value:08x}",
                "definition_provenance": pv.get(key, []),
                "call_provenance": [f"0x{e.src:06x}"],
                "uses": out_uses[:20],
                "confidence": "PROVEN" if proven else "CANDIDATE",
                "reasons": reasons,
            })
    return out


def _indirect_target(insn):
    ops = insn.operands.replace(" ", "")
    m = re.search(r"\((r\d+),(r\d+)\)", ops)
    if m:
        return {m.group(1), m.group(2)}
    m = re.search(r"\((r\d+)\)", ops)
    if m:
        return {m.group(1)}
    if "(ra)" in ops or "ra" in ops:
        return {"ra"}
    return set()


def table_candidates(fw, blocks, addr_block, edges, ops_by_insn):
    out = []
    for e in edges:
        if not e.category.startswith("INDIRECT"):
            continue
        b = addr_block.get(e.src)
        site_insn = fw.insns.get(e.src)
        targets = _indirect_target(site_insn) if site_insn else set()
        prior = []
        linked = False
        if b and site_insn:
            for addr in reversed(blocks[b]):
                if addr >= e.src:
                    continue
                for o in ops_by_insn.get(addr, []):
                    if o["operation"] not in ("READ", "ADDRESS_LOAD"):
                        continue
                    insn = fw.insns.get(addr)
                    written = _writes_at(insn) if insn else set()
                    if targets & written:
                        linked = True
                    prior.append({
                        "instruction": o["instruction"],
                        "operation": o["operation"],
                        "address_kind": o["address_kind"],
                        "effective_address": o["effective_address"],
                        "expression": o["expression"],
                        "width_bits": o.get("width_bits"),
                        "writes_target": bool(targets & written),
                    })
                if len(prior) >= 4:
                    break
        target_is_ra = "ra" in targets
        confidence = ("CANDIDATE" if linked and not target_is_ra
                      else "UNRESOLVED")
        out.append({
            "site": f"0x{e.src:06x}",
            "category": e.category,
            "target_registers": sorted(targets),
            "target_expression": (
                ", ".join(sorted(targets)) if targets else None),
            "candidate_table_base": (
                prior[0]["effective_address"]
                if linked and prior and prior[0]["address_kind"] == "RESOLVED"
                else None),
            "entry_width": None,
            "entry_width_status": "UNKNOWN",
            "nearby_load_width_bits": (prior[0].get("width_bits")
                                       if linked and prior else None),
            "candidate_table_base_proven": False,
            "index_bounds": "UNKNOWN",
            "consumer": e.reason,
            "def_use_link": linked,
            "nearby_loads": prior,
            "provenance": [f"0x{e.src:06x}"] +
                          [o["instruction"] for o in prior],
            "possible_targets": "UNRESOLVED",
            "confidence": confidence,
        })
    return out


def _irq_tree(entry, summaries, depth=0, seen=None):
    seen = set() if seen is None else seen
    key = f"0x{entry:06x}"
    if key in seen or depth > 3:
        return {"entry": key, "cycle_or_depth_limit": True}
    seen.add(key)
    s = summaries.get(key, {})
    node = {
        "entry": key,
        "memory_operations": s.get("memory_operations", []),
        "direct_calls": [],
        "indirect_sites": s.get("possible_call_targets", {})
        .get("indirect_sites", 0),
        "confidence": "DIRECT_RESOLVED",
    }
    for c in s.get("possible_call_targets", {}).get("direct_edges", []):
        t = c.get("target")
        if not t:
            continue
        taddr = int(t, 16)
        node["direct_calls"].append({
            "site": c["site"], "target": t,
            "confidence": c["confidence"],
            "callee": _irq_tree(taddr, summaries, depth + 1, seen),
        })
    return node


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
            "indirect_sites": s.get("possible_call_targets", {})
            .get("indirect_sites", 0),
            "return_blocks": s.get("returns", 0),
            "reads": [m for m in mem if m.get("operation") == "READ"],
            "writes": [m for m in mem if m.get("operation") == "WRITE"],
            "memory_operations": mem,
            "callgraph": _irq_tree(ha, summaries),
            "frequency_8khz_proven": False,
            "frequency_evidence": None,
            "pcm_named": False,
        })
    return out


def analyze_image(name, path, objdump):
    (fw, blocks, addr_block, edges, succ, preds, states, provs,
     converged, iterations) = load_fw(name, path, objdump)
    ops = json.loads((ROOT / "tools" / "reports" /
                      "peripheral-xrefs.json").read_text())["images"][name]
    ops_by_insn = defaultdict(list)
    for o in ops["operations"]:
        ops_by_insn[int(o["instruction"], 16)].append(o)
    entries = {e.dst for e in call_edges(edges) if e.dst in fw.insns}
    vec_targets = set(vector_handlers(name))
    entries.update(h for h in vec_targets if h in fw.insns)
    if 0x1602 in fw.insns:
        entries.add(0x1602)
    may_cache = {}
    summaries = {f"0x{e:06x}": make_summary(
        fw, blocks, succ, preds, edges, ops_by_insn, e, addr_block,
        may_cache) for e in sorted(entries)}
    direct_targets = {e.dst for e in call_edges(edges)}
    for entry, s in summaries.items():
        addr = int(entry, 16)
        if addr in direct_targets:
            s["entry_kind"] = "DIRECT_CALL_TARGET"
        elif addr in vec_targets:
            s["entry_kind"] = "IRQ_VECTOR_HANDLER"
        elif addr == 0x1602:
            s["entry_kind"] = "BOOTSTRAP_ENTRY"
        else:
            s["entry_kind"] = "HEURISTIC_OR_UNKNOWN"
        s["cfg_completeness"]["unknown_indirect_entry"] = (
            s["entry_kind"] == "HEURISTIC_OR_UNKNOWN")
    owners = defaultdict(set)
    for entry in entries:
        for b in function_blocks(addr_block.get(entry, entry), blocks, succ):
            owners[b].add(entry)
    args = arg_propagations(fw, blocks, addr_block, edges, summaries,
                            ops_by_insn, succ, preds, states, provs,
                            owners, may_cache, converged)
    tables = table_candidates(fw, blocks, addr_block, edges, ops_by_insn)
    vectors = irq_paths(fw, blocks, addr_block, summaries, ops_by_insn, name)
    return {
        "fw": fw, "blocks": blocks, "addr_block": addr_block,
        "edges": edges, "states": states, "provs": provs,
        "converged": converged, "iterations": iterations,
        "summaries": summaries, "arguments": args, "tables": tables,
        "vectors": vectors, "ops_by_insn": ops_by_insn,
        "succ": succ, "preds": preds,
    }


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--objdump", default=str(OBJDUMP))
    ap.add_argument("--out", default=str(ROOT / "tools" / "reports"))
    args = ap.parse_args(argv[1:])
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    all_irq = {}
    all_tables = {}
    status = 0
    for name, path in IMAGES:
        if not path.is_file():
            print(f"SKIP {name}: firmware missing")
            continue
        a = analyze_image(name, path, args.objdump)
        summaries = a["summaries"]
        args_out = a["arguments"]
        tables = a["tables"]
        all_tables[name] = {
            "source": str(path.relative_to(ROOT)),
            "sha256": json.loads((ROOT / "tools" / "reports" /
                                  "peripheral-xrefs.json").read_text())
                      ["images"][name]["sha256"],
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
        all_irq[name] = {
            "source": str(path.relative_to(ROOT)),
            "sha256": json.loads((ROOT / "tools" / "reports" /
                                  "peripheral-xrefs.json").read_text())
                      ["images"][name]["sha256"],
            "vectors": a["vectors"],
            "vector_count": len(a["vectors"]),
            "pcm_named_handlers": 0,
        }
        direct_targets = {e.dst for e in call_edges(a["edges"])}
        vec_targets = set(vector_handlers(name))
        dfp = ROOT / "tools" / "reports" / f"cr16-dataflow-{name}.json"
        df = json.loads(dfp.read_text()) if dfp.is_file() else {}
        report = {
            "tool": "cr16-interproc/3",
            "image": name,
            "source": str(path.relative_to(ROOT)),
            "sha256": json.loads((ROOT / "tools" / "reports" /
                                  "peripheral-xrefs.json").read_text())
                      ["images"][name]["sha256"],
            "analysis_status": ("CONVERGED" if a["converged"] else
                                "NON_CONVERGED"),
            "dataflow": {
                "status": df.get("analysis_status"),
                "iterations": a["iterations"],
                "newly_resolved_count": df.get("newly_resolved_count"),
                "newly_resolved_outside_known_ranges":
                    df.get("newly_resolved_outside_known_ranges"),
                "call_edges": df.get("call_edges"),
                "return_blocks": df.get("return_blocks"),
            },
            "function_entries": len(summaries),
            "entrypoints": {
                "direct_call_targets": len(direct_targets),
                "vector_handlers": len(vec_targets),
                "bootstrap_0x1602": any(s["entry"] == "0x001602"
                                        for s in summaries.values()),
                "candidate_heuristic": len(set(summaries) -
                                           {f"0x{x:06x}" for x in
                                            direct_targets | vec_targets}),
            },
            "direct_call_edges": len(call_edges(a["edges"])),
            "function_summaries": [summaries[k] for k in sorted(summaries)],
            "argument_propagations": args_out,
            "proven_argument_propagations": sum(
                1 for x in args_out if x["confidence"] == "PROVEN"),
            "candidate_argument_propagations": sum(
                1 for x in args_out if x["confidence"] == "CANDIDATE"),
            "unresolved_indirect_edges": sum(
                1 for e in a["edges"] if e.category.startswith("INDIRECT")),
            "cfg_completeness": {
                "direct_call_edges": len(call_edges(a["edges"])),
                "indirect_edges": sum(
                    1 for e in a["edges"] if e.category.startswith("INDIRECT")),
                "unknown_call_targets": sum(
                    1 for e in a["edges"] if e.kind == "call"
                    and e.category != C.DIRECT_RESOLVED),
            },
            "limitations": [
                "only direct-call register-pair arguments are modelled",
                "stack-passed arguments and return values are not modelled",
                "indirect calls and register-list memory forms clobber all "
                "registers",
                "a table candidate needs a proven def-use chain and bounded "
                "index before it can be PROVEN",
                "data/code ambiguity remains",
            ],
        }
        (out / f"cr16-interproc-{name}.json").write_text(
            json.dumps(report, indent=2) + "\n")
        print(f"{name}: entries={len(summaries)} "
              f"calls={len(call_edges(a['edges']))} "
              f"arg_proven={report['proven_argument_propagations']} "
              f"arg_candidate={report['candidate_argument_propagations']} "
              f"indirect={report['unresolved_indirect_edges']} "
              f"status={report['analysis_status']}")
        if not a["converged"]:
            status = 1
    (out / "cr16-table-dispatch.json").write_text(
        json.dumps({
            "tool": "cr16-table-dispatch/3",
            "capabilities": {
                "table_entry_widths_decoded": [],
                "endianness_decoded": [],
                "nearby_load_widths_observed": sorted({
                    x.get("nearby_load_width_bits")
                    for img in all_tables.values()
                    for x in img["candidates"]
                    if x.get("nearby_load_width_bits") is not None
                }),
                "address_forms_inspected": ["absolute", "register-relative"],
                "note": ("A nearby load may define the indirect register, but "
                         "no table entry width, stride, index bound or "
                         "endianness was decoded.  The report therefore does "
                         "not claim 16/20/24/32-bit or both-endian coverage."),
            },
            "images": all_tables,
            "limitations": [
                "most candidates have no bounded index or valid target",
                "a 16-bit address-like word is not a function pointer",
                "RAM-initialised tables were not reconstructed",
                "no candidate has a completed consumer chain",
            ],
        }, indent=2) + "\n")
    (out / "cr16-irq-paths.json").write_text(
        json.dumps({"tool": "cr16-irq-paths/3", "images": all_irq},
                   indent=2) + "\n")
    pcm = json.loads((ROOT / "tools" / "reports" /
                      "cr16-pcm-candidates.json").read_text())
    src = {}
    xr = json.loads((ROOT / "tools" / "reports" /
                     "peripheral-xrefs.json").read_text())
    for name, path in IMAGES:
        if path.is_file():
            src[name] = {"source": str(path.relative_to(ROOT)),
                         "sha256": xr["images"][name]["sha256"]}
    (out / "cr16-fon-handler-candidates.json").write_text(
        json.dumps({
            "tool": "cr16-fon-handler-candidates/3",
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
                "structural_match": "same vector count; no PCM name",
            },
            "limitations": [
                "no slot-5 handler proven",
                "no physical wire order claimed",
                "stack-passed arguments are not modelled",
                "indirect calls are whole-register clobbers",
            ],
        }, indent=2) + "\n")
    return status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
