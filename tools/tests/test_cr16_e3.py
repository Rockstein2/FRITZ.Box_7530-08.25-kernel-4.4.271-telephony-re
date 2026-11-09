#!/usr/bin/env python3
"""Regression checks for the FON-E3 soundness audit and focused traces."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REP = ROOT / "reports"
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
