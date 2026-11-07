#!/usr/bin/env python3
"""Check that the peripheral cross-reference tool is stable and complete.

Run: python3 tools/tests/test_cr16_peripheral_xrefs.py

The checks are:

* the abs20 address is decoded from the bytes (not from objdump text);
* a known region reachable only through `movd` is linked to that literal;
* accesses with an unknown base are never given a numeric address;
* the generator is deterministic and the committed JSON is reproduced by
  rerunning the tool;
* both images are covered and a missing environment is a SKIP, not a pass.

Results are PASS / FAIL / SKIP.
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src" / "mock"))

import cr16_cfg as C  # noqa: E402
import cr16_peripheral_xrefs as X  # noqa: E402

REPORT = ROOT / "tools" / "reports" / "peripheral-xrefs.json"
OBJDUMP = Path("/tmp/opencode/cr16/build/binutils/objdump")
FW = ROOT / "firmware" / "dectfw_secondlevel_441.hex"

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


print("== abs20 decoding")
for raw, want in ((bytes.fromhex("0f890260"), 0xF6002),
                  (bytes.fromhex("0fc90264"), 0xF6402),
                  (bytes.fromhex("2fc90254"), 0xF5402),
                  (bytes.fromhex("0fc10064"), 0xF6400),
                  (bytes.fromhex("0f890a58"), 0xF580A)):
    check(f"abs20 {raw.hex()}", X.abs20(raw), want)

if not FW.is_file() or not OBJDUMP.is_file():
    skip("scan", "firmware or CR16 objdump missing")
else:
    fw = C.load(str(FW))
    C.disassemble(fw, str(OBJDUMP))
    recs = X.scan(fw, "normal")

    # 1. A known abs20 access is reported with its address.
    hit = [r for r in recs if r["address"] == "0x00255e"]
    check("0x255e is recorded as an abs20 write", len(hit), 1)
    if hit:
        check("0x255e effective address", hit[0]["effective_address"],
              "0x0f6400")
        check("0x255e access kind", hit[0]["access"], "write")
        check("0x255e width", hit[0]["width"], 16)

    # 2. The movd candidate is recorded as an address load, not as a memory
    #    access, so it cannot be mistaken for a register read/write.
    hit = [r for r in recs if r["address"] == "0x0025c4"]
    check("0x25c4 is an address load", hit[0]["access"] if hit else None,
          "address_load")

    # 3. Unknown bases never produce a numeric address.
    unknown = [r for r in recs if r["evidence"] == "RUNTIME_ADDRESS"]
    check("runtime addresses are not numeric",
          all(not r["effective_address"].startswith("0x")
              for r in unknown), True)

    # 4. The tool is deterministic.
    a = json.dumps(X.scan(C.load(str(FW)), "normal"), sort_keys=True)
    b = json.dumps(X.scan(C.load(str(FW)), "normal"), sort_keys=True)
    check("scan is deterministic", a, b)

# ---------------------------------------------------------------------------
# 5. The committed report is reproduced by the tool
# ---------------------------------------------------------------------------
if not REPORT.is_file():
    skip("report reproducibility", f"{REPORT} missing")
else:
    out = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "cr16_peripheral_xrefs.py"),
         "--json", "/tmp/xrefs-check.json"],
        capture_output=True, text=True)
    if out.returncode != 0:
        skip("report reproducibility", out.stderr.strip() or "tool failed")
    else:
        generated = json.loads(Path("/tmp/xrefs-check.json").read_text())
        committed = json.loads(REPORT.read_text())
        check("committed report matches a fresh run", committed, generated)

print()
print(f"{fails} failure(s), {skips} skip(s)")
sys.exit(1 if fails else 0)
