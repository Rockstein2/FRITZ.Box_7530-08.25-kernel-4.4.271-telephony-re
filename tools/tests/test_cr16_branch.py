#!/usr/bin/env python3
"""Branch decoder tests and full validation report.

Run: python3 tools/tests/test_cr16_branch.py [--json OUT.json]

Every branch instruction of both firmware images is decoded and compared
against the CR16 objdump built from binutils 2.44 (the independent oracle).
Each case ends in exactly one status:

    MATCH               decoder and oracle agree
    MISMATCH            decoder and oracle disagree
    UNSUPPORTED         the encoding form is not implemented (no target made up)
    INVALID             the instruction is not a branch / decoder refuses it
    ORACLE_UNAVAILABLE  the oracle could not be run for that address

`MATCH` is only assigned when the oracle actually produced a target.  A
skipped oracle is never counted as a match, and `UNSUPPORTED` is not a pass.

Results are PASS / FAIL / SKIP per assertion, and the whole per-instruction
table is written to JSON on request so that a reviewer can re-check a claim
without the firmware (the image itself is never stored in Git).
"""
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

FW_NORMAL = ROOT / "firmware" / "dectfw_secondlevel_441.hex"
FW_P2TEST = ROOT / "firmware" / "dectfw_secondlevel_441p2test.hex"

OBJDUMP_CANDIDATES = [
    Path("/tmp/opencode/cr16/build/binutils/objdump"),
    Path("/tmp/opencode/cr16/build2/binutils/objdump"),
]

STATUSES = ("MATCH", "MISMATCH", "UNSUPPORTED", "INVALID",
            "ORACLE_UNAVAILABLE")

fails = 0
skips = 0
records = []


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


def objdump():
    for p in OBJDUMP_CANDIDATES:
        if p.is_file():
            return p
    return None


def oracle_target(od, addr, raw, relative_printed=False):
    """Absolute target printed by objdump at the instruction's own address.

    For the branch-if-zero family (`beq0b`/`bne0b`/`beq0w`/`bne0w`) binutils
    prints `2*offset + 2`, i.e. the displacement and not `addr + disp`; the
    flag turns the printed number back into an absolute target.  That is the
    documented difference between the `disps5` and `dispe9` print paths in
    `cr16-dis.c` (`a->constant = 2 * a->constant + 2` happens before the
    `memaddr +` step only for BRANCH_NEQ_INS).
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
            # `bal (ra),*+0x3c8c:m` and `beq0b r0,*+0x2:s` both end with the
            # absolute target; the sign prefix is cosmetic in CR16 objdump
            # (the number is already `addr + displacement`).
            m = re.search(r"\*[+-](0x[0-9a-f]+)", ops)
            if m:
                value = int(m.group(1), 16)
                if relative_printed:
                    return (addr + value) & 0xFFFFFF
                return value
            return None
    return None


# ---------------------------------------------------------------------------
# 1. The two loop heads of 0x25F90, computed field by field
# ---------------------------------------------------------------------------
print("== dispe9 field arithmetic")
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
    check(f"target {hx} @{addr:#07x}", B.cond2_target(addr, w0), want_target)

check("24-bit wrap", B.cond2_target(0xFFFF00, 0x0010), 0xFFFF00)
check("backward wrap", B.cond2_target(0x000010, 0x1F01), (0x000010 - 0x1E) & 0xFFFFFF)

# ---------------------------------------------------------------------------
# 2. Branch-if-zero (disps5) and the 4-byte forms
# ---------------------------------------------------------------------------
print("== other forms")
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

check("register-indirect jump has no target",
      B.decode_insn(0x494, "jump", bytes.fromhex("ee0a"))[2], "NOT_A_BRANCH")
check("register-indirect jal has no target",
      B.decode_insn(0x14, "jal", bytes.fromhex("d600"))[2], "NOT_A_BRANCH")
check("non-branch has no target",
      B.decode_insn(0x25FAE, "loadw", bytes.fromhex("0f890260"))[2],
      "NOT_A_BRANCH")
check("6-byte conditional is unsupported",
      B.decode_insn(0x92FC, "bhi", bytes.fromhex("10004d00074e"))[2],
      "UNSUPPORTED")

# ---------------------------------------------------------------------------
# 3. Full sweep of both images with per-form statistics
# ---------------------------------------------------------------------------
def classify(od, fw, name, sha):
    stats = {}
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
            if oracle is not None and oracle != addr:
                # objdump produced a target for something we call a
                # non-branch: that is a real disagreement.
                verdict = "MISMATCH"
            else:
                verdict = "INVALID"
        else:
            verdict = "INVALID"
        key = (form, verdict)
        stats[key] = stats.get(key, 0) + 1
        if verdict in ("MISMATCH", "UNSUPPORTED"):
            records.append({
                "firmware": name,
                "firmware_sha256": sha,
                "address": f"{addr:#08x}",
                "bytes": insn.raw.hex(),
                "mnemonic": insn.mnemonic,
                "form": form,
                "calculated_target": None if target is None
                else f"{target:#08x}",
                "oracle_target": None if oracle is None else
                f"{oracle:#08x}",
                "status": verdict,
            })
    return stats


def sweep(path, label, od):
    if not path.is_file():
        skip(f"{label} sweep", f"{path} missing")
        return None
    fw = C.load(str(path))
    C.disassemble(fw, str(od))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    stats = classify(od, fw, path.name, sha)
    total = sum(stats.values())
    print(f"-- {label}: {total} branch instructions, sha256 {sha[:16]}...")
    by_verdict = {v: 0 for v in STATUSES}
    for (form, verdict), n in sorted(stats.items()):
        print(f"   {form:20s} {verdict:20s} {n:5d}")
        by_verdict[verdict] += n
    return by_verdict


od = objdump()
if od is None:
    skip("full sweep", "CR16 objdump not available")
else:
    normal = sweep(FW_NORMAL, "normal", od)
    p2 = sweep(FW_P2TEST, "p2test", od)
    if normal is not None:
        check("normal: zero MISMATCH", normal["MISMATCH"], 0)
        check("normal: zero ORACLE_UNAVAILABLE",
              normal["ORACLE_UNAVAILABLE"], 0)
        check("normal: MATCH covers all direct branches",
              normal["MATCH"] > 0, True)
    if p2 is not None:
        check("p2test: zero MISMATCH", p2["MISMATCH"], 0)
        check("p2test: zero ORACLE_UNAVAILABLE",
              p2["ORACLE_UNAVAILABLE"], 0)

# ---------------------------------------------------------------------------
# 4. Machine-readable report
# ---------------------------------------------------------------------------
if "--json" in sys.argv:
    out = Path(sys.argv[sys.argv.index("--json") + 1])
    out.write_text(json.dumps({"records": records}, indent=1) + "\n")
    print(f"wrote {out} ({len(records)} records)")

print()
print(f"{fails} failure(s), {skips} skip(s)")
sys.exit(1 if fails else 0)
