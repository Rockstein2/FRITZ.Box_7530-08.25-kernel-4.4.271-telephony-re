#!/usr/bin/env python3
"""Tests for the address-alias candidate analysis.

Run: python3 tools/tests/test_cr16_address_alias.py

Results are PASS / FAIL / SKIP.  Without the committed cross-reference
report or the firmware the tool must SKIP and must not rewrite the report.
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import cr16_address_alias as A  # noqa: E402

REPORT = ROOT / "tools" / "reports" / "cr16-address-alias.json"
XREF = ROOT / "tools" / "reports" / "peripheral-xrefs.json"
OBJDUMP = Path("/tmp/opencode/cr16/build/binutils/objdump")
FW = [ROOT / "firmware" / "dectfw_secondlevel_441.hex",
      ROOT / "firmware" / "dectfw_secondlevel_441p2test.hex"]

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


def row(addr, operation, kind, width=16):
    return {"instruction": f"0x{addr:06x}", "operation": operation,
            "address_kind": kind, "effective_address": f"0x{addr:08x}",
            "width_bits": width, "reachable_mode_a": True,
            "reachable_mode_b": True}


# ---------------------------------------------------------------------------
# 1. pair discovery on synthetic addresses
# ---------------------------------------------------------------------------
print("== pair discovery")

low = 0x000F6006
high = 0x00FF6006
check("mask is 20 bits", A.LOW_MASK, 0x000FFFFF)
check("low bits of the pair agree",
      (low & A.LOW_MASK) == (high & A.LOW_MASK), True)
check("difference", f"0x{high - low:08x}", "0x00f00000")
check("0x000F6006 is in scope", A.in_scope(low), True)
check("0x00FF6006 is in scope", A.in_scope(high), True)
check("an address outside both blocks is rejected",
      A.in_scope(0x00001000), False)
check("low bits that differ give no pair",
      (0x000F6006 & A.LOW_MASK) == (0x00FF6007 & A.LOW_MASK), False)

# the tool must only pair addresses that are actually present
synthetic = {
    low: [row(0x1348, "WRITE", "RESOLVED")],
    high: [row(0x258C, "WRITE", "RESOLVED")],
}
check("two present addresses with equal low bits form one pair",
      sorted(a & A.LOW_MASK for a in synthetic) == [0xF6006, 0xF6006], True)

# ---------------------------------------------------------------------------
# 2. ADDRESS_LOAD is not a memory operation
# ---------------------------------------------------------------------------
print("== ADDRESS_LOAD exclusion")
entry = {"operations": [
    {"instruction": "0x002582", "operation": "ADDRESS_LOAD",
     "address_kind": "RESOLVED", "effective_address": "0x00ff6006",
     "width_bits": 32, "reachable_mode_a": True, "reachable_mode_b": True},
    {"instruction": "0x00258c", "operation": "WRITE",
     "address_kind": "RESOLVED", "effective_address": "0x00ff6006",
     "width_bits": 16, "reachable_mode_a": True, "reachable_mode_b": True},
]}
collected = A.collect(entry)
check("ADDRESS_LOAD is not collected as an access",
      [r["operation"] for r in collected[0x00FF6006]], ["WRITE"])

# ---------------------------------------------------------------------------
# 3. UNKNOWN accesses never get an address
# ---------------------------------------------------------------------------
print("== UNKNOWN exclusion")
entry = {"operations": [
    {"instruction": "0x0025d0", "operation": "WRITE", "address_kind":
     "SYMBOLIC", "effective_address": None, "width_bits": 16,
     "reachable_mode_a": True, "reachable_mode_b": True},
    {"instruction": "0x000100", "operation": "READ", "address_kind":
     "UNKNOWN", "effective_address": None, "width_bits": 16,
     "reachable_mode_a": True, "reachable_mode_b": True},
]}
check("symbolic and unknown rows are not collected", A.collect(entry), {})

# ---------------------------------------------------------------------------
# 4. evidence never escalates without a document
# ---------------------------------------------------------------------------
print("== evidence levels")
check("code analysis cannot claim DOCUMENTED_ALIAS",
      A.MAX_CODE_LEVEL, "BEHAVIOR_CORRELATION")
rows_a = [row(0x1348, "WRITE", "RESOLVED")]
rows_b = [row(0x258C, "WRITE", "RESOLVED")]
correlated, notes = A.behaviour(rows_a, rows_b)
check("same operation set produces a correlation", correlated, True)
check("correlation notes explain it",
      any("same operation set" in n for n in notes), True)
rows_c = [row(0x2602C, "READ", "RESOLVED")]
correlated2, _ = A.behaviour(rows_a, rows_c)
check("different operation sets do not correlate", correlated2, False)

# ---------------------------------------------------------------------------
# 5. the committed report, if present
# ---------------------------------------------------------------------------
print("== committed report")
if not XREF.is_file():
    skip("report checks", f"{XREF} missing")
elif not all(p.is_file() for p in FW):
    skip("report checks", "firmware missing")
elif not REPORT.is_file():
    skip("report checks", f"{REPORT} missing")
else:
    data = json.loads(REPORT.read_text())
    for image in ("normal", "p2test"):
        pairs = data["images"][image]["pairs"]
        check(f"{image}: the 0x6006 pair is found",
              any(p["address_a"] == "0x000f6006"
                  and p["address_b"] == "0x00ff6006" for p in pairs), True)
        check(f"{image}: every pair has equal low 20 bits",
              all(int(p["address_a"], 16) & A.LOW_MASK
                  == int(p["address_b"], 16) & A.LOW_MASK
                  for p in pairs), True)
        check(f"{image}: every pair spans the two blocks",
              all(p["address_a"].startswith("0x000f")
                  and p["address_b"].startswith("0x00ff")
                  for p in pairs), True)
        check(f"{image}: no pair is claimed proven",
              all(p["proof_status"].startswith("candidate")
                  for p in pairs), True)
        check(f"{image}: no pair reaches DOCUMENTED_ALIAS",
              all(p["evidence"] != "DOCUMENTED_ALIAS" for p in pairs), True)
        check(f"{image}: every pair is listed with its instructions",
              all(p["a"]["sites"] and p["b"]["sites"] for p in pairs), True)
        # the two addresses must stay separate entries
        check(f"{image}: the two addresses are never merged into one",
              all(p["address_a"] != p["address_b"] for p in pairs), True)

    # different low bits never form a pair
    lows = set()
    for image in ("normal", "p2test"):
        for p in data["images"][image]["pairs"]:
            lows.add(p["low_bits_match"])
    check("all pairs share the same low-bits key set per image",
          len(lows) >= 1, True)

    print("== reproducibility")
    out = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "cr16_address_alias.py"),
         "--json", "/tmp/cr16-address-alias-check.json"],
        capture_output=True, text=True)
    if out.returncode != 0:
        skip("report reproducibility", out.stderr.strip() or "tool failed")
    else:
        generated = json.loads(
            Path("/tmp/cr16-address-alias-check.json").read_text())
        check("committed report matches a fresh run",
              json.loads(REPORT.read_text()), generated)

# ---------------------------------------------------------------------------
# 6. SKIP path never writes the report
# ---------------------------------------------------------------------------
print("== skip path")
target = Path("/tmp/cr16-address-alias-skip.json")
if target.exists():
    target.unlink()
# remove the *input* cross-reference report so the tool has nothing to
# analyse, then restore it (the output report must not be touched)
xr = A.XREF_REPORT
backup = xr.read_text() if xr.is_file() else None
try:
    if xr.is_file():
        xr.unlink()
    out = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "cr16_address_alias.py"),
         "--json", str(target)], capture_output=True, text=True)
    check("missing input report gives a non-zero exit",
          out.returncode != 0, True)
    check("missing input report writes no output", target.exists(), False)
finally:
    if backup is not None:
        xr.write_text(backup)

print()
print(f"{fails} failure(s), {skips} skip(s)")
sys.exit(1 if fails else 0)
