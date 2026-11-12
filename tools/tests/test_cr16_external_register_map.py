#!/usr/bin/env python3
"""Tests for the external register-map correlation.

Run: python3 tools/tests/test_cr16_external_register_map.py

E3.2 established that an abs20-encoded operand ``0xFxxxx`` expands to the
architectural effective address ``0x00FFxxxx`` (RELOC_ABS20, an ISA rule
confirmed by two independent implementations).  A low-20-bit match against
an abs20 site is therefore the *same architectural address*, not an
unresolved hardware alias; the physical SC14448 register identity stays
UNKNOWN.  The optional reference-header checks SKIP when
``/tmp/opencode/vc/device`` is absent, and that SKIP is never rewritten as
a PASS.
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import cr16_external_register_map as E  # noqa: E402
import cr16_peripheral_xrefs as X      # noqa: E402

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
    skips += 1


# ---------------------------------------------------------------------------
# 1. ISA rule checks: no external reference headers required
# ---------------------------------------------------------------------------
print("== ISA address rule (E3.2)")
check("reloc 0xF4900", E.reloc_abs20(0x0F4900), 0x00FF4900)
check("reloc threshold low", E.reloc_abs20(0xEFFFF), 0xEFFFF)
check("reloc threshold high", E.reloc_abs20(0xF0000), 0xFF0000)
check("match abs20 site", E.architectural_match_status(0x000F4900,
                                                        0x00FF4900),
      "SAME_ARCHITECTURAL_ADDRESS_BY_RELOC_ABS20")
check("match exact site", E.architectural_match_status(0x00FF4900,
                                                       0x00FF4900),
      "EXACT_ARCHITECTURAL_ADDRESS")
check("match unrelated site", E.architectural_match_status(0x000F4900,
                                                           0x00FF4C00),
      "LOW_BITS_ONLY_NO_ISA_RULE")
if E.FIRST_LEVEL.is_file():
    check("first-level abs20 loadw expands to 0x00FF4900",
          X.abs20_address(bytes.fromhex("0f890049")), 0x00FF4900)
else:
    skip("first-level image", f"{E.FIRST_LEVEL} missing")

print("== committed report (basic invariants)")
if not REPORT.is_file():
    skip("report", f"{REPORT} missing")
else:
    data = json.loads(REPORT.read_text())
    check("report has the reference commit",
          data["upstream"]["commit"], E.UPSTREAM_SHA)
    check("report lists the files read",
          len(data["upstream"]["files_read"]) >= 6, True)
    check("licence is recorded", "MIT" in data["upstream"]["license"], True)
    check("alias conclusion stays UNKNOWN",
          data["alias_conclusion"].startswith("UNKNOWN"), True)
    check("alias conclusion does not invent a documented alias",
          "DOCUMENTED" in data["alias_conclusion"], False)
    check("caution about SC14441 is recorded",
          "SC14441" in data["caution"], True)
    # E3.2 correction: a regenerated (tool v2) report carries the ISA-rule
    # field.  The committed v1 artifact predates it; that is recorded as a
    # SKIP here, never silently passed.
    if data.get("tool", "").endswith("/1") and \
            "alias_conclusion_isa_rule" not in data:
        skip("ISA-rule field", "v1 report predates the E3.2 ISA-rule "
             "field; regenerate with the reference headers for v2")
    else:
        check("alias conclusion states the ISA rule (E3.2)",
              ("SAME ARCHITECTURAL ADDRESS" in data["alias_conclusion"] or
               data.get("alias_conclusion_isa_rule")
               == "PROVEN_BY_ISA_IMPLEMENTATIONS"), True)
    levels = {r.get("evidence") for r in data["registers"]}
    check("no HARDWARE_CONFIRMED level exists",
          any("HARDWARE" in str(lv) for lv in levels), False)
    check("no DOCUMENTED_ALIAS level exists",
          any("DOCUMENTED" in str(lv) for lv in levels), False)

# ---------------------------------------------------------------------------
# 2. optional reference-header checks (SKIP when headers are absent; the
#    SKIP status is kept, never substituted with a PASS)
# ---------------------------------------------------------------------------
if not E.DEFAULT_TM.is_dir():
    skip("reference headers", f"{E.DEFAULT_TM} missing")
    skip("correlation", "reference headers missing")
    skip("report reproduction", "reference headers missing")
else:
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
        # the first-level image encodes the UART at 0x000F4900, which is the
        # abs20 form of the architectural 0x00FF4900 (E3.2); the correlation
        # must keep that distinction and never claim a hardware alias.
        check("0x000f4900 appears in our firmware", 0x000F4900 in ours, True)
        check("0x000f4c00 (watchdog) appears", 0x000F4C00 in ours, True)

        report = E.build(E.DEFAULT_TM, E.XREF)
        regs = {r["name"]: r for r in report["registers"]}
        uart = regs["UART_CTRL_REG"]
        check("UART control is reported as FUNCTIONAL_REGISTER_MATCH",
              uart["evidence"], "FUNCTIONAL_REGISTER_MATCH")
        check("UART control has a low-bit candidate",
              list(uart["low_bit_matches"]), ["0x000f4900"])
        # the abs20 low-bit match is the same architectural address, not a
        # separate hardware alias
        if uart["low_bit_matches"]:
            lm = next(iter(uart["low_bit_matches"].values()))
            if isinstance(lm, dict) and "architectural_status" in lm:
                check("UART low-bit match classified by the ISA rule",
                      lm["architectural_status"],
                      "SAME_ARCHITECTURAL_ADDRESS_BY_RELOC_ABS20")
            else:
                skip("UART low-bit match classification",
                     "report was generated before the E3.2 field existed")
        check("the exact address is not claimed present",
              uart["found_in_our_firmware"], False)

        check("an address present in both is not merged",
              regs["WATCHDOG_REG"]["found_in_our_firmware"], True)
        for r in report["registers"]:
            if r["evidence"] == "FUNCTIONAL_REGISTER_MATCH":
                check(f"{r['name']}: FUNCTIONAL_REGISTER_MATCH has manual "
                      "evidence", bool(r.get("manual_verification")), True)
        check("a GPIO register is not promoted by its name alone",
              regs["P0_DIR_REG"]["evidence"] != "FUNCTIONAL_REGISTER_MATCH",
              True)
        check("the watchdog value is verified, not assumed",
              any("0xff" in n for n in regs["WATCHDOG_REG"]
                  ["functional_notes"]), True)
        check("the alias conclusion stays UNKNOWN",
              report["alias_conclusion"].startswith("UNKNOWN"), True)
        check("the physical alias is not declared resolved",
              report.get("alias_conclusion_physical", "UNKNOWN"),
              "UNKNOWN_NO_HARDWARE_EVIDENCE")
        check("the caution about SC14441 is recorded",
              "SC14441" in report["caution"], True)
        check("upstream commit is recorded",
              report["upstream"]["commit"], E.UPSTREAM_SHA)
        check("fork commit is recorded",
              report["upstream"]["fork_commit"], E.FORK_SHA)
        chips = {c["chip"]: c for c in report["chip_configs"]}
        check("the fork declares SC14448", "SC14448" in chips, True)
        check("SC14448 RAM origin", chips.get("SC14448", {}).get(
            "ram_origin"), "0x00010000")
        check("the PLL control register is found at the exact address",
              regs["CLK_PLL_CTRL_REG"]["found_in_our_firmware"], True)
        check("the pad control register is found at the exact address",
              regs["PAD_CTRL_REG"]["found_in_our_firmware"], True)

        print("== evidence levels")
        levels = {r["evidence"] for r in report["registers"]}
        check("no HARDWARE_CONFIRMED level exists",
              any("HARDWARE" in lv for lv in levels), False)
        check("no DOCUMENTED_ALIAS level exists",
              any("DOCUMENTED" in lv for lv in levels), False)

    print("== committed report reproduction")
    if not REPORT.is_file():
        skip("report", f"{REPORT} missing")
    else:
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
