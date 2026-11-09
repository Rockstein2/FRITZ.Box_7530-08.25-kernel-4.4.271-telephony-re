#!/usr/bin/env python3
"""Bounded IRQ pointer/dispatch checks and fresh report replay."""
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
import cr16_irq_event_trace as T  # noqa: E402

fails = skips = 0


def check(label, got, want):
    global fails
    if got != want:
        fails += 1
        print(f"FAIL {label}: {repr(got)[:200]} != {repr(want)[:200]}")
    else:
        print(f"PASS {label}")


direct, unknown = T.pointer_uses([
    {"instruction": "0x10", "operation": "WRITE", "effective_address":
     "0x000000d5", "width_bits": 32},
    {"instruction": "0x12", "operation": "READ", "effective_address":
     "0x000000d6", "width_bits": 32},
    {"instruction": "0x14", "operation": "WRITE", "effective_address": None,
     "width_bits": 16}])
check("overlap detects unaligned direct writer", direct[0]["instruction"],
      "0x10")
check("unknown pointer write not mistaken for absence", unknown, 1)
branch = C.Insn(0x25db4, 2, "beq", "*+0x25dbe:s", bytes.fromhex("0510"))
target = C.Insn(0x25dbe, 2, "movb", "$0x4:s,r2", bytes.fromhex("4258"))
fw = C.Firmware(runs=[(0x25db4, bytes(0x20))],
                insns={branch.addr: branch, target.addr: target})
check("direct event dispatch fixture", T.DIP.edge(fw, 0x25db4, 0x25dbe),
      True)
indirect = C.Insn(0x25db6, 2, "jump", "(r1,r0)", bytes.fromhex("ee0a"))
fw.insns[indirect.addr] = indirect
check("indirect event dispatch unresolved",
      C.classify_insn(indirect, fw)[0].dst, None)
with patch.object(T.D, "run_image", return_value=(
        {"converged": False, "analysis_status": "NON_CONVERGED"}, None, [])):
    try:
        T.build(str(A.OBJDUMP))
        check("NON_CONVERGED fails closed", False, True)
    except ValueError as exc:
        check("NON_CONVERGED fails closed", "NON_CONVERGED" in str(exc), True)

if not A.OBJDUMP.is_file() or any(not p.is_file() for _, p in A.IMAGES):
    skips += 1
    print("SKIP fresh replay: firmware/CR16 oracle unavailable")
else:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        r = subprocess.run([sys.executable, str(ROOT / "tools" /
                                                  "cr16_irq_event_trace.py"),
                            "--out", td], capture_output=True, text=True)
        check("replay success", r.returncode, 0)
        for fn in T.FILENAMES:
            check(f"fresh {fn}", (p / fn).is_file(), True)
            if (p / fn).is_file():
                check(f"replay {fn}", json.loads((p / fn).read_text()),
                      json.loads((ROOT / "tools" / "reports" / fn).read_text()))
        before = {fn: (p / fn).read_bytes() for fn in T.FILENAMES}
        r = subprocess.run([sys.executable, str(ROOT / "tools" /
                                                  "cr16_irq_event_trace.py"),
                            "--objdump", str(p / "absent"), "--out", td],
                           capture_output=True, text=True)
        check("missing oracle fails", r.returncode != 0, True)
        check("failed run preserves reports", {fn: (p / fn).read_bytes()
              for fn in T.FILENAMES}, before)
        for n in ("normal", "p2test"):
            data = json.loads((p / T.FILENAMES[1]).read_text())["images"][n]
            check(f"{n}: SC14480 not SC14448 proof",
                  data["related_device_evidence"]["status"],
                  "RELATED_DEVICE_HYPOTHESIS")
            check(f"{n}: runtime writer absence not claimed",
                  data["dataflow_evidence"]["runtime_writer_absence_proven"],
                  False)
            check(f"{n}: event bits not raw",
                  "NOT_RAW_VECTOR_BITS" in data["dataflow_evidence"]
                  ["helper_input_bits_status"], True)

print(f"{fails} failure(s), {skips} skip(s)")
raise SystemExit(bool(fails))
