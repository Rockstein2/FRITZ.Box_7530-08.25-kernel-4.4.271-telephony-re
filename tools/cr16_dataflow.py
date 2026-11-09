#!/usr/bin/env python3
"""Conservative cross-block register dataflow for SC14448 CR16 firmware.

Offline only.  It reuses the existing CR16 disassembler/CFG and the
`cr16_peripheral_xrefs` operand helpers.  The merge rule is deliberately
sound: a register/pair keeps a value at a join only when every predecessor
agrees on the same value.  Calls and indirect control flow kill the state.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict, deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src" / "mock"))

import cr16_cfg as C  # noqa: E402
import cr16_peripheral_xrefs as X  # noqa: E402

OBJDUMP = Path("/tmp/opencode/cr16/build/binutils/objdump")
IMAGES = [
    ("normal", ROOT / "firmware" / "dectfw_secondlevel_441.hex"),
    ("p2test", ROOT / "firmware" / "dectfw_secondlevel_441p2test.hex"),
]

CALLS = C.CALLS
RETS = C.RETS
MAX_ITERS = 1000


def merge_state(states):
    """Meet of states: a key survives only if every state agrees exactly."""
    if not states:
        return {}
    keys = set(states[0])
    for s in states[1:]:
        keys &= set(s)
    return {k: states[0][k] for k in keys
            if all(s[k] == states[0][k] for s in states[1:])}


def merge_provenance(provs, keep):
    out = {}
    for key in keep:
        chain = []
        for p in provs:
            chain.extend(p.get(key, []))
        out[key] = sorted(set(chain))
    return out


def blocks_and_successors(fw):
    blocks = X.blocks_of(fw)
    starts = sorted(blocks)
    addr_block = {a: s for s in starts for a in blocks[s]}
    edges = C.build(fw)
    succ = defaultdict(set)
    for start in starts:
        last = blocks[start][-1]
        insn = fw.insns[last]
        if insn.mnemonic in RETS:
            continue
        if insn.mnemonic in CALLS:
            # A direct call has two successors: the callee entry and the
            # continuation after the return.  State propagation is still
            # conservative (the call transfer clears the state); this only
            # restores CFG coverage for the continuation.
            for e in edges:
                if e.src != last or e.category != C.DIRECT_RESOLVED:
                    continue
                if e.kind in ("call", "fallthrough") and e.dst in addr_block:
                    succ[start].add(addr_block[e.dst])
            continue
        for e in edges:
            if e.src != last or e.category != C.DIRECT_RESOLVED:
                continue
            if e.kind not in ("fallthrough", "cond", "jump"):
                continue
            if e.dst in addr_block:
                succ[start].add(addr_block[e.dst])
    preds = defaultdict(set)
    for s, ds in succ.items():
        for d in ds:
            preds[d].add(s)
    return blocks, starts, addr_block, succ, preds


def merge_entry(preds, states, provs, start):
    if not preds[start]:
        return {}, {}
    ps = [p for p in preds[start] if p in states]
    if not ps:
        return {}, {}
    state = merge_state([states[p] for p in ps])
    prov = merge_provenance([provs[p] for p in ps], set(state))
    return state, prov


def resolve_operand(insn, kind, state):
    """Return (address_kind, effective, expression, provenance_key)."""
    operands = X.split_operands(insn.operands)
    if kind in ("WRITE", "RMW") and insn.mnemonic in (
            "sbitw", "cbitw", "sbitb", "cbitb"):
        candidates = operands[1:] or operands
    elif kind == "READ":
        candidates = operands
    else:
        candidates = list(reversed(operands))

    parsed = payload = None
    for operand in candidates:
        p = X.parse_memory_operand(operand)
        if p:
            parsed, payload = p
            break
    if parsed == "ABS":
        value = X.abs_address(insn)
        if value == payload:
            return "RESOLVED", f"0x{value:08x}", None, None
        return "UNKNOWN", None, None, None
    if parsed == "DISP_RP":
        disp, hi, lo = payload
        st = X.pair_state(state, hi, lo)
        if st[0] == "KNOWN32":
            return ("RESOLVED", f"0x{(st[1] + disp) & 0xffffffff:08x}",
                    None, ("P", hi, lo))
        return "UNKNOWN", None, f"({hi},{lo})+{disp}", None
    if parsed == "DISP_R":
        disp, reg = payload
        if reg in ("r12", "r13"):
            return "INDEXED", f"[{reg}]+{disp:#x}", None, None
        if reg == "ra":
            return "PC_RELATIVE", f"ra+{disp}", None, None
        st = state.get(("R", reg))
        if st and st[0] == "KNOWN16":
            return ("RESOLVED", f"0x{(st[1] + disp) & 0xffff:08x}",
                    None, ("R", reg))
        return "UNKNOWN", None, f"{reg}+{disp}", None
    if parsed == "IDX":
        reg, disp = payload
        return "INDEXED", f"[{reg}]+{disp:#x}", None, None
    if parsed == "STACK":
        return "STACK", "sp", None, None
    return "UNKNOWN", None, None, None


def transfer(fw, blocks, state, prov, image, start, mode_a, mode_b):
    rows = []
    unclassified = []
    st = dict(state)
    pv = {k: list(v) for k, v in prov.items()}
    for addr in blocks[start]:
        insn = fw.insns[addr]
        ops = insn.operands.replace(" ", "")

        if insn.mnemonic in X.BIT_TEST:
            parsed = "READ"
            operands = X.split_operands(insn.operands)
            for operand in operands[1:] or operands:
                p = X.parse_memory_operand(operand)
                if p:
                    parsed, payload = p
                    break
            if parsed is not None:
                akind, effective, expr, key = resolve_operand(
                    insn, "READ", st)
                pv_row = pv.get(key, []) if key else [f"0x{addr:06x}"]
                rows.append(_row(image, addr, insn, "READ",
                                 X.BIT_TEST[insn.mnemonic], akind,
                                 effective, pv_row, expr, mode_a, mode_b,
                                 "single bit"))
            # tbit does not modify registers
            continue

        if insn.mnemonic in X.ACCESS:
            kind, width = X.ACCESS[insn.mnemonic]
            akind, effective, expr, key = resolve_operand(insn, kind, st)
            pv_row = pv.get(key, []) if key else [f"0x{addr:06x}"]
            rows.append(_row(image, addr, insn, kind, width, akind,
                             effective, pv_row, expr, mode_a, mode_b))
            X.write_back(st, insn)
            for reg in X.written_registers(insn):
                for k in list(pv):
                    if k == ("R", reg) or (k[0] == "P" and reg in k[1:]):
                        pv.pop(k, None)
            continue

        if insn.mnemonic == "movd":
            m = X.MD_RE.match(ops)
            if m:
                rows.append(_row(image, addr, insn, "ADDRESS_LOAD", 32,
                                 "RESOLVED", f"0x{int(m.group(1), 16):08x}",
                                 [f"0x{addr:06x}"], None, mode_a, mode_b))
                X.apply_instruction(st, insn)
                for k in list(pv):
                    if k not in st:
                        pv.pop(k, None)
                pv[("P", m.group(2), m.group(3))] = [f"0x{addr:06x}"]
                continue

        if insn.mnemonic in CALLS:
            st.clear()
            pv.clear()
            continue

        before = set(st)
        X.apply_instruction(st, insn)
        for k in list(pv):
            if k not in st:
                pv.pop(k, None)
        # preserve provenance for a constant pair built by addd
        if insn.mnemonic == "addd":
            m = __import__("re").match(
                r"^\((r\d+),(r\d+)\),\((r\d+),(r\d+)\)$", ops)
            if m:
                src = ("P", m.group(1), m.group(2))
                dst = ("P", m.group(3), m.group(4))
                if dst in st and st[dst][0] == "KNOWN32":
                    pv[dst] = sorted(set(pv.get(src, []) +
                                         pv.get(dst, []) +
                                         [f"0x{addr:06x}"]))
        if insn.mnemonic == "movw":
            m = __import__("re").match(
                r"^\$(-?0x[0-9a-f]+|-?\d+)(?::[sm])?,\((r\d+),(r\d+)\)$",
                ops)
            if m:
                pv[("P", m.group(2), m.group(3))] = [f"0x{addr:06x}"]
        # any newly invalidated key loses provenance; no invented values
        for k in list(pv):
            if k not in st:
                pv.pop(k, None)
    return rows, unclassified, st, pv


def _row(image, addr, insn, kind, width, akind, effective, provenance,
         expr, mode_a, mode_b, note=""):
    return {
        "image": image,
        "instruction": f"0x{addr:06x}",
        "bytes": insn.raw.hex(),
        "mnemonic": insn.mnemonic,
        "operation": kind,
        "width_bits": width,
        "address_kind": akind,
        "effective_address": effective,
        "expression": expr,
        "provenance": sorted(set(provenance)),
        "reachable_mode_a": addr in mode_a,
        "reachable_mode_b": addr in mode_b,
        "note": note,
    }


def compute_states(name, path, objdump, max_iters=MAX_ITERS):
    """Run the block-entry constant analysis and return its state tables.\n\n    This is the shared soundness primitive used by E3.  The caller must check
    ``converged`` before treating any state as proof.
    """
    fw = C.load(str(path))
    C.disassemble(fw, objdump)
    blocks, starts, addr_block, succ, preds = blocks_and_successors(fw)
    mode_a, mode_b = X.reachability(fw)
    states = {s: {} for s in starts}
    provs = {s: {} for s in starts}
    out_states = {s: {} for s in starts}
    out_provs = {s: {} for s in starts}
    converged = False
    iterations = 0
    for iterations in range(1, max_iters + 1):
        changed = False
        for s in starts:
            state, prov = merge_entry(preds, out_states, out_provs, s)
            _r, _u, out_st, out_pv = transfer(
                fw, blocks, state, prov, name, s, mode_a, mode_b)
            if (state != states[s] or prov != provs[s] or
                    out_st != out_states[s] or out_pv != out_provs[s]):
                states[s] = state
                provs[s] = prov
                out_states[s] = out_st
                out_provs[s] = out_pv
                changed = True
        if not changed:
            converged = True
            break
    return (fw, blocks, starts, addr_block, succ, preds, states, provs,
            converged, iterations)


def run_image(name, path, objdump, max_iters=MAX_ITERS):
    (fw, blocks, starts, addr_block, succ, preds, states, provs,
     converged, iterations) = compute_states(name, path, objdump, max_iters)
    mode_a, mode_b = X.reachability(fw)
    rows = []
    unclassified = []
    for s in starts:
        r, u, _st, _pv = transfer(fw, blocks, states[s], provs[s],
                                   name, s, mode_a, mode_b)
        rows.extend(r)
        unclassified.extend(u)

    old = json.loads((ROOT / "tools" / "reports" /
                      "peripheral-xrefs.json").read_text())["images"][name]
    old_keys = {(o["instruction"], o["operation"], o["effective_address"])
                for o in old["operations"] if o["address_kind"] == "RESOLVED"}
    for r in rows:
        if r["address_kind"] == "RESOLVED" and r["effective_address"]:
            r["plausibility_note"] = X._resolved_note(
                int(r["effective_address"], 16))
    for r in rows:
        if r["address_kind"] == "RESOLVED":
            r["confidence"] = "PROVEN" if converged else "CANDIDATE"
    new_resolved = [r for r in rows if r["address_kind"] == "RESOLVED"
                    and (r["instruction"], r["operation"],
                         r["effective_address"]) not in old_keys]
    stats = defaultdict(int)
    for r in rows:
        stats[f"{r['operation']}/{r['address_kind']}"] += 1
    old_stats = old["stats"]
    report = {
        "tool": "cr16-dataflow/1",
        "image": name,
        "sha256": old.get("sha256"),
        "decoded_instructions": len(fw.insns),
        "blocks": len(starts),
        "source_stats": old_stats,
        "new_stats": dict(sorted(stats.items())),
        "newly_resolved": new_resolved,
        "newly_resolved_count": len(new_resolved),
        "newly_resolved_outside_known_ranges": sum(
            1 for r in new_resolved if r.get("plausibility_note")),
        "analysis_status": "CONVERGED" if converged else "NON_CONVERGED",
        "converged": converged,
        "incomplete": not converged,
        "iterations": iterations,
        "max_iterations": max_iters,
        "call_edges": sum(1 for e in C.build(fw)
                           if e.kind == "call" and
                           e.category == C.DIRECT_RESOLVED),
        "return_blocks": sum(1 for s in starts
                             if fw.insns[blocks[s][-1]].mnemonic in RETS),
        "unclassified": unclassified,
        "state_blocks": sum(1 for s in starts if states[s]),
        "limitations": [
            "merge keeps a key only when all predecessors agree exactly",
            "calls and indirect control flow clear the state",
            "indexed r12/r13 accesses are not converted to constants",
            "table/vector dispatch is reported separately",
        ],
    }
    return report, fw, rows


def indirect_report(name, fw):
    edges = C.build(fw)
    indirect = [{
        "instruction": f"0x{e.src:06x}",
        "kind": e.kind,
        "category": e.category,
        "reason": e.reason,
    } for e in edges if e.category.startswith("INDIRECT")]
    hits = C.find_indirect_tables(fw, set(fw.insns))
    return {
        "tool": "cr16-indirect/1",
        "image": name,
        "indirect_edges": indirect,
        "indirect_count": len(indirect),
        "table_hits": hits[:200],
        "table_hit_count": len(hits),
        "limitations": [
            "a 16-bit word equal to an instruction address is a candidate, "
            "not proof of a function pointer",
            "no vector entry is assigned a PCM name",
        ],
    }


def pcm_report(name, rows):
    windows = ("0x000f60", "0x00ff60", "0x000f64", "0x00ff64",
               "0x000f54", "0x00ff54")
    selected = [r for r in rows if (r["effective_address"] or "").startswith(
        windows)]
    return {
        "tool": "cr16-pcm-candidates/1",
        "image": name,
        "candidate_accesses": selected,
        "count": len(selected),
        "candidate_regions": [
            "0x01000000 + indexed writes: loader/copy or runtime unknown",
            "0x00108xx: data/table candidate",
            "0x00116xx: data/table candidate",
            "0x000F6002/6, 0x00FF6006: control/status candidates",
        ],
        "limitations": [
            "no resolved slot-5 buffer",
            "indirect and indexed paths remain",
        ],
    }


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--objdump", default=str(OBJDUMP))
    ap.add_argument("--out", default=str(ROOT / "tools" / "reports"))
    ap.add_argument("--max-iterations", type=int, default=MAX_ITERS)
    args = ap.parse_args(argv[1:])
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    all_ind = []
    all_pcm = []
    status = 0
    for name, path in IMAGES:
        if not path.is_file():
            print(f"SKIP {name}: {path} missing")
            continue
        report, fw, rows = run_image(name, path, args.objdump,
                                     args.max_iterations)
        if not report["converged"]:
            # Never replace a previously confirmed report with an incomplete
            # fixed-point result.  Keep the diagnostics under a distinct name.
            (out / f"cr16-dataflow-{name}.incomplete.json").write_text(
                json.dumps(report, indent=2) + "\n")
            print(f"{name}: NON_CONVERGED after {report['iterations']} "
                  f"iterations; report not promoted", file=sys.stderr)
            status = 1
            continue
        (out / f"cr16-dataflow-{name}.json").write_text(
            json.dumps(report, indent=2) + "\n")
        print(f"{name}: blocks={report['blocks']} "
              f"new_resolved={report['newly_resolved_count']} "
              f"state_blocks={report['state_blocks']}")
        ir = indirect_report(name, fw)
        all_ind.append(ir)
        all_pcm.append(pcm_report(name, rows))
    if status:
        # A mixed/partial set must not overwrite the last complete candidate
        # reports either.
        print("incomplete analysis; combined reports not written",
              file=sys.stderr)
        return 1
    (out / "cr16-indirect-candidates.json").write_text(
        json.dumps({"tool": "cr16-indirect/1", "images": all_ind},
                   indent=2) + "\n")
    (out / "cr16-pcm-candidates.json").write_text(
        json.dumps({"tool": "cr16-pcm-candidates/1", "images": all_pcm},
                   indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
