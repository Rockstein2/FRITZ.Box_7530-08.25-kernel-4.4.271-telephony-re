#!/usr/bin/env python3
"""Tests for the E2 interprocedural/table/IRQ reports."""
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


class _FakeFw:
    def __init__(self, insns):
        self.insns = insns


def _insn(addr, mnemonic, operands="", size=2):
    return C.Insn(addr, size, mnemonic, operands, b"\x00" * size)


def test_may_written_paths():
    # Diamond: one branch writes r0, the other does not.  The join must see
    # r0 as possibly written; a local linear sweep over address order would
    # not prove this.
    fw = _FakeFw({
        0x10: _insn(0x10, "movw", "$0x1,r0"),
        0x12: _insn(0x12, "movw", "$0x2,r1"),
        0x14: _insn(0x14, "nop"),
        0x16: _insn(0x16, "movw", "$0x3,r2"),
        0x18: _insn(0x18, "nop"),
    })
    blocks = {0x10: [0x10], 0x12: [0x12], 0x14: [0x14],
              0x16: [0x16], 0x18: [0x18]}
    succ = {0x10: {0x12, 0x14}, 0x12: {0x16}, 0x14: {0x16},
            0x16: {0x18}}
    preds = {0x12: {0x10}, 0x14: {0x10}, 0x16: {0x12, 0x14},
             0x18: {0x16}}
    addr_block = {a: b for b, bs in blocks.items() for a in bs}
    m = I._may_written(0x10, fw, blocks, preds, succ, addr_block)
    check("diamond: branch write reaches the join",
          "r1" in m["before"][0x16], True)
    check("diamond: unmodified register is not marked written",
          "r2" not in m["before"][0x16], True)
    check("diamond: may analysis converges", m["converged"], True)

    # A call is a whole-register clobber; a following use cannot preserve a
    # caller pair.
    fw2 = _FakeFw({0x20: _insn(0x20, "bal", "(ra),*+0x0"),
                   0x22: _insn(0x22, "nop")})
    b2 = {0x20: [0x20, 0x22]}
    m2 = I._may_written(0x20, fw2, b2, {}, {}, {0x20: 0x20, 0x22: 0x20})
    check("call clobbers every modelled register",
          "r3" in m2["before"][0x22], True)

    # Register-list memory forms are conservative clobbers.
    fw3 = _FakeFw({0x30: _insn(0x30, "loadm", "$0x1,r0"),
                   0x32: _insn(0x32, "nop")})
    b3 = {0x30: [0x30, 0x32]}
    m3 = I._may_written(0x30, fw3, b3, {}, {}, {0x30: 0x30, 0x32: 0x30})
    check("loadm is a whole-register clobber",
          "r5" in m3["before"][0x32], True)

    # Entry in the middle of a block is not a confirmed entry.
    m4 = I._may_written(0x42, fw3, b3, {}, {}, {0x30: 0x30, 0x32: 0x30})
    check("mid-block entry is marked inferred", m4["entry_mid"], True)
    check("mid-block entry cannot be complete", m4["complete"], False)

    # An external predecessor into a non-entry block makes incoming state
    # unknown, never an invented empty path.
    fw5 = _FakeFw({0x60: _insn(0x60, "nop"), 0x62: _insn(0x62, "nop")})
    b5 = {0x60: [0x60], 0x62: [0x62]}
    m5 = I._may_written(0x60, fw5, b5, {0x62: {0x99}}, {0x60: {0x62}},
                        {0x60: 0x60, 0x62: 0x62})
    check("external predecessor makes the block incomplete",
          m5["complete"], False)
    check("external predecessor is never an empty path",
          "r0" in m5["before"][0x62], True)

    # Indirect target parser: `jump (ra)` is not a table pair.
    check("register-indirect target parser keeps RA separate",
          I._indirect_target(_insn(0x50, "jump", "(ra)")), {"ra"})
    check("register-indirect target parser keeps the pair",
          I._indirect_target(_insn(0x52, "jal", "(r7,r6)")), {"r7", "r6"})


test_may_written_paths()

for name, entries, calls, proven in (
        ("normal", 432, 1489, 91), ("p2test", 403, 1371, 42)):
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
    check(f"{name}: summaries record CFG completeness",
          all("cfg_completeness" in s
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
        check(f"{name}: table report does not claim decoded widths",
              t["capabilities"]["table_entry_widths_decoded"] == [], True)
        check(f"{name}: table report does not claim decoded endianness",
              t["capabilities"]["endianness_decoded"] == [], True)
        check(f"{name}: table candidates keep linkage status",
              all("def_use_link" in x
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
        summaries = {s["entry"]: s for s in d["function_summaries"]}
        check(f"{name}: IRQ indirect count uses summary field",
              all(x["indirect_sites"] ==
                  summaries.get(x["handler"], {})
                  .get("possible_call_targets", {})
                  .get("indirect_sites", 0)
                  for x in i["images"][name]["vectors"]), True)

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
