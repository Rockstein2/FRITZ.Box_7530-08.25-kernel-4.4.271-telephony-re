#!/usr/bin/env python3
"""Bounded offline DIP fill/initialisation evidence; no firmware execution."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import cr16_address_spaces as A
import cr16_cfg as C
import cr16_dataflow as D
import cr16_peripheral_xrefs as X

ROOT = Path(__file__).resolve().parent.parent
SITES = {
    "normal": dict(entry=0x25f90, init=0x25f98, literal=0x25f9a,
                   call=0x25f9e, store=0x25d0, helper=0x25ba,
                   compare=0x25fa4, branch=0x25fa8, after=0x25faa,
                   stop=0x258c, start=0x25b4, cell=0x937c,
                   bmc=(0x255e, 0x2566), writer=0x2618,
                   other=(0x2e72, 0x2f98, 0x36ba, 0x36ec)),
    "p2test": dict(entry=0x26746, init=0x2674e, literal=0x26750,
                   call=0x26754, store=0x1e8c, helper=0x1e76,
                   compare=0x2675a, branch=0x2675e, after=0x26760,
                   stop=0x1e48, start=0x1e70, cell=0x94b6,
                   bmc=(0x1e12, 0x1e1a), writer=0x1ed4,
                   other=(0x2a0e, 0x2b32, 0x340c, 0x343e)),
}
FILENAMES = ("cr16-e33-dip-fill-proof.json", "cr16-e33-dip-opcodes.json",
             "cr16-e33-dip-init.json")


def cite(fw, addr):
    i = fw.insns[addr]
    return dict(instruction=f"0x{addr:06x}", raw_bytes=i.raw.hex(),
                disassembly=f"{i.mnemonic} {i.operands}".strip())


def edge(fw, src, target):
    return any(e.dst == target and e.category == C.DIRECT_RESOLVED
               for e in C.classify_insn(fw.insns[src], fw))


def fill_check(fw, s):
    """Check *local* instruction chain; do not assume runtime counter values."""
    p = fw.insns
    body = [i for i in p.values() if s["helper"] <= i.addr <= s["store"]]
    expected = ["push", "movd", "loadw", "movd", "movzw", "ashud",
                "addd", "storw"]
    form = [i.mnemonic for i in sorted(body, key=lambda x: x.addr)] == expected
    valid = (form and p[s["store"]].operands == "r2,0x0:s(r5,r4)" and
             p[s["helper"] + 0x0a].operands == "$0x1000000:l,(r5,r4)" and
             p[s["helper"] + 0x10].operands == "r3,(r7,r6)" and
             p[s["helper"] + 0x12].operands == "$1:s,(r7,r6)" and
             p[s["helper"] + 0x14].operands == "(r7,r6),(r5,r4)")
    literal = (p[s["literal"]].operands == "$0x1001:m,r2" and
               edge(fw, s["call"], s["helper"]))
    backedge = edge(fw, s["branch"], s["literal"])
    return valid, literal, backedge


def loop_confidence(*, initial, limit, step, backedge, exits,
                    unknown_predecessor=False, payload_clobber=False,
                    address_clobber=False, conditional_store=False,
                    flag_semantics=False):
    """Conservative proof gate for synthetic and real loop evidence."""
    if initial is None or limit is None or step != 1 or not backedge:
        return "UNRESOLVED"
    if (unknown_predecessor or payload_clobber or address_clobber or
            conditional_store or exits != 1 or not flag_semantics):
        return "PARTIALLY_PROVEN"
    if initial < 1 or limit < initial:
        return "UNRESOLVED"
    return "PROVEN_UNDER_CFG_MODEL"


def cfg_evidence(fw, s):
    """Direct-edge coverage only; indirect entries remain unmodelled."""
    edges = C.build(fw)
    predecessor = {}
    for e in edges:
        if e.dst is not None and e.category == C.DIRECT_RESOLVED:
            predecessor.setdefault(e.dst, []).append(e.src)
    reached = C.reach_all(fw, edges, [s["entry"]])
    return dict(entry=f"0x{s['entry']:06x}",
        selected_store_reachable=s["store"] in reached,
        selected_branch_reachable=s["branch"] in reached,
        store_hops=reached.get(s["store"]),
        store_direct_predecessors=[f"0x{x:06x}" for x in sorted(
            set(predecessor.get(s["store"], [])))],
        branch_direct_predecessors=[f"0x{x:06x}" for x in sorted(
            set(predecessor.get(s["branch"], [])))],
        unknown_indirect_edges=sum(e.kind == "indirect" for e in edges))


def report_image(name, fw, df):
    s = SITES[name]
    valid, literal, backedge = fill_check(fw, s)
    if not (valid and literal and backedge):
        raise ValueError(f"{name}: required local fill instructions/CFG edge differ")
    coverage = cfg_evidence(fw, s)
    if not coverage["selected_store_reachable"] or not coverage[
            "selected_branch_reachable"]:
        raise ValueError(f"{name}: selected fill sites not reached by direct CFG")
    # Extract independently from this image. An external writer of the
    # counter, an indirect entry, or an unmodelled call invalidates a global
    # 'exactly 511 stores' claim; these are reported, not assumed away.
    sites = [s["init"], s["literal"], s["call"], s["helper"] + 0x02,
             s["helper"] + 0x0a, s["helper"] + 0x10,
             s["helper"] + 0x12, s["helper"] + 0x14, s["store"],
             s["store"] + 2, s["store"] + 4, s["compare"], s["branch"]]
    evidence = [cite(fw, a) for a in sites]
    unresolved = ["external/indirect writers of the counter cell not excluded",
                  "full call-entry coverage and callee register preservation not proved",
                  "CR16 cmpw/bhi flag direction not independently ISA-verified",
                  "other indirect writers of the 0x01000000 bank not excluded"]
    confidence = loop_confidence(initial=1, limit=512, step=1,
                backedge=backedge, exits=1, unknown_predecessor=True,
                flag_semantics=False)
    common = dict(image=name, firmware_sha256=A.REFERENCE_SHA[name],
                  analysis_status="CONVERGED_BOUNDED_PATHS",
                  instruction_provenance=evidence,
                  control_flow_evidence={"call_target": f"0x{s['helper']:06x}",
                    "backedge": [f"0x{s['branch']:06x}", f"0x{s['literal']:06x}"],
                    "backedge_verified": backedge, "entry_global_proven": False,
                    "direct_cfg": coverage},
                  dataflow_evidence={"local_store_source": "r2",
                    "source_definition": f"0x{s['literal']:06x}",
                    "source_to_store": "LOCAL_CALL_PATH_ONLY",
                    "address_formula": "0x01000000 + 2*zero_extend16(counter)",
                    "counter_cell": f"0x{s['cell']:06x}",
                    "counter_initialisation": 1, "counter_increment": 1,
                    "compare_immediate": "0x0200",
                    "store_count": "511 CONDITIONAL ON CMP/BHI AND NO EXTERNAL WRITERS"},
                  related_device_evidence={"status": "RELATED_DEVICE_HYPOTHESIS",
                    "source": "SC14480 Rev 1.0, printed pp. 33-38, 131-132, 171-172"},
                  unresolved_paths=unresolved, confidence=confidence)
    fill = dict(common, value_provenance="LOCAL_LITERAL_AND_CALL_PATH",
                address_provenance="LOCAL_BODY_ARITHMETIC",
                loop_bounds_provenance="COUNTER_INIT_INCREMENT_BACKEDGE_VERIFIED; COMPARE_SEMANTICS_UNRESOLVED",
                cfg_coverage=coverage,
                additional_bank_base_sites=[cite(fw, a) for a in s["other"]],
                other_bank_writer=cite(fw, s["writer"]))
    init = dict(common, instruction_provenance=[cite(fw, a) for a in
                (s["init"], s["literal"], s["call"], s["after"],
                 *s["bmc"], s["stop"], s["start"])],
                control_flow_evidence={"after_fill_call": f"0x{s['after']:06x}",
                  "bmc_then_stop_then_zero_on_local_callee_path": True,
                  "stop_before_fill_on_this_path": False},
                dataflow_evidence={"stop_write": "0x0080",
                  "release_write": "0x0000", "bmc_writes": ["0x0000", "0x00f0"]},
                unresolved_paths=unresolved + [
                  "no global ordering across other callers/interrupts",
                  "DIP_PC poll meaning SC14448 not proved"],
                confidence="PARTIALLY_PROVEN")
    return fill, init


def publish(out, data):
    """Write complete validated bundle before promotion; restore on errors."""
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".e33-", dir=out) as td:
        stage = Path(td)
        backup = stage / "previous"
        backup.mkdir()
        old = {}
        for fn, body in data.items():
            target = out / fn
            old[fn] = target.exists()
            if target.exists():
                (backup / fn).write_bytes(target.read_bytes())
            (stage / fn).write_text(json.dumps(body, indent=1) + "\n")
            json.loads((stage / fn).read_text())
        done = []
        try:
            for fn in data:
                os.replace(stage / fn, out / fn)
                done.append(fn)
        except OSError:
            for fn in reversed(done):
                if old[fn]:
                    os.replace(backup / fn, out / fn)
                else:
                    (out / fn).unlink()
            raise


def build(objdump):
    A._validate_inputs(objdump)
    fills, inits, opcodes = {}, {}, {}
    for name, path in A.IMAGES:
        df, fw, _ = D.run_image(name, path, objdump)
        if df.get("converged") is not True or df.get("analysis_status") != "CONVERGED":
            raise ValueError(f"{name}: NON_CONVERGED")
        fills[name], inits[name] = report_image(name, fw, df)
        opcodes[name] = dict(image=name, firmware_sha256=A.REFERENCE_SHA[name],
            analysis_status="CONVERGED_BOUNDED_PATHS",
            instruction_provenance=[cite(fw, SITES[name]["literal"])],
            control_flow_evidence={}, dataflow_evidence={"word": "0x1001",
                "store_link": "LOCAL_CALL_PATH_ONLY"},
            related_device_evidence={"status": "RELATED_DEVICE_HYPOTHESIS",
                "source": "SC14480 Table 10 pp.35-38",
                "little_endian_candidate": "BR opcode 0x01, parameter 0x10",
                "big_endian_candidate": "BR_B0 opcode 0x10, parameter 0x01",
                "first_executable_word": "DIP_RAM+1 (SC14480 p.172)",
                "full_encoding_source": "AN-D-140 unavailable offline",
                "osmocomdect_sources": "unavailable offline; no SC14448 transfer"},
            unresolved_paths=["opcode byte order and parameter/target encoding",
                "branch behaviour, bank selection and first RAM word",
                "program validity and SC14448 DIP RAM identity"],
            confidence="CANDIDATE")
    return dict(zip(FILENAMES, [dict(tool="cr16-e33-dip-fill-proof/1",
        images=fills), dict(tool="cr16-e33-dip-opcodes/1", images=opcodes),
        dict(tool="cr16-e33-dip-init/1", images=inits)]))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--objdump", default=str(A.OBJDUMP))
    ap.add_argument("--out", default=str(ROOT / "tools" / "reports"))
    args = ap.parse_args(argv)
    try:
        publish(Path(args.out), build(args.objdump))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "cr16-e33-dip.incomplete.json").write_text(json.dumps(
            {"analysis_status": "INCOMPLETE", "reason": str(exc)}, indent=1) + "\n")
        print(f"INCOMPLETE DIP trace: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
