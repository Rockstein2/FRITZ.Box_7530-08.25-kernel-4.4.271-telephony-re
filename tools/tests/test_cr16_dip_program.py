#!/usr/bin/env python3
"""Offline E3.4 regression fixtures and fresh seven-report replay."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import cr16_address_spaces as A  # noqa: E402
import cr16_cfg as C  # noqa: E402
import cr16_dip_program as P  # noqa: E402

fails = skips = 0


def check(label, actual, expected):
    global fails
    if actual != expected:
        print(f"FAIL {label}: {repr(actual)[:240]} != {repr(expected)[:240]}")
        fails += 1
    else:
        print(f"PASS {label}")


check("local post-increment count", P.loop_iterations(1, 512), 511)
check("last boundary writes once", P.loop_iterations(512, 512), 1)
check("wrong branch orientation fails", P.loop_iterations(1, 512,
      compare="DEST_GREATER"), None)
check("clobbered counter fails", P.loop_iterations(1, 512, clobber=True), None)
check("conditional store fails", P.loop_iterations(1, 512,
      conditional_store=True), None)
check("unknown initial fails", P.loop_iterations(0, 512), None)
check("multiple writers retain both possible values",
      P.memory_cell([{"value": "0x1001", "instruction": "0x1"},
                     {"value": "0x12aa", "instruction": "0x2"}])
      ["possible_values"], ["0x1001", "0x12aa"])
check("unordered writers have no final value",
      P.memory_cell([{"value": "0x1001", "instruction": "0x1"},
                     {"value": "0x12aa", "instruction": "0x2"}])
      ["final_value"], None)
check("runtime expression not fabricated as constant",
      P.memory_cell([{"value": "(high<<8)|low", "instruction": "0x3"}])
      ["possible_values"], ["(high<<8)|low"])
check("unknown indirect writer not silently erased",
      P.memory_cell([{"value": "UNKNOWN", "instruction": "indirect"}])
      ["final_value"], None)
insns = {0x100: C.Insn(0x100, 2, "movw", "r0,r2", b"\0\0"),
         0x102: C.Insn(0x102, 2, "storw", "r2,0x0:s(r1,r0)", b"\0\0")}
fw = C.Firmware(runs=[(0x100, bytes(8))], insns=insns)
check("direct segment continuity", P.checked_sequence(fw, [0x100, 0x102]),
      True)
fw.insns[0x100] = C.Insn(0x100, 2, "br", "*+0x102:s", b"\0\0")
check("jump cannot masquerade as straight line",
      P.checked_sequence(fw, [0x100, 0x102]), False)

if not A.OBJDUMP.is_file() or any(not p.is_file() for _, p in A.IMAGES):
    skips += 1
    print("SKIP replay: CR16 oracle or firmware unavailable")
else:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        command = [sys.executable, str(ROOT / "tools" / "cr16_dip_program.py"),
                   "--out", td]
        proc = subprocess.run(command, capture_output=True, text=True)
        check("fresh replay exits zero", proc.returncode, 0)
        for fn in P.NAMES:
            check(f"fresh {fn}", (out / fn).is_file(), True)
            if (out / fn).is_file():
                check(f"replay matches {fn}",
                      json.loads((out / fn).read_text()),
                      json.loads((ROOT / "tools" / "reports" / fn).read_text()))
        original = {fn: (out / fn).read_bytes() for fn in P.NAMES}
        fail = subprocess.run(command + ["--objdump", str(out / "missing")],
                              capture_output=True, text=True)
        check("missing oracle fails", fail.returncode != 0, True)
        check("missing oracle preserves bundle",
              {fn: (out / fn).read_bytes() for fn in P.NAMES}, original)
        check("diagnostic exists", (out / "cr16-e34.incomplete.json").is_file(),
              True)
        with patch.object(P.D, "run_image", return_value=(
                {"converged": False}, None, [])):
            try:
                P.build(str(A.OBJDUMP))
                check("NON_CONVERGED rejects report", False, True)
            except ValueError as exc:
                check("NON_CONVERGED rejects report", "NON_CONVERGED" in str(exc),
                      True)
            check("NON_CONVERGED CLI exits nonzero",
                  P.main(["--out", td]) != 0, True)
        check("NON_CONVERGED preserves old bundle",
              {fn: (out / fn).read_bytes() for fn in P.NAMES}, original)
        with patch.object(A, "REFERENCE_SHA", {n: "0" * 64
                                               for n in ("normal", "p2test")}):
            check("wrong SHA fails", P.main(["--out", td]) != 0, True)
        check("wrong SHA preserves old bundle",
              {fn: (out / fn).read_bytes() for fn in P.NAMES}, original)
        for n in ("normal", "p2test"):
            loop = json.loads((out / P.NAMES[2]).read_text())["images"][n]
            check(f"{n}: local 511 only",
                  (loop["dataflow_provenance"]["local_loop_count"],
                   loop["dataflow_provenance"]["all_path_loop_count"]),
                  (511, None))
            cells = json.loads((out / P.NAMES[1]).read_text())["images"][n]
            check(f"{n}: cell 2 includes static word",
                  "0x12aa" in cells["possible_final_values"][2]
                  ["possible_values"], True)
            check(f"{n}: cell 2 not finalised",
                  cells["possible_final_values"][2]["final_value"], None)

print(f"{fails} failure(s), {skips} skip(s)")
raise SystemExit(bool(fails))
