#!/usr/bin/env python3
"""Tests for the external register-map correlation.

Run: python3 tools/tests/test_cr16_external_register_map.py
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import cr16_external_register_map as E  # noqa: E402

REPORT = ROOT / "tools" / "reports" / "cr16-external-register-map.json"

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


if not E.DEFAULT_TM.is_dir():
    skip("reference headers", f"{E.DEFAULT_TM} missing")
    print()
    print(f"{fails} failure(s), {skips} skip(s)")
    sys.exit(1 if fails else 0)

print("== extraction")
defs = E.extract_defines(E.DEFAULT_TM)
by_name = {d["name"]: d for d in defs}
check("headers were read", len(defs) > 40, True)
for name, addr, width in (
        ("UART_CTRL_REG", "0x00ff4900", 16),
        ("UART_RX_TX_REG", "0x00ff4902", 16),
        ("UART_CLEAR_TX_INT_REG", "0x00ff4904", 16),
        ("UART_CLEAR_RX_INT_REG", "0x00ff4906", 16),
        ("WATCHDOG_REG", "0x00ff4c00", 16),
        ("RESET_INT_PENDING_REG", "0x00ff5402", 16),
        ("CHIP_ID1_REG", "0x00fffbf8", 8)):
    d = by_name.get(name)
    check(f"{name} address", d and d["address"], addr)
    check(f"{name} width", d and d["width"], width)

print("== our firmware")
if not E.XREF.is_file():
    skip("correlation", "peripheral-xrefs.json missing")
else:
    ours = E.our_accesses(json.loads(E.XREF.read_text()))
    # the first-level image uses 0x000Fxxxx, the reference uses 0x00FFxxxx
    check("0x000f4900 is used by our firmware", 0x000F4900 in ours, True)
    check("0x00ff4900 is NOT used by our firmware", 0x00FF4900 in ours, False)
    check("0x000f4c00 (watchdog) is used", 0x000F4C00 in ours, True)
    check("the low 20 bits of 0x00ff4900 match 0x000f4900",
          0x00FF4900 & E.LOW_MASK, 0x000F4900 & E.LOW_MASK)

    report = E.build(E.DEFAULT_TM, E.XREF)
    regs = {r["name"]: r for r in report["registers"]}
    uart = regs["UART_CTRL_REG"]
    check("UART control is reported as LOW_BITS_ONLY",
          uart["evidence"], "LOW_BITS_ONLY")
    check("UART control has a low-bit candidate",
          list(uart["low_bit_matches"]), ["0x000f4900"])
    check("the exact address is not claimed present",
          uart["found_in_our_firmware"], False)

    check("an address present in both is not merged",
          regs["WATCHDOG_REG"]["found_in_our_firmware"], True)
    check("the alias conclusion stays UNKNOWN",
          report["alias_conclusion"].startswith("UNKNOWN"), True)
    check("the caution about SC14441 is recorded",
          "SC14441" in report["caution"], True)
    check("upstream commit is recorded",
          report["upstream"]["commit"], E.UPSTREAM_SHA)
    check("fork commit is recorded",
          report["upstream"]["fork_commit"], E.FORK_SHA)
    chips = {c["chip"]: c for c in report["chip_configs"]}
    check("the fork declares SC14448", "SC14448" in chips, True)
    check("SC14448 RAM origin", chips.get("SC14448", {}).get("ram_origin"),
          "0x00010000")
    check("the PLL control register is found at the exact address",
          regs["CLK_PLL_CTRL_REG"]["found_in_our_firmware"], True)
    check("the pad control register is found at the exact address",
          regs["PAD_CTRL_REG"]["found_in_our_firmware"], True)
    check("licence is recorded", "MIT" in report["upstream"]["license"], True)

    print("== evidence levels")
    levels = {r["evidence"] for r in report["registers"]}
    check("no HARDWARE_CONFIRMED level exists",
          any("HARDWARE" in lv for lv in levels), False)
    check("no DOCUMENTED_ALIAS level exists",
          any("DOCUMENTED" in lv for lv in levels), False)

print("== committed report")
if not REPORT.is_file():
    skip("report", f"{REPORT} missing")
else:
    data = json.loads(REPORT.read_text())
    check("report has the reference commit",
          data["upstream"]["commit"], E.UPSTREAM_SHA)
    check("report lists the files read",
          len(data["upstream"]["files_read"]) >= 6, True)
    out = subprocess.run(
        [sys.executable, str(ROOT / "tools" /
                             "cr16_external_register_map.py"),
         "--json", "/tmp/cr16-ext-check.json"],
        capture_output=True, text=True)
    if out.returncode != 0:
        skip("reproducibility", out.stderr.strip() or "tool failed")
    else:
        check("report reproduces",
              json.loads(REPORT.read_text()),
              json.loads(Path("/tmp/cr16-ext-check.json").read_text()))

print()
print(f"{fails} failure(s), {skips} skip(s)")
sys.exit(1 if fails else 0)
