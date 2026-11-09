#!/usr/bin/env python3
"""Tests for CR16 address forms and the Q57 address-space resolution.

Run: python3 tools/tests/test_cr16_address_spaces.py

The unit checks do not need the firmware.  Report checks require the two
firmware images and the CR16 binutils oracle; they SKIP otherwise.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src" / "mock"))

import cr16_cfg as C  # noqa: E402
import cr16_address_spaces as A  # noqa: E402
import cr16_peripheral_xrefs as X  # noqa: E402

REPORTS = ROOT / "tools" / "reports"
OBJDUMP = A.OBJDUMP
FW = {
    "normal": ROOT / "firmware" / "dectfw_secondlevel_441.hex",
    "p2test": ROOT / "firmware" / "dectfw_secondlevel_441p2test.hex",
}

fails = 0
skips = 0


def check(name, got, want):
    global fails
    if got == want:
        print(f"PASS {name}")
    else:
        print(f"FAIL {name}: got {repr(got)[:300]} want {repr(want)[:300]}")
        fails += 1


def skip(name, why):
    global skips
    print(f"SKIP {name}: {why}")
    skips += 1


def insn(addr, raw, mnemonic, operands):
    return C.Insn(addr, len(raw), mnemonic, operands, raw)


# ---------------------------------------------------------------------------
# 1. abs20 encoding and expansion
# ---------------------------------------------------------------------------
print("== abs20 encoding")
raw = bytes.fromhex("0f890260")
check("encoded 20-bit field", X.abs20_encoded_address(raw), 0xF6002)
check("architectural address", X.abs20_address(raw), 0xFF6002)
check("threshold low side", X.reloc_abs20(0xEFFFF), 0xEFFFF)
check("threshold high side", X.reloc_abs20(0xF0000), 0xFF0000)
check("0xF6006 expands to 0xFF6006", X.reloc_abs20(0xF6006), 0xFF6006)
check("0xF5402 expands to 0xFF5402", X.reloc_abs20(0xF5402), 0xFF5402)
check("0xEFFFF does not expand", X.reloc_abs20(0xEFFFF), 0xEFFFF)
check("0x00000 stays zero", X.reloc_abs20(0), 0)

abs20 = insn(0x1348, raw, "loadw", "0xf6002:m,r0")
form, operand, payload, base, disp = A._memory_form(abs20)
check("abs20 form", form, "ABS20")
check("abs20 operand", operand, "0xf6002:m")
check("abs20 base is absent", base, None)
arch = A._arch_form(abs20, {"effective_address": "0x00ff6002"})
check("abs20 architectural address", arch["architectural_effective_address"],
      "0x00ff6002")
check("abs20 encoded address", arch["encoded_address"], "0xf6002")
check("abs20 extension", arch["extension_models"]["architectural_effective"],
      "0x00ff6002")

pair = insn(0x258C, bytes.fromhex("20d0"), "storw", "r2,0x0:s(r1,r0)")
form, operand, payload, base, disp = A._memory_form(pair)
check("pair form", form, "REGISTER_PAIR")
check("pair registers", base, ("r1", "r0"))
check("pair displacement", disp, 0)
arch = A._arch_form(pair, {"effective_address": "0x00ff6006"})
check("pair keeps its dataflow address",
      arch["architectural_effective_address"], "0x00ff6006")
check("pair has no extension model", arch["extension_models"], None)

print("== address direction")
for mnemonic, operands, raw, mode, operation in (
        ("loadw", "0xf6006:m,r0", "0f890660", "ABS20", "READ"),
        ("storw", "r0,0xf6006:m", "0fc90660", "ABS20", "WRITE"),
        # Oracle-verified six-byte forms: the proposed four-byte loadd/stord
        # fixtures were not present in either image and must not be invented.
        ("loadd", "0x11dde:l,(r3,r2)", "120020b1de1d", "ABS24", "READ"),
        ("stord", "(r5,r4),0x936c:l", "130040b06c93", "ABS24", "WRITE"),
        ("loadw", "0x0:s(r1,r0),r2", "2090", "REGISTER_PAIR", "READ"),
        ("storw", "r2,0x0:s(r1,r0)", "20d0", "REGISTER_PAIR", "WRITE")):
    i = insn(0x1348, bytes.fromhex(raw), mnemonic, operands)
    check(f"{mnemonic} {operands} mode", A._memory_form(i)[0], mode)
    check(f"{mnemonic} {operands} operation", X.ACCESS[mnemonic][0], operation)
    if mode in ("ABS20", "ABS24"):
        a = A._arch_form(i, {})
        encoded, effective = (("0xf6006", "0x00ff6006") if mode == "ABS20"
                              else (("0x00011dde", "0x00011dde") if
                                    mnemonic == "loadd" else
                                    ("0x0000936c", "0x0000936c")))
        check(f"{mnemonic} encoded", a["encoded_address"], encoded)
        check(f"{mnemonic} effective", a["architectural_effective_address"],
              effective)
check("movd pair to pair is not memory",
      X.address_operand(insn(0, b"\0\0", "movd", "(r3,r2),(r1,r0)")),
      (None, None))
for m in ("loadm", "loadmp", "storm", "stormp"):
    check(f"{m} unsupported", X.address_operand(insn(0, b"\0\0", m,
          "(r3,r2),(r1,r0)")), (None, None))

print("== fail-closed publication")
with tempfile.TemporaryDirectory() as td:
    dest = Path(td)
    original = {fn: f"old {fn}\n" for fn in A.REPORT_NAMES}
    for fn, text in original.items():
        (dest / fn).write_text(text)
    for reason in ("missing normal", "missing p2test", "wrong SHA256",
                   "missing objdump", "NON_CONVERGED", "invalid structure"):
        with tempfile.TemporaryDirectory() as inputs:
            paths = {n: Path(inputs) / f"{n}.hex" for n in FW}
            for p in paths.values():
                p.write_bytes(b"synthetic image")
            if reason == "missing normal":
                paths["normal"].unlink()
            if reason == "missing p2test":
                paths["p2test"].unlink()
            expected = {n: A._sha(p) for n, p in paths.items() if p.exists()}
            if reason == "wrong SHA256":
                expected["normal"] = "0" * 64
            with patch.object(A, "IMAGES", list(paths.items())), \
                    patch.object(A, "REFERENCE_SHA", expected), \
                    patch.object(A, "_build_reports", side_effect=ValueError(reason)):
                oracle = str(OBJDUMP) if reason != "missing objdump" else str(
                    Path(inputs) / "absent-objdump")
                rc = A.main(["cr16_address_spaces", "--out", td,
                             "--objdump", oracle])
        check(f"{reason} fails", rc != 0, True)
        check(f"{reason} preserves reports",
              {fn: (dest / fn).read_text() for fn in A.REPORT_NAMES}, original)
        check(f"{reason} diagnostic", bool(json.loads((dest /
              "cr16-address-spaces.incomplete.json").read_text())["reason"]), True)
    new = {fn: {"filename": fn} for fn in A.REPORT_NAMES}
    replace = os.replace
    calls = [0]

    def fail_second(source, target):
        calls[0] += 1
        if calls[0] == 2:
            raise OSError("synthetic promotion error")
        return replace(source, target)

    try:
        with patch.object(A.os, "replace", side_effect=fail_second):
            A._publish(dest, new)
        check("failed promotion raises", False, True)
    except OSError:
        check("failed promotion preserves complete previous bundle",
              {fn: (dest / fn).read_text() for fn in A.REPORT_NAMES}, original)
    A._publish(dest, new)
    check("complete staged bundle", {fn: json.loads((dest / fn).read_text())
          for fn in A.REPORT_NAMES}, new)

# ---------------------------------------------------------------------------
# 2. reports and instruction-level provenance
# ---------------------------------------------------------------------------
print("== reports")
missing = [p for p in [OBJDUMP, *FW.values()] if not p.exists()]
if missing:
    skip("report checks", f"missing {missing[0]}")
else:
    forms = {}
    for name in ("normal", "p2test"):
        p = REPORTS / f"cr16-address-forms-{name}.json"
        if not p.exists():
            skip(f"{name} report", f"{p.name} missing")
            continue
        d = json.loads(p.read_text())
        forms[name] = d
        check(f"{name}: source is committed firmware",
              d["source"], f"firmware/{FW[name].name}")
        check(f"{name}: all resolved records have provenance",
              all(r.get("source_provenance") for r in d["records"]
                  if r.get("address_kind") != "UNKNOWN"), True)
        # Every abs20 record's raw bytes must reproduce its encoded field.
        abs20_rows = [r for r in d["records"]
                      if r["address_mode"] == "ABS20"]
        check(f"{name}: abs20 records present", len(abs20_rows) > 0, True)
        ok = True
        for r in abs20_rows:
            raw = bytes.fromhex(r["raw_bytes"])
            enc = X.abs20_encoded_address(raw)
            if r.get("encoded_address") != f"0x{enc:05x}":
                ok = False
                break
            if r.get("architectural_effective_address") != \
                    f"0x{X.reloc_abs20(enc):08x}":
                ok = False
                break
        check(f"{name}: every abs20 raw field reproduces the report", ok, True)
        # No effective low-space 0x000F address remains after expansion.
        check(f"{name}: no effective 0x000Fxxxx address",
              any((r.get("architectural_effective_address") or "").
                  lower().startswith("0x000f") for r in d["records"]), False)
        # Selected raw sites.
        by_inst = {r["instruction"]: r for r in d["records"]}
        site = "0x001348" if name == "normal" else "0x000dbe"
        r = by_inst[site]
        check(f"{name}: 0x6006 abs20 site", r["raw_bytes"], "2fc90660")
        check(f"{name}: 0x6006 encoded field", r["encoded_address"], "0xf6006")
        check(f"{name}: 0x6006 canonical address",
              r["architectural_effective_address"], "0x00ff6006")
        site = "0x001934" if name == "normal" else "0x0013b6"
        r = by_inst[site]
        check(f"{name}: 0x5402 canonical address",
              r["architectural_effective_address"], "0x00ff5402")
        site = "0x00258c" if name == "normal" else "0x001e48"
        r = by_inst[site]
        check(f"{name}: pair 0x6006 canonical address",
              r["architectural_effective_address"], "0x00ff6006")
        check(f"{name}: pair site has no encoded absolute field",
              r["encoded_address"], None)
        for site, address, operation in ((
                ("0x025fae", "0x00ff6002", "READ"),
                ("0x028cde", "0x00ff6006", "READ")) if name == "normal"
                else (("0x026764", "0x00ff6002", "READ"),)):
            r = by_inst[site]
            check(f"{name}: {site} address", r["effective_address"], address)
            check(f"{name}: {site} operation", r["operation"], operation)

    if len(forms) == 2:
        modes = {n: forms[n]["summary"]["by_address_mode"] for n in forms}
        check("normal/p2test have the same address-form vocabulary",
              set(modes["normal"]) == set(modes["p2test"]), True)
        check("normal/p2test both contain ABS20 and REGISTER_PAIR",
              all("ABS20" in modes[n] and "REGISTER_PAIR" in modes[n]
                  for n in modes), True)

    cp = REPORTS / "cr16-address-space-conflicts.json"
    if cp.exists():
        c = json.loads(cp.read_text())
        for name in ("normal", "p2test"):
            if name not in c.get("images", {}):
                continue
            rows = {p["low_encoded_form"]: p
                    for p in c["images"][name]}
            p = rows["0x000f6006"]
            check(f"{name}: 0x6006 extension matches high",
                  p["sign_extension_matches_high"], True)
            check(f"{name}: 0x6006 status",
                  p["status"], "SAME_ARCHITECTURAL_ADDRESS")
            check(f"{name}: 0x6006 alias proof",
                  p["alias_proof"], "PROVEN_BY_ISA_EXTENSION")
            check(f"{name}: physical identity remains candidate",
                  p["physical_register_identity"], "CANDIDATE")
            p = rows["0x000f5402"]
            check(f"{name}: 0x5402 extension matches high",
                  p["sign_extension_matches_high"], True)
            check(f"{name}: 0x5402 is single-form",
                  p["status"], "SAME_ARCHITECTURAL_ADDRESS_SINGLE_FORM")
        check("no conflict report claims a physical alias",
              all(p["physical_register_identity"] == "CANDIDATE"
                  for image in c["images"].values() for p in image), True)
        check("hypotheses include reloc_abs20 proof",
              any(h["name"] == "SIGN_EXTENSION_RELOC_ABS20"
                  and h["status"] == "PROVEN_BY_ISA"
                  for h in c["hypotheses"]), True)

    dp = REPORTS / "cr16-dip-ram-fill.json"
    if dp.exists():
        d = json.loads(dp.read_text())
        for name in ("normal", "p2test"):
            if name not in d.get("images", {}):
                continue
            x = d["images"][name]
            check(f"{name}: DIP payload", x["payload"], "0x1001")
            check(f"{name}: DIP classification",
                  x["classification"], "DIP_RAM_FILL_CANDIDATE")
            check(f"{name}: DIP not PCM", x["pcm_evidence"], False)
            check(f"{name}: DIP little-endian candidate is BR",
                  x["payload_byte_orders"]["little_endian"]["opcode_name"],
                  "BR")
            check(f"{name}: DIP big-endian candidate is BR_B0",
                  x["payload_byte_orders"]["big_endian"]["opcode_name"],
                  "BR_B0")

    ap = REPORTS / "cr16-e32-audit.json"
    if ap.exists():
        a = json.loads(ap.read_text())
        check("audit records local table def-use",
              a["e31_fixes"]["table_def_use_scope"],
              "LOCAL_BASIC_BLOCK_ONLY")
        check("audit records fail-closed baseline",
              "fail-closed" in a["e31_fixes"]["old_baseline"], True)
        check("audit records mismatched uses",
              all("mismatched_uses" in v for v in a["images"].values()), True)

    # Replay a small deterministic subset.  The full tool is exercised by the
    # report generation and the verification script.
    print("== replay")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        result = subprocess.run([sys.executable, str(ROOT / "tools" /
                                             "cr16_address_spaces.py"),
                                 "--objdump", str(OBJDUMP), "--out", str(out)],
                                check=False, capture_output=True, text=True)
        check("replay exits zero", result.returncode, 0)
        for fn in A.REPORT_NAMES:
            check(f"replay created {fn}", (out / fn).is_file(), True)
            if (out / fn).is_file():
                check(f"replay matches {fn}",
                      json.loads((REPORTS / fn).read_text()),
                      json.loads((out / fn).read_text()))

print(f"\n{fails} failure(s), {skips} skip(s)")
raise SystemExit(1 if fails else 0)
