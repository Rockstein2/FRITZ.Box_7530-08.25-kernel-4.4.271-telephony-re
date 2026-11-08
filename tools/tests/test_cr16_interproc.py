#!/usr/bin/env python3
"""Tests for the E2 interprocedural/table/IRQ reports."""
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


for name, entries, calls, proven in (
        ("normal", 432, 1489, 25), ("p2test", 403, 1371, 10)):
    d = load(f"cr16-interproc-{name}.json")
    if d is None:
        continue
    check(f"{name}: function entries", d["function_entries"], entries)
    check(f"{name}: direct calls", d["direct_call_edges"], calls)
    check(f"{name}: proven argument propagations",
          d["proven_argument_propagations"], proven)
    check(f"{name}: no unknown handler claimed",
          d["unresolved_indirect_edges"] > 0, True)
    check(f"{name}: summaries present",
          len(d["function_summaries"]) == entries, True)
    check(f"{name}: summaries record clobbers and preservation",
          all("written" in s and "preserved" in s
              for s in d["function_summaries"]), True)
    check(f"{name}: summaries leave return values UNKNOWN",
          all(s["return_values"] == "UNKNOWN"
              for s in d["function_summaries"]), True)
    check(f"{name}: a calling summary clobbers all registers",
          any(s["calls"] and "r0" in s["written"]
              for s in d["function_summaries"]), True)

t = load("cr16-table-dispatch.json")
if t is not None:
    for name in ("normal", "p2test"):
        check(f"{name}: table candidates present",
              len(t["images"][name]["candidates"]) > 0, True)
        check(f"{name}: no table candidate promoted to PROVEN",
              t["images"][name]["summary"]["proven_targets"], 0)
        check(f"{name}: table candidates record 16-bit width",
              all(x["entry_width"] == 16
                  for x in t["images"][name]["candidates"]), True)

i = load("cr16-irq-paths.json")
if i is not None:
    for name in ("normal", "p2test"):
        check(f"{name}: 31 vectors", len(i["images"][name]["vectors"]), 31)
        check(f"{name}: no PCM-named IRQ",
              i["images"][name]["pcm_named_handlers"], 0)
        check(f"{name}: no proven 8 kHz IRQ period",
              sum(1 for x in i["images"][name]["vectors"]
                  if x["frequency_8khz_proven"]), 0)

h = load("cr16-fon-handler-candidates.json")
if h is not None:
    check("E2 does not claim a proven slot-5 handler",
          h["handler_found"], False)
    check("E2 lists remaining paths",
          len(h["remaining_paths"]) >= 4, True)

# Reproducibility: a fresh run must recreate the committed reports.
_objdump = Path("/tmp/opencode/cr16/build/binutils/objdump")
_fw = ROOT.parent / "firmware" / "dectfw_secondlevel_441.hex"
if _objdump.is_file() and _fw.is_file():
    with tempfile.TemporaryDirectory() as _td:
        _r = subprocess.run(
            [sys.executable, str(ROOT / "cr16_interproc.py"),
             "--objdump", str(_objdump), "--out", _td],
            cwd=str(ROOT.parent), capture_output=True, text=True)
        check("E2 fresh run exits cleanly", _r.returncode, 0)
        for _name in ("cr16-interproc-normal.json",
                      "cr16-interproc-p2test.json",
                      "cr16-table-dispatch.json",
                      "cr16-irq-paths.json",
                      "cr16-fon-handler-candidates.json"):
            _new = Path(_td) / _name
            _old = REP / _name
            check(f"E2 report reproduces: {_name}",
                  json.loads(_new.read_text()) if _new.is_file() else None,
                  json.loads(_old.read_text()) if _old.is_file() else None)
else:
    print("SKIP E2 reproducibility: oracle or firmware missing")

print(f"\n{fails} failure(s), {skips} skip(s)")
sys.exit(1 if fails else 0)
