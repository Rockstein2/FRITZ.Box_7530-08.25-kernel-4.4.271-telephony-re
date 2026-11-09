#!/usr/bin/env python3
"""Tests for the conservative cross-block CR16 dataflow.

Run: python3 tools/tests/test_cr16_dataflow.py

The merge tests are pure; the firmware tests are SKIP when the CR16 oracle or
the external firmware is unavailable.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src" / "mock"))

import cr16_cfg as C  # noqa: E402
import cr16_dataflow as D  # noqa: E402
import cr16_peripheral_xrefs as X  # noqa: E402

OBJDUMP = Path("/tmp/opencode/cr16/build/binutils/objdump")
FW = ROOT.parent / "firmware" / "dectfw_secondlevel_441.hex"
P2 = ROOT.parent / "firmware" / "dectfw_secondlevel_441p2test.hex"

fails = 0
skips = 0


def check(name, got, want):
    global fails
    if got == want:
        print(f"PASS {name}")
    else:
        print(f"FAIL {name}: got {got!r} want {want!r}")
        fails += 1


def skip(name, why):
    global skips
    print(f"SKIP {name}: {why}")
    skips += 1


def state(v=0):
    return {("P", "r1", "r0"): ("KNOWN32", v)}


def test_merge():
    check("same constant survives", D.merge_state([state(0xF6000),
                                                   state(0xF6000)]),
          state(0xF6000))
    check("different constants do not survive",
          D.merge_state([state(0xF6000), state(0xF6004)]), {})
    check("missing predecessor kills a value",
          D.merge_state([state(0xF6000), {}]), {})
    check("empty join is empty", D.merge_state([{}, {}]), {})
    provs = [{("P", "r1", "r0"): ["0x10"]},
             {("P", "r1", "r0"): ["0x20"]}]
    check("provenance is unioned only for a surviving key",
          D.merge_provenance(provs, {("P", "r1", "r0")}),
          {("P", "r1", "r0"): ["0x10", "0x20"]})


def test_resolve():
    insn = C.Insn(0, 4, "storw", "r2,0x0:s(r1,r0)", b"\x20\xd0")
    akind, effective, expr, key = D.resolve_operand(insn, "WRITE",
                                                     state(0xF6000))
    check("cross-block constant pair resolves",
          (akind, effective, key), ("RESOLVED", "0x000f6000",
                                    ("P", "r1", "r0")))
    check("unknown pair stays unknown",
          D.resolve_operand(insn, "WRITE", {})[0], "UNKNOWN")
    insn2 = C.Insn(2, 4, "storw", "r2,0x6:s(r1,r0)", b"\x20\xd0")
    check("base plus offset resolves",
          D.resolve_operand(insn2, "WRITE", state(0xF6000))[1],
          "0x000f6006")
    insn3 = C.Insn(4, 4, "loadw", "0x6:s(r1,r0),r2", b"\x20\x90")
    check("load base plus offset resolves",
          D.resolve_operand(insn3, "READ", state(0xF6000))[1],
          "0x000f6006")
    insn4 = C.Insn(6, 2, "loadw", "0x0:s(r12),r2", b"\x00\x00")
    check("indexed form is not a constant",
          D.resolve_operand(insn4, "READ", {})[0], "INDEXED")


def test_firmware():
    if not OBJDUMP.is_file():
        skip("firmware dataflow", "CR16 objdump missing")
        return
    if not FW.is_file():
        skip("firmware dataflow", "normal firmware missing")
        return
    report, fw, rows = D.run_image("normal", FW, str(OBJDUMP))
    check("normal dataflow has blocks", report["blocks"] > 1000, True)
    check("normal dataflow has cross-block constants",
          report["state_blocks"] > 0, True)
    check("normal dataflow finds new resolved accesses",
          report["newly_resolved_count"] > 0, True)
    check("normal CFG records direct call edges",
          report["call_edges"] > 0, True)
    check("normal CFG records return blocks",
          report["return_blocks"] > 0, True)
    blocks, starts, _ab, succ, _preds = D.blocks_and_successors(fw)
    call_blocks = [s for s in starts
                   if fw.insns[blocks[s][-1]].mnemonic in D.CALLS]
    return_blocks = [s for s in starts
                     if fw.insns[blocks[s][-1]].mnemonic in D.RETS]
    check("a call block has a callee and a continuation",
          any(len(succ[s]) >= 2 for s in call_blocks), True)
    check("return blocks have no normal successor",
          all(not succ[s] for s in return_blocks), True)
    # 0x0010cc was UNKNOWN in E0 and must have a cross-block provenance.
    hit = [r for r in report["newly_resolved"]
           if r["instruction"] == "0x0010cc"]
    check("known cross-block tbitw is resolved",
          bool(hit) and hit[0]["address_kind"] == "RESOLVED", True)
    check("known cross-block row has provenance",
          bool(hit) and len(hit[0]["provenance"]) > 0, True)
    # The dataflow must not turn all unknown indexed accesses into constants.
    check("indexed accesses remain represented",
          any(r["address_kind"] == "INDEXED" for r in rows), True)
    if P2.is_file():
        rep2, _fw2, _rows2 = D.run_image("p2test", P2, str(OBJDUMP))
        check("p2test has blocks", rep2["blocks"] > 1000, True)
        check("p2test has cross-block constants",
              rep2["state_blocks"] > 0, True)
    # A deliberately tiny iteration cap must not be reported as converged.
    forced, _fw3, _rows3 = D.run_image("normal", FW, str(OBJDUMP),
                                       max_iters=1)
    check("forced iteration cap reports NON_CONVERGED",
          forced["analysis_status"], "NON_CONVERGED")
    check("forced cap does not claim PROVEN new rows",
          all(r.get("confidence") == "CANDIDATE"
              for r in forced["newly_resolved"]), True)
    with tempfile.TemporaryDirectory() as td:
        sentinel = Path(td) / "cr16-dataflow-normal.json"
        sentinel.write_text('{"sentinel": true}\n')
        p = subprocess.run(
            [sys.executable, str(ROOT / "cr16_dataflow.py"),
             "--objdump", str(OBJDUMP), "--max-iterations", "1",
             "--out", td],
            cwd=str(ROOT.parent), capture_output=True, text=True)
        check("NON_CONVERGED CLI exits non-zero", p.returncode != 0, True)
        check("NON_CONVERGED CLI writes incomplete report",
              (Path(td) / "cr16-dataflow-normal.incomplete.json").is_file(),
              True)
        check("NON_CONVERGED CLI does not overwrite confirmed report",
              sentinel.read_text(), '{"sentinel": true}\n')


def test_reports():
    p = ROOT / "reports" / "cr16-dataflow-normal.json"
    if not p.is_file():
        skip("dataflow reports", "report missing")
        return
    d = json.loads(p.read_text())
    check("report records source stats", "source_stats" in d, True)
    check("report records newly resolved", "newly_resolved" in d, True)
    check("report records remaining categories", "new_stats" in d, True)
    check("report records limitations", "limitations" in d, True)


def main():
    test_merge()
    test_resolve()
    test_firmware()
    test_reports()
    print(f"\n{fails} failure(s), {skips} skip(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
