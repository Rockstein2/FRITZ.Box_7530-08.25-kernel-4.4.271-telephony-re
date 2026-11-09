#!/usr/bin/env python3
"""Fail-closed DIP path fixtures and fresh offline report replay."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import cr16_dip_trace as T  # noqa: E402
import cr16_address_spaces as A  # noqa: E402

fails = skips = 0


def check(label, got, want):
    global fails
    if got != want:
        fails += 1
        print(f"FAIL {label}: {got!r} != {want!r}")
    else:
        print(f"PASS {label}")


base = dict(initial=1, limit=512, step=1, backedge=True, exits=1,
            flag_semantics=True)
check("bounded loop model", T.loop_confidence(**base), "PROVEN_UNDER_CFG_MODEL")
for label, changes in (("unknown predecessor", dict(unknown_predecessor=True)),
                       ("changed payload", dict(payload_clobber=True)),
                       ("clobbered address", dict(address_clobber=True)),
                       ("conditional store", dict(conditional_store=True)),
                       ("multiple exits", dict(exits=2)),
                       ("unverified branch condition", dict(flag_semantics=False))):
    check(label, T.loop_confidence(**(base | changes)), "PARTIALLY_PROVEN")
check("unknown initial counter", T.loop_confidence(**(base | {"initial": None})),
      "UNRESOLVED")
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
                                                  "cr16_dip_trace.py"),
                            "--out", td], capture_output=True, text=True)
        check("replay success", r.returncode, 0)
        for fn in T.FILENAMES:
            check(f"fresh {fn}", (p / fn).is_file(), True)
            if (p / fn).is_file():
                check(f"replay {fn}", json.loads((p / fn).read_text()),
                      json.loads((ROOT / "tools" / "reports" / fn).read_text()))
        before = {fn: (p / fn).read_bytes() for fn in T.FILENAMES}
        r = subprocess.run([sys.executable, str(ROOT / "tools" /
                                                  "cr16_dip_trace.py"),
                            "--objdump", str(p / "absent"), "--out", td],
                           capture_output=True, text=True)
        check("missing oracle fails", r.returncode != 0, True)
        check("failed run preserves bundle",
              {fn: (p / fn).read_bytes() for fn in T.FILENAMES}, before)
        check("failure diagnostic", (p / "cr16-e33-dip.incomplete.json").is_file(),
              True)
        for n in ("normal", "p2test"):
            data = json.loads((p / T.FILENAMES[0]).read_text())["images"][n]
            check(f"{n}: not global PROVEN", data["confidence"],
                  "PARTIALLY_PROVEN")

print(f"{fails} failure(s), {skips} skip(s)")
raise SystemExit(bool(fails))
