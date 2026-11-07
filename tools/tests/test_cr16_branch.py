#!/usr/bin/env python3
"""Branch decoder tests and the reproducible validation report.

Run:
    python3 tools/tests/test_cr16_branch.py
    python3 tools/tests/test_cr16_branch.py --json tools/reports/cr16-branch-validation.json [--check]

The JSON writer here is the **only** producer of
`tools/reports/cr16-branch-validation.json`; the test assertions and the file
are generated in the same pass from the same tables, so the committed report
is exactly what this command prints.

Determinism rules:

* no timestamps, no absolute paths and no host names in the output;
* every list is sorted by a stable key (image, address);
* every dictionary is written with `sort_keys=True` and a fixed separator;
* the output ends with a single newline.

Consequently, after
    python3 tools/tests/test_cr16_branch.py --json tools/reports/....json
    git diff --exit-code -- tools/reports/....json
must be empty whenever the firmware and the toolchain are unchanged.

Exit status: 0 when every assertion passes and the report was written (or
`--check` found no difference), 1 on any failure, and 2 when the environment
is incomplete (missing firmware or missing CR16 objdump) — in that case no
report is written, so an absent environment can never produce a "successful"
report.

Statuses assigned per instruction: MATCH, MISMATCH, UNSUPPORTED, INVALID,
ORACLE_UNAVAILABLE.  Only MATCH is a pass.  UNSUPPORTED means "the encoding is
not implemented"; INVALID means "this instruction is not a branch" (register
indirect transfers and non-branch instructions); ORACLE_UNAVAILABLE means no
independent target could be produced.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(ROOT / "src" / "mock"))

import cr16_cfg as C  # noqa: E402
import cr16_branch as B  # noqa: E402

TOOL_VERSION = "cr16-branch-validation/2"
DEFAULT_REPORT = ROOT / "tools" / "reports" / "cr16-branch-validation.json"

IMAGES = [
    ("normal", ROOT / "firmware" / "dectfw_secondlevel_441.hex"),
    ("p2test", ROOT / "firmware" / "dectfw_secondlevel_441p2test.hex"),
]

OBJDUMP_CANDIDATES = [
    Path("/tmp/opencode/cr16/build/binutils/objdump"),
    Path("/tmp/opencode/cr16/build2/binutils/objdump"),
]

STATUSES = ("MATCH", "MISMATCH", "UNSUPPORTED", "INVALID",
            "ORACLE_UNAVAILABLE")

fails = 0
skips = 0


# ---------------------------------------------------------------------------
# small assertion helpers: every result is PASS / FAIL / SKIP
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# oracle
# ---------------------------------------------------------------------------
def find_objdump():
    for p in OBJDUMP_CANDIDATES:
        if p.is_file():
            return p
    return None


def usable_objdump(path):
    """A supplied path must exist and run, otherwise the run is a SKIP."""
    if path is None:
        return None
    try:
        subprocess.run([str(path), "--version"], capture_output=True,
                       text=True, check=False)
    except OSError:
        return None
    return path


def objdump_version(od):
    if od is None:
        return "unknown"
    try:
        out = subprocess.run([str(od), "--version"], capture_output=True,
                             text=True, check=False).stdout
    except OSError:
        return "unknown"
    first = out.splitlines()[0] if out else ""
    m = re.search(r"(\d+\.\d+(?:\.\d+)?)", first)
    return m.group(1) if m else first.strip()


def oracle_target(od, addr, raw, relative_printed=False):
    """Absolute target printed by objdump at the instruction's own address.

    `objdump` prints `memaddr + displacement` for branch instructions; the
    `*+`/`*-` prefix only reflects the sign of the displacement.  For the
    branch-if-zero family (`disps5`) binutils prints `2*offset + 2`, i.e. the
    displacement itself, so `relative_printed` adds the address back.
    """
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        f.write(bytes(raw) + b"\0\0\0\0")
        tmp = Path(f.name)
    try:
        out = subprocess.run(
            [str(od), "-D", "-b", "binary", "-m", "cr16",
             f"--adjust-vma={addr}", str(tmp)],
            capture_output=True, text=True, check=False).stdout
    finally:
        tmp.unlink(missing_ok=True)
    for line in out.splitlines():
        if line.strip().startswith(f"{addr:x}:"):
            ops = line.split("\t")[-1].strip()
            m = re.search(r"\*[+-](0x[0-9a-f]+)", ops)
            if not m:
                return None
            value = int(m.group(1), 16)
            return (addr + value) & 0xFFFFFF if relative_printed else value
    return None


# ---------------------------------------------------------------------------
# tables
# ---------------------------------------------------------------------------
def classify(od, fw, image, sha):
    """Return the per-instruction table for one image."""
    rows = []
    for addr, insn in sorted(fw.insns.items()):
        if insn.mnemonic not in (C.COND | C.CALLS | C.JUMPS):
            continue
        target, form, status = B.decode_insn(addr, insn.mnemonic,
                                             insn.raw[:min(6, insn.size)])
        oracle = oracle_target(od, addr, insn.raw,
                               relative_printed=(form == "disps5"))
        if status == "DIRECT":
            if oracle is None:
                verdict = "ORACLE_UNAVAILABLE"
            elif target == oracle:
                verdict = "MATCH"
            else:
                verdict = "MISMATCH"
        elif status == "UNSUPPORTED":
            verdict = "UNSUPPORTED"
        elif status == "NOT_A_BRANCH":
            # A register-indirect transfer or a plain instruction: objdump
            # must not have produced a target for it, otherwise the decoder
            # and the oracle disagree about what the bytes are.
            verdict = ("MISMATCH" if oracle is not None and oracle != addr
                       else "INVALID")
        else:
            verdict = "INVALID"
        rows.append({
            "address": f"{addr:#08x}",
            "bytes": insn.raw.hex(),
            "form": form,
            "mnemonic": insn.mnemonic,
            "target": None if target is None else f"{target:#08x}",
            "oracle": None if oracle is None else f"{oracle:#08x}",
            "status": verdict,
            "image": image,
            "firmware_sha256": sha,
        })
    return rows


def summarise(rows):
    by_form = {}
    by_status = {s: 0 for s in STATUSES}
    for r in rows:
        by_form.setdefault(r["form"], {s: 0 for s in STATUSES})
        by_form[r["form"]][r["status"]] += 1
        by_status[r["status"]] += 1
    return {"by_form": by_form, "by_status": by_status,
            "control_transfers": len(rows)}


def build_report(od, tables, image_meta):
    """Assemble the exact JSON structure that is committed."""
    summary = {}
    unsupported = []
    mismatches = []
    for image, rows in tables.items():
        summary[image] = summarise(rows)
        for r in rows:
            if r["status"] == "UNSUPPORTED":
                unsupported.append(r)
            elif r["status"] == "MISMATCH":
                mismatches.append(r)
    unsupported.sort(key=lambda r: (r["image"], r["address"]))
    mismatches.sort(key=lambda r: (r["image"], r["address"]))
    return {
        "tool": TOOL_VERSION,
        "decoder": "tools/cr16_branch.py",
        "binutils_version": objdump_version(od),
        "binutils_objdump": od.name,
        "images": image_meta,
        "summary": summary,
        "unsupported": unsupported,
        "mismatches": mismatches,
        "note": (
            "Generated by `python3 tools/tests/test_cr16_branch.py --json "
            "tools/reports/cr16-branch-validation.json`.  Only cases that are "
            "not MATCH are listed; every MATCH can be reproduced by rerunning "
            "the command against the vendor images, which are not stored in "
            "Git.  Statuses: MATCH, MISMATCH, UNSUPPORTED, INVALID (not a "
            "branch: register-indirect transfer or plain instruction), "
            "ORACLE_UNAVAILABLE."
        ),
    }


def dump(report):
    return json.dumps(report, indent=1, sort_keys=True,
                      ensure_ascii=True) + "\n"


# ---------------------------------------------------------------------------
# fixed assertions on the decoder (independent of the images)
# ---------------------------------------------------------------------------
def run_unit_checks():
    print("== dispe9 field arithmetic (from cr16-dis.c)")
    for hx, addr, want_disp, want_target in (
            ("491f", 0x25FA8, -0x0E, 0x25F9A),
            ("1d1f", 0x25FB4, -0x06, 0x25FAE),
            ("4d19", 0x25E64, -0xC6, 0x25D9E),
            ("3a1f", 0x28C00, -0x0C, 0x28BF4),
            ("1212", 0x000EE, +0x44, 0x00132),
            ("4011", 0x00294, +0x20, 0x002B4)):
        raw = bytes.fromhex(hx)
        w0 = raw[0] | (raw[1] << 8)
        disp, sign = B.cond2_disp(w0)
        check(f"disp {hx} @{addr:#07x}", disp, want_disp)
        check(f"sign {hx}", sign, want_disp < 0)
        check(f"target {hx} @{addr:#07x}", B.cond2_target(addr, w0),
              want_target)

    print("== boundary and wrap-around")
    check("forward to the same address (0 displacement)",
          B.cond2_target(0xFFFF00, 0x0010), 0xFFFF00)
    check("backward wraps through 0x000000",
          B.cond2_target(0x000010, 0x1F01), (0x000010 - 0x1E) & 0xFFFFFF)
    # The field is an 8-bit even signed value; sweep it exhaustively rather
    # than asserting two magic words.
    disp = [B.cond2_disp(w)[0] for w in range(0x1000, 0x2000)]
    check("largest backward displacement", min(disp), -0xFE)
    check("largest forward displacement", max(disp), 0xFE)
    check("all displacements are even", all(d % 2 == 0 for d in disp), True)
    check("0x1F01 is -0x1E", B.cond2_disp(0x1F01)[0], -0x1E)

    print("== other branch forms")
    for addr, mn, hx, want in (
            (0x016A, "beq0b", "000c", 0x016C),
            (0x0174, "bne0b", "000d", 0x0196),
            (0x017E, "beq0w", "000e", 0x0180),
            (0x0100, "beq0b", "100c", 0x0104),
            (0x0100, "beq0b", "f00c", 0x0120),
            (0x0100, "bne0w", "ff0f", 0x0140)):
        raw = bytes.fromhex(hx)
        t, form, status = B.decode_insn(addr, mn, raw)
        check(f"disps5 {hx} @{addr:#07x}", (t, status), (want, "DIRECT"))
        check(f"disps5 {hx} form", form, "disps5")
    for addr, hx, want in ((0x0000, "40 18 00 03", 0x0300),
                           (0x0200, "00 18 00 01", 0x0300)):
        raw = bytes.fromhex(hx.replace(" ", ""))
        t, form, status = B.decode(addr, raw)
        check(f"cond32 {hx} @{addr:#07x}", (t, status), (want, "DIRECT"))
    for hx, addr, want in (("00 c0 1c 17", 0x2570, 0x3C8C),
                           ("ff c0 7b ff", 0x257E, 0x24F8),
                           ("02 c0 c8 66", 0x25E2, 0x28CAA),
                           ("ff c0 a7 f9", 0x0AF0, 0x0496)):
        raw = bytes.fromhex(hx.replace(" ", ""))
        t, form, status = B.decode(addr, raw)
        check(f"bal {hx} @{addr:#06x}", (t, status), (want, "DIRECT"))

    print("== non-branch instructions and unsupported forms")
    check("register-indirect jump",
          B.decode_insn(0x494, "jump", bytes.fromhex("ee0a"))[2],
          "NOT_A_BRANCH")
    check("register-indirect jal",
          B.decode_insn(0x14, "jal", bytes.fromhex("d600"))[2],
          "NOT_A_BRANCH")
    check("plain load has no target",
          B.decode_insn(0x25FAE, "loadw", bytes.fromhex("0f890260"))[2],
          "NOT_A_BRANCH")
    check("6-byte conditional stays unsupported",
          B.decode_insn(0x92FC, "bhi", bytes.fromhex("10004d00074e"))[2],
          "UNSUPPORTED")


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", metavar="PATH", type=Path,
                    help="write the validation report to PATH")
    ap.add_argument("--check", action="store_true",
                    help="compare the generated report with PATH instead of "
                         "writing it; exit 1 on any difference")
    ap.add_argument("--objdump", metavar="PATH", type=Path,
                    help="CR16 objdump to use as the oracle")
    ap.add_argument("--normal", metavar="PATH", type=Path,
                    help="normal firmware image (Intel HEX)")
    ap.add_argument("--p2test", metavar="PATH", type=Path,
                    help="p2test firmware image (Intel HEX)")
    args = ap.parse_args()

    global IMAGES
    if args.normal or args.p2test:
        IMAGES = [("normal", args.normal or IMAGES[0][1]),
                  ("p2test", args.p2test or IMAGES[1][1])]

    run_unit_checks()

    od = usable_objdump(args.objdump) if args.objdump else find_objdump()
    missing = [str(p) for _, p in IMAGES if not p.is_file()]
    if od is None or missing:
        why = ("CR16 objdump not found" if od is None
               else f"firmware missing: {', '.join(missing)}")
        print(f"SKIP full validation: {why}")
        print()
        print("environment incomplete: no report written, "
              f"{fails} failure(s), {skips + 1} skip(s)")
        return 2

    tables = {}
    image_meta = {}
    for image, path in IMAGES:
        fw = C.load(str(path))
        C.disassemble(fw, str(od))
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        rows = classify(od, fw, image, sha)
        tables[image] = rows
        image_meta[image] = {
            "file": path.name,
            "sha256": sha,
            "decoded_instructions": len(fw.insns),
        }
        s = summarise(rows)
        print(f"-- {image}: {s['control_transfers']} control transfers, "
              f"sha256 {sha[:16]}...")
        for form in sorted(s["by_form"]):
            for verdict in STATUSES:
                n = s["by_form"][form][verdict]
                if n:
                    print(f"   {form:20s} {verdict:20s} {n:5d}")
        check(f"{image}: category counts add up",
              sum(s["by_status"].values()), s["control_transfers"])
        check(f"{image}: zero MISMATCH", s["by_status"]["MISMATCH"], 0)
        check(f"{image}: zero ORACLE_UNAVAILABLE",
              s["by_status"]["ORACLE_UNAVAILABLE"], 0)
        check(f"{image}: at least one MATCH", s["by_status"]["MATCH"] > 0,
              True)

    report = build_report(od, tables, image_meta)
    text = dump(report)
    if args.json:
        if args.check:
            try:
                current = args.json.read_text()
            except FileNotFoundError:
                current = ""
            check(f"{args.json}: report is reproducible", current, text)
        else:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(text)
            print(f"wrote {args.json} "
                  f"({len(report['unsupported'])} unsupported, "
                  f"{len(report['mismatches'])} mismatch)")

    print()
    print(f"{fails} failure(s), {skips} skip(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
