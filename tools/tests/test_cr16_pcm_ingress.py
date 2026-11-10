#!/usr/bin/env python3
"""Bounded E3.5 replay and source-to-sink fail-closed fixtures."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import cr16_address_spaces as A  # noqa: E402
import cr16_pcm_ingress as P  # noqa: E402

fails = skips = 0


def check(label, actual, want):
    global fails
    if actual != want:
        print(f"FAIL {label}: {str(actual)[:160]} != {str(want)[:160]}")
        fails += 1
    else:
        print(f"PASS {label}")


check("normal marker", P.ctrl_word(0, 0), 0x4000)
check("normal source bits", P.ctrl_word(0x0ff0, (1 << 17) | (1 << 18)),
      0x4000 | ((0xff0 >> 3) & 0x1e0) | ((0xff0 >> 4) & 0xf) | 0x210)
check("special marker with payload", P.ctrl_word(0, 0, 0x1234), 0x9234)
check("special may overlap normal bit14", P.ctrl_word(0, 0, 0x4001), 0xc001)
check("rx mapped bit3 to reg44 bit7", P.rx_reg44(8) & 0x80, 0x80)
check("rx marker suppresses update", P.rx_reg44(0x8000), None)
check("matching mask not sufficient", P.classify_consumer(False, True, True),
      "PCM_CONTROL_CANDIDATE")
check("unlinked effect unresolved", P.classify_consumer(False, False, True),
      "UNRESOLVED")
check("logical link without physical still candidate",
      P.classify_consumer(True, True, True), "PCM_CONTROL_CANDIDATE")
check("fully evidenced synthetic path", P.classify_consumer(
    True, True, True, physical_mapping_proven=True), "FON_SLOT5_CONSUMER_PROVEN")
check("related register name remains hypothesis",
      P.REFERENCE_HINTS[0x01027FAE].startswith("SC14480"), True)

if not A.OBJDUMP.is_file() or any(not p.is_file() for _, p in A.IMAGES):
    skips += 1
    print("SKIP firmware replay: missing offline inputs")
else:
    with tempfile.TemporaryDirectory() as td:
        command = [sys.executable, str(ROOT / "tools" / "cr16_pcm_ingress.py"),
                   "--out", td]
        p = subprocess.run(command, capture_output=True, text=True)
        check("fresh replay succeeds", p.returncode, 0)
        for fn in P.FILES:
            check("fresh report " + fn, (Path(td) / fn).is_file(), True)
            if (Path(td) / fn).is_file():
                check("deterministic report " + fn,
                      json.loads((Path(td) / fn).read_text()),
                      json.loads((ROOT / "tools" / "reports" / fn).read_text()))
        original = {fn: (Path(td) / fn).read_bytes() for fn in P.FILES}
        bad = subprocess.run(command + ["--objdump", str(Path(td) / "missing")],
                             capture_output=True, text=True)
        check("missing oracle rejected", bad.returncode != 0, True)
        with patch.object(P.D, "run_image", return_value=(
                {"converged": False}, None, [])):
            check("NON_CONVERGED rejected", P.main(["--out", td]) != 0, True)
        with patch.object(A, "REFERENCE_SHA", {k: "0" * 64 for k in
                                                ("normal", "p2test")}):
            check("wrong SHA rejected", P.main(["--out", td]) != 0, True)
        check("bad inputs preserve complete report set",
              {fn: (Path(td) / fn).read_bytes() for fn in P.FILES}, original)
        for n in ("normal", "p2test"):
            boundaries = json.loads((Path(td) / P.FILES[6]).read_text())["images"][n]
            check(f"{n}: physical mapping stays UNKNOWN",
                  boundaries["cfg_evidence"]["physical_transport"], "UNKNOWN")
            check(f"{n}: no false FON status",
                  boundaries["cfg_evidence"]["FON_SLOT5_CONSUMER_PROVEN"], False)

print(f"{fails} failure(s), {skips} skip(s)")
raise SystemExit(bool(fails))
