#!/usr/bin/env python3
"""Regression checks for the FON-E3 soundness audit and focused traces."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REP = ROOT / "reports"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "src" / "mock"))
import cr16_cfg as C  # noqa: E402
import cr16_e3 as E  # noqa: E402
import cr16_interproc as I  # noqa: E402
fails = 0
skips = 0


def check(name, got, want):
    global fails
    if got == want:
        print(f"PASS {name}")
    else:
        print(f"FAIL {name}: got {got!r} want {want!r}")
        fails += 1


def load(name):
    p = REP / name
    if not p.is_file():
        print(f"SKIP {name}: missing")
        return None
    return json.loads(p.read_text())


def _insn(addr, mnemonic, operands):
    return C.Insn(addr, 2, mnemonic, operands, b"\x00\x00")


class _Fw:
    def __init__(self, insns):
        self.insns = insns


# Independent unit fixture: an old proof with the same call/callee/pair/value
# but a different memory-use address must not be accepted.
_old = {"argument_propagations": [{
    "call_site": "0x10", "callee": "0x20", "argument_pair": ["r2", "r3"],
    "constant": "0x100", "confidence": "PROVEN",
    "uses": [{"instruction": "0x21", "operation": "READ",
              "effective_address": "0x100"}],
}]}
_new = [{
    "call_site": "0x10", "callee": "0x20", "argument_pair": ["r2", "r3"],
    "constant": "0x100", "confidence": "PROVEN",
    "uses": [{"instruction": "0x22", "operation": "READ",
              "effective_address": "0x100", "displacement": 0}],
}]
_aud = E.audit("fixture", _old, _new)
check("E3 audit rejects a changed memory-use address",
      _aud["audited_old_proven"][0]["new_classification"], "INVALID")
check("E3 audit marks the old use missing",
      _aud["audited_old_proven"][0]["use_match"]["all_old_uses_matched"],
      False)

# Independent table fixture: a nearer non-load write kills a preceding load.
_ops_ok = {0x100: [{"instruction": "0x000100", "operation": "READ",
                    "address_kind": "RESOLVED",
                    "effective_address": "0x200", "expression": None,
                    "width_bits": 16}]}
_fw_ok = _Fw({0x100: _insn(0x100, "loadw", "0x0:(r1),r0")})
_c, _s, _n = I._find_table_consumer(_fw_ok, [0x100, 0x102], 0x102,
                                    {"r0"}, _ops_ok)
check("E3 table fixture links a load to the target", _s,
      "LOAD_WRITES_TARGET")
_ops_kill = dict(_ops_ok)
_ops_kill[0x102] = [{"instruction": "0x000102", "operation": "READ",
                     "address_kind": "RESOLVED",
                     "effective_address": "0x202", "expression": None,
                     "width_bits": 16}]
_fw_kill = _Fw({0x100: _insn(0x100, "loadw", "0x0:(r1),r0"),
                0x102: _insn(0x102, "movw", "$0x0,r0")})
_c, _s, _n = I._find_table_consumer(_fw_kill, [0x100, 0x102, 0x104],
                                    0x104, {"r0"}, _ops_kill)
check("E3 table fixture rejects a later target clobber", _s,
      "TARGET_WRITTEN_BEFORE_LOAD")

# Independent IRQ tree fixture: sibling branches must not share a recursion
# stack, so the common leaf is not falsely marked as a cycle.
_sum = {
    "0x00000a": {"possible_call_targets": {"indirect_sites": 0,
        "direct_edges": [{"site": "0xa1", "target": "0x00000b",
                          "confidence": "DIRECT_RESOLVED"},
                         {"site": "0xa2", "target": "0x00000c",
                          "confidence": "DIRECT_RESOLVED"}]}},
    "0x00000b": {"possible_call_targets": {"indirect_sites": 0,
        "direct_edges": [{"site": "0xb1", "target": "0x00000d",
                          "confidence": "DIRECT_RESOLVED"}]}},
    "0x00000c": {"possible_call_targets": {"indirect_sites": 0,
        "direct_edges": [{"site": "0xc1", "target": "0x00000d",
                          "confidence": "DIRECT_RESOLVED"}]}},
    "0x00000d": {"possible_call_targets": {"indirect_sites": 0,
                                           "direct_edges": []}},
}
_tree = I._irq_tree(0xA, _sum)
_b = _tree["direct_calls"][0]["callee"]
_c = _tree["direct_calls"][1]["callee"]
check("E3 sibling IRQ branches both reach the shared leaf",
      (_b["direct_calls"][0]["callee"].get("cycle_or_depth_limit", False),
       _c["direct_calls"][0]["callee"].get("cycle_or_depth_limit", False)),
      (False, False))

# Pointer arithmetic fixture independent of the committed JSON.
_pf = _Fw({})
_pf.runs = [(0xD6, b"\x80\x7f\x02\x01")]
check("E3 0xD6 pointer is little-endian 0x01027F80",
      E.read_u32(_pf, 0xD6), 0x01027F80)

# Fail-closed CLI: no normal reports may be written on forced NON_CONVERGED.
_objdump = Path("/tmp/opencode/cr16/build/binutils/objdump")
if _objdump.is_file():
    with tempfile.TemporaryDirectory() as td:
        _r = subprocess.run(
            [sys.executable, str(ROOT / "cr16_interproc.py"),
             "--objdump", str(_objdump), "--max-iterations", "1",
             "--out", td], cwd=str(ROOT.parent), capture_output=True,
            text=True)
        check("E3 interproc NON_CONVERGED exits non-zero",
              _r.returncode != 0, True)
        check("E3 interproc does not write normal report",
              (Path(td) / "cr16-interproc-normal.json").exists(), False)
        check("E3 interproc writes incomplete report",
              (Path(td) / "cr16-interproc-normal.incomplete.json").is_file(),
              True)
    with tempfile.TemporaryDirectory() as td:
        _r = subprocess.run(
            [sys.executable, str(ROOT / "cr16_e3.py"),
             "--objdump", str(_objdump), "--max-iterations", "1",
             "--out", td], cwd=str(ROOT.parent), capture_output=True,
            text=True)
        check("E3 focused NON_CONVERGED exits non-zero",
              _r.returncode != 0, True)
        check("E3 focused does not write normal report",
              (Path(td) / "cr16-e3-soundness-audit.json").exists(), False)
        check("E3 focused writes incomplete report",
              (Path(td) /
               "cr16-e3-soundness-audit.incomplete.json").is_file(), True)

for name in ("cr16-e3-soundness-audit.json",
             "cr16-e3-dsp-paths.json", "cr16-e3-dip-paths.json",
             "cr16-e3-callsite-audit.json",
             "cr16-e3-handler-candidates.json"):
    check(f"E3 report exists: {name}", (REP / name).is_file(), True)

s = load("cr16-e3-soundness-audit.json")
if s is not None:
    check("E3 audit keeps E2 baseline", s["baseline_commit"],
          "89599db81e2816cf323a554bb4054175d06dad25")
    for name, old, proven, cand in (("normal", 25, 91, 82),
                                    ("p2test", 10, 42, 92)):
        d = s["images"][name]
        check(f"E3 {name}: audited old PROVEN", d["old_proven"], old)
        check(f"E3 {name}: new PROVEN after path analysis",
              d["new_proven"], proven)
        check(f"E3 {name}: new CANDIDATE after path analysis",
              d["new_candidate"], cand)
        check(f"E3 {name}: all old records reclassified",
              len(d["audited_old_proven"]), old)
        check(f"E3 {name}: every audit has instruction provenance",
              all(a["old_uses"] for a in d["audited_old_proven"]), True)

c = load("cr16-e3-callsite-audit.json")
if c is not None:
    for name in ("normal", "p2test"):
        check(f"E3 {name}: callsite audit carries arguments",
              len(c["images"][name]["arguments"]) > 0, True)

for name in ("normal", "p2test"):
    d = load("cr16-e3-dsp-paths.json")
    if d is None:
        break
    x = d["images"][name]
    check(f"E3 {name}: DSP pointer cell", x["pointer_cell"]["address"],
          "0x000000d6")
    check(f"E3 {name}: DSP pointer value", x["pointer_cell"]["image_u32"],
          "0x01027f80")
    check(f"E3 {name}: DSP pointer +0x58",
          x["pointer_cell"]["plus_0x58"], "0x01027fd8")
    check(f"E3 {name}: DSP pointer is not proven runtime",
          x["pointer_cell"]["status"], "STATIC_POINTER_CANDIDATE")
    check(f"E3 {name}: DSP has helpers", len(x["helpers"]), 2)
    irq = load("cr16-irq-paths.json")
    if irq is not None:
        vec = [v for v in irq["images"][name]["vectors"]
               if v["reference_name"] == "dsp_int"]
        check(f"E3 {name}: DSP IRQ has a callgraph",
              bool(vec and vec[0]["callgraph"].get("direct_calls")), True)
    check(f"E3 {name}: DSP is not named PCM", x["pcm_evidence"], False)
    check(f"E3 {name}: DSP is not named slot-5", x["slot5_evidence"], False)

for name, base, fields in (("normal", "0x000002c4",
                            ["0x000002d2", "0x000002d4"]),
                           ("p2test", "0x00000224",
                            ["0x00000232", "0x00000234"])):
    d = load("cr16-e3-dsp-paths.json")
    if d is None:
        break
    x = d["images"][name]
    check(f"E3 {name}: DSP counter base", x["distinct_bases"]["counter_base"],
          base)
    check(f"E3 {name}: DSP counter fields",
          x["distinct_bases"]["counter_fields"], fields)

for name in ("normal", "p2test"):
    d = load("cr16-e3-dip-paths.json")
    if d is None:
        break
    x = d["images"][name]
    addrs = {o.get("effective_address") for o in x["memory_operations"]}
    check(f"E3 {name}: DIP reads 0xF6006", "0x000f6006" in addrs, True)
    check(f"E3 {name}: DIP writes 0xF5402", "0x000f5402" in addrs, True)
    check(f"E3 {name}: DIP does not claim an alias",
          x["f6006"]["alias_claim"], "UNKNOWN")
    check(f"E3 {name}: DIP has a callee", len(x["callees"]) >= 1, True)

h = load("cr16-e3-handler-candidates.json")
if h is not None:
    for name in ("normal", "p2test"):
        x = h["images"][name]
        check(f"E3 {name}: no slot-5 handler", x["slot5_handler_found"],
              False)
        check(f"E3 {name}: no PCM-named handler",
              x["pcm_named_handlers"], 0)
        check(f"E3 {name}: 0x01000000 is not PCM",
              x["0x01000000"]["runtime_pcm_buffer_proven"], False)
        check(f"E3 {name}: 0x01000000 address space stays unresolved",
              x["0x01000000"]["classification"], "UNRESOLVED")
        check(f"E3 {name}: 0x01000000 keeps a runtime-pointer candidate",
              x["0x01000000"]["runtime_pointer_candidate"], True)

# Reproducibility of the focused reports.
_objdump = Path("/tmp/opencode/cr16/build/binutils/objdump")
if _objdump.is_file():
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run(
            [sys.executable, str(ROOT / "cr16_e3.py"),
             "--objdump", str(_objdump), "--out", td],
            cwd=str(ROOT.parent), capture_output=True, text=True)
        check("E3 fresh run exits cleanly", r.returncode, 0)
        for fn in ("cr16-e3-soundness-audit.json",
                   "cr16-e3-dsp-paths.json",
                   "cr16-e3-dip-paths.json",
                   "cr16-e3-callsite-audit.json",
                   "cr16-e3-handler-candidates.json"):
            got = Path(td) / fn
            want = REP / fn
            check(f"E3 report reproduces: {fn}",
                  json.loads(got.read_text()) if got.is_file() else None,
                  json.loads(want.read_text()) if want.is_file() else None)
else:
    print("SKIP E3 reproducibility: oracle missing")

print(f"\n{fails} failure(s), {skips} skip(s)")
sys.exit(1 if fails else 0)
