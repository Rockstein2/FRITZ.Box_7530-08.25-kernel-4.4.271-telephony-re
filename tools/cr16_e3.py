#!/usr/bin/env python3
"""FON-E3 focused CR16 audit and DSP/DIP/PCM trace.

Offline only.  This tool consumes the E3-corrected interprocedural analyzer and
writes the E3 reports; it does not execute firmware or touch hardware.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for p in (str(HERE), str(ROOT / "src" / "mock")):
    sys.path.insert(0, p)

import cr16_cfg as C  # noqa: E402
import cr16_dataflow as D  # noqa: E402
import cr16_interproc as I  # noqa: E402
import cr16_peripheral_xrefs as X  # noqa: E402

OBJDUMP = Path("/tmp/opencode/cr16/build/binutils/objdump")
IMAGES = [
    ("normal", ROOT / "firmware" / "dectfw_secondlevel_441.hex"),
    ("p2test", ROOT / "firmware" / "dectfw_secondlevel_441p2test.hex"),
]
BASELINE = "89599db81e2816cf323a554bb4054175d06dad25"
OLD_REPORTS = ("cr16-interproc-normal.json", "cr16-interproc-p2test.json")
DSP = {
    "normal": {"entry": 0x028a94, "end": 0x028b0a,
               "helpers": [0x003b28, 0x003b38],
               "counter_base": 0x000002c4},
    "p2test": {"entry": 0x027914, "end": 0x02798a,
               "helpers": [0x027744, 0x027754],
               "counter_base": 0x00000224},
}
DIP = {
    "normal": {"entry": 0x028cd0, "end": 0x028cf4},
    "p2test": {"entry": 0x027c88, "end": 0x027cac},
}


def read_u32(fw, addr):
    for lo, data in fw.runs:
        if lo <= addr and addr + 4 <= lo + len(data):
            return int.from_bytes(data[addr - lo:addr - lo + 4], "little")
    return None


def read_u8(fw, addr):
    for lo, data in fw.runs:
        if lo <= addr < lo + len(data):
            return data[addr - lo]
    return None


def rows_in(rows, lo, hi):
    return [r for r in rows if lo <= int(r["instruction"], 16) <= hi]


def old_report(name):
    """Prefer the immutable E2 commit; fall back to the local saved copy."""
    fn = f"cr16-interproc-{name}.json"
    try:
        out = subprocess.check_output(
            ["git", "show", f"{BASELINE}:tools/reports/{fn}"],
            cwd=str(ROOT), text=True, stderr=subprocess.DEVNULL)
        return json.loads(out)
    except Exception:
        p = Path("/tmp/opencode/e2-baseline") / fn
        return json.loads(p.read_text()) if p.is_file() else {"argument_propagations": []}


def key_of(a):
    return (a["call_site"], a["callee"], tuple(a["argument_pair"]),
            a["constant"])


def _use_key(u):
    return (u.get("instruction"), u.get("effective_address"))


def _match_uses(old_uses, new_uses):
    """Match every old memory use by instruction and effective address."""
    new_map = {}
    for u in new_uses:
        new_map.setdefault(_use_key(u), []).append(u)
    matched, missing = [], []
    for ou in old_uses:
        k = _use_key(ou)
        candidates = new_map.get(k)
        if candidates:
            nu = candidates.pop(0)
            matched.append({
                "instruction": ou.get("instruction"),
                "displacement": ou.get("displacement"),
                "effective_address": ou.get("effective_address"),
                "old_operation": ou.get("operation"),
                "new_operation": nu.get("operation"),
                "new_displacement": nu.get("displacement"),
                "new_effective_address": nu.get("effective_address"),
                "match": True,
            })
        else:
            missing.append({
                "instruction": ou.get("instruction"),
                "displacement": ou.get("displacement"),
                "effective_address": ou.get("effective_address"),
                "old_operation": ou.get("operation"),
                "match": False,
            })
    extra = [u for vals in new_map.values() for u in vals]
    return matched, missing, extra


def audit(name, old, new_args):
    old_args = old.get("argument_propagations", [])
    new_by_key = {}
    for a in new_args:
        new_by_key.setdefault(key_of(a), []).append(a)
    old_proven = [a for a in old_args if a.get("confidence") == "PROVEN"]
    audited = []
    counts = {"PROVEN": 0, "CANDIDATE": 0, "INVALID": 0}
    for a in sorted(old_proven, key=lambda x: x["call_site"]):
        matches = new_by_key.get(key_of(a), [])
        if not matches:
            b = None
            matched, missing, extra = [], list(a.get("uses", [])), []
            reasons = ["no matching caller constant/use under E3 path analysis"]
            cls = "INVALID"
        else:
            b = None
            matched, missing, extra = [], list(a.get("uses", [])), []
            # Prefer a new record whose uses cover every old use.
            for candidate in matches:
                m, miss, ext = _match_uses(a.get("uses", []),
                                           candidate.get("uses", []))
                if not miss:
                    b = candidate
                    matched, missing, extra = m, miss, ext
                    break
            if b is None:
                b = matches[0]
                matched, missing, extra = _match_uses(
                    a.get("uses", []), b.get("uses", []))
            if missing:
                cls = "INVALID"
                reasons = ["one or more old memory uses are missing or changed"]
            else:
                cls = b["confidence"]
                reasons = b.get("reasons", [])
        counts[cls] += 1
        audited.append({
            "image": name,
            "old_call_site": a["call_site"],
            "callee": a["callee"],
            "argument_pair": a["argument_pair"],
            "constant": a["constant"],
            "old_classification": "PROVEN",
            "new_classification": cls,
            "old_uses": a.get("uses", []),
            "use_match": {
                "matched": matched,
                "missing": missing,
                "new_extra": extra,
                "all_old_uses_matched": not missing,
            },
            "new_record": ({
                "caller_entry": b.get("caller_entry"),
                "definition_provenance": b.get("definition_provenance", []),
                "uses": b.get("uses", []),
                "reasons": b.get("reasons", []),
            } if b is not None else None),
            "reasons": reasons,
        })
    old_keys = {key_of(a) for a in old_args}
    new_only = [a for a in new_args
                if key_of(a) not in old_keys and a["confidence"] == "PROVEN"]
    return {
        "old_proven": len(old_proven),
        "new_proven": sum(1 for a in new_args if a["confidence"] == "PROVEN"),
        "new_candidate": sum(1 for a in new_args
                             if a["confidence"] == "CANDIDATE"),
        "reclassified": counts,
        "audited_old_proven": audited,
        "new_proven_not_in_e2": [
            {"call_site": a["call_site"], "callee": a["callee"],
             "argument_pair": a["argument_pair"], "constant": a["constant"],
             "caller_entry": a.get("caller_entry")}
            for a in new_only
        ],
    }


def helper_summary(entry, a):
    return I.make_summary(a["fw"], a["blocks"], a["succ"], a["preds"],
                          a["edges"], a["ops_by_insn"], entry,
                          a["addr_block"], {})


def focused_image(name, path, args):
    a = I.analyze_image(name, path, args.objdump, args.max_iterations)
    report, fw, rows = D.run_image(name, path, args.objdump,
                                   max_iters=args.max_iterations)
    # D.run_image re-disassembles; reuse the same data for instruction reads.
    dsp = DSP[name]
    dip = DIP[name]
    ptr = read_u32(fw, 0xD6)
    dsp_rows = rows_in(rows, dsp["entry"], dsp["end"])
    dip_rows = rows_in(rows, dip["entry"], dip["end"])
    edge_list = a["edges"]
    calls = [e for e in edge_list
             if e.kind == "call" and e.category == C.DIRECT_RESOLVED]
    dsp_calls = [e for e in calls if dsp["entry"] <= e.src <= dsp["end"]]
    dip_calls = [e for e in calls if dip["entry"] <= e.src <= dip["end"]]
    dsp_helpers = []
    for e in dsp_calls:
        if e.dst is None:
            continue
        dsp_helpers.append({
            "site": f"0x{e.src:06x}",
            "target": f"0x{e.dst:06x}",
            "summary": helper_summary(e.dst, a),
        })
    dip_helpers = []
    for e in dip_calls:
        if e.dst is None:
            continue
        dip_helpers.append({
            "site": f"0x{e.src:06x}",
            "target": f"0x{e.dst:06x}",
            "summary": helper_summary(e.dst, a),
        })
    dsp_out = {
        "image": name,
        "entry": f"0x{dsp['entry']:06x}",
        "entry_kind": "IRQ_VECTOR_HANDLER",
        "confidence_semantics": ("memory-operation confidence is address "
                                 "resolution only, not handler proof"),
        "memory_operations": dsp_rows,
        "pointer_cell": {
            "address": "0x000000d6",
            "image_u32": f"0x{ptr:08x}" if ptr is not None else None,
            "pointer_source": "static image value",
            "plus_0x58": f"0x{(ptr + 0x58):08x}" if ptr is not None else None,
            "runtime_writers_resolved": [],
            "address_space": "UNRESOLVED_ABOVE_24BIT",
            "status": "STATIC_POINTER_CANDIDATE",
        },
        "distinct_bases": {
            "pointer_plus_0": f"0x{(ptr + 0x58):08x}" if ptr is not None else None,
            "counter_base": f"0x{dsp['counter_base']:08x}",
            "counter_fields": [
                f"0x{dsp['counter_base'] + 0x0e:08x}",
                f"0x{dsp['counter_base'] + 0x10:08x}",
            ],
            "note": ("+0/+14/+16 in the instruction listing do not share one "
                     "base: the first is pointer+0x58, the counters are at "
                     f"0x{dsp['counter_base']:x}+0xe/+0x10"),
        },
        "helpers": dsp_helpers,
        "classification": "DSP_EVENT_OR_SOFTWARE_QUEUE_CANDIDATE",
        "slot5_evidence": False,
        "pcm_evidence": False,
        "unresolved": [
            "writers of the 0xD6 pointer cell",
            "runtime value of the pointer after loader handoff",
            "source of the 16-bit event word at pointer+0x58",
            "semantics of the two helper functions",
            "meaning of the 0xF5402=0x2000 acknowledgement",
        ],
    }
    dip_out = {
        "image": name,
        "entry": f"0x{dip['entry']:06x}",
        "confidence_semantics": ("memory-operation confidence is address "
                                 "resolution only, not handler proof"),
        "memory_operations": dip_rows,
        "value_flow": [
            {"instruction": f"0x{dip['entry'] + 0x0e:06x}",
             "note": "loadw 0xF6006 -> r0"},
            {"note": "movb r0,r2 passes only the low byte to the callee"},
            {"note": "movw 0x400,r0 overwrites r0 before the store"},
            {"note": "storw r0,0xF5402 writes 0x0400"},
            {"note": "bal callee receives r2 as an input"},
        ],
        "f6006": {
            "read_address_space": "0x000F6006",
            "pulse_address_space": "0x00FF6006",
            "alias_claim": "UNKNOWN",
            "low_byte_consumer": "callee r2 input",
        },
        "f5402": {"write_value": "0x0400", "role": "acknowledgement candidate"},
        "poll_link": {
            "polled_0xF6002": "0x25FAE normal / 0x26764 p2test",
            "status": "SEPARATE_PATH_CANDIDATE",
            "sequence_proven": False,
        },
        "callees": dip_helpers,
        "classification": "EVENT_STATUS_ACK_CANDIDATE",
        "slot5_evidence": False,
        "pcm_evidence": False,
        "unresolved": [
            "bit-level meaning of 0xF6006",
            "whether the read has read-to-clear semantics",
            "callee event-code semantics",
            "whether the callee touches 0x01000000 or a FIFO",
        ],
    }
    return a, dsp_out, dip_out, report


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--objdump", default=str(OBJDUMP))
    ap.add_argument("--out", default=str(ROOT / "tools" / "reports"))
    ap.add_argument("--max-iterations", type=int, default=D.MAX_ITERS)
    args = ap.parse_args(argv[1:])
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    soundness = {"tool": "cr16-e3-soundness-audit/1",
                 "baseline_commit": BASELINE,
                 "criterion": ("PROVEN requires a caller constant to reach "
                               "the call on all modelled paths and the callee "
                               "to preserve the pair until the memory use"),
                 "source_images": {}, "images": {}}
    callsites = {"tool": "cr16-e3-callsite-audit/1",
                 "baseline_commit": BASELINE,
                 "source_images": {}, "images": {}}
    dsp_all = {"tool": "cr16-e3-dsp-paths/1", "images": {}}
    dip_all = {"tool": "cr16-e3-dip-paths/1", "images": {}}
    handlers = {"tool": "cr16-e3-handler-candidates/1", "images": {}}
    status = 0
    for name, path in IMAGES:
        if not path.is_file():
            print(f"SKIP {name}: firmware missing")
            continue
        a, dsp, dip, df = focused_image(name, path, args)
        old = old_report(name)
        aud = audit(name, old, a["arguments"])
        soundness["images"][name] = aud
        callsites["images"][name] = {
            "arguments": a["arguments"],
            "old_proven": aud["old_proven"],
            "new_proven": aud["new_proven"],
            "new_candidate": aud["new_candidate"],
            "reclassified": aud["reclassified"],
        }
        xr = json.loads((ROOT / "tools" / "reports" /
                         "peripheral-xrefs.json").read_text())
        sha = xr["images"][name]["sha256"]
        dsp["source"] = str(path.relative_to(ROOT))
        dsp["sha256"] = sha
        dip["source"] = str(path.relative_to(ROOT))
        dip["sha256"] = sha
        soundness["source_images"][name] = {
            "source": str(path.relative_to(ROOT)), "sha256": sha}
        callsites["source_images"][name] = {
            "source": str(path.relative_to(ROOT)), "sha256": sha}
        dsp_all["images"][name] = dsp
        dip_all["images"][name] = dip
        fw = a["fw"]
        handlers["images"][name] = {
            "source": str(path.relative_to(ROOT)),
            "sha256": sha,
            "slot5_handler_found": False,
            "slot5_status": "CANDIDATE_ONLY",
            "dsp_int": dsp["classification"],
            "dip_int": dip["classification"],
            "pcm_named_handlers": 0,
            "0x01000000": {
                "fill_range": "0x01000002…0x010003FE",
                "fill_loop": {
                    "control": ("0x25f90" if name == "normal" else
                                "0x26750"),
                    "static_store": ("0x25d0" if name == "normal" else
                                     "0x1e8c"),
                    "iterations": "1…511",
                    "classification": "RAM_INIT_CANDIDATE",
                },
                "d6_pointer": dsp["pointer_cell"],
                "classification": "UNRESOLVED",
                "address_space": "UNRESOLVED",
                "runtime_pointer_candidate": True,
                "runtime_pcm_buffer_proven": False,
                "note": ("0x01000000 is outside the 24-bit address range; the "
                         "fill loop has one static store executed over 511 "
                         "iterations.  The dsp pointer target is outside the "
                         "fill range.  The region is not named PCM"),
            },
            "remaining": [
                "0xD6 runtime writers / loader relocation",
                "source of the DSP event word",
                "0xF6006 bit semantics and callee event decoding",
                "unresolved indirect/table sites",
                "stack-passed arguments",
            ],
            "limitations": [
                "no proven slot-5 consumer",
                "no physical wire order claimed",
            ],
        }
        print(f"{name}: old={aud['old_proven']} new={aud['new_proven']} "
              f"candidate={aud['new_candidate']} "
              f"reclassified={aud['reclassified']}")
        if not a["converged"]:
            status = 1
    if status:
        for fn, data in (
                ("cr16-e3-soundness-audit.incomplete.json", soundness),
                ("cr16-e3-callsite-audit.incomplete.json", callsites),
                ("cr16-e3-dsp-paths.incomplete.json", dsp_all),
                ("cr16-e3-dip-paths.incomplete.json", dip_all),
                ("cr16-e3-handler-candidates.incomplete.json", handlers)):
            (out / fn).write_text(json.dumps(data, indent=2) + "\n")
        print("incomplete E3 analysis; reports not promoted", file=sys.stderr)
        return 1
    for fn, data in (
            ("cr16-e3-soundness-audit.json", soundness),
            ("cr16-e3-callsite-audit.json", callsites),
            ("cr16-e3-dsp-paths.json", dsp_all),
            ("cr16-e3-dip-paths.json", dip_all),
            ("cr16-e3-handler-candidates.json", handlers)):
        (out / fn).write_text(json.dumps(data, indent=2) + "\n")
    return status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
