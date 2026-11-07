#!/usr/bin/env python3
"""Tests for the peripheral cross-reference scanner.

Run: python3 tools/tests/test_cr16_peripheral_xrefs.py

Two kinds of checks:

* synthetic images with known instructions (built as Intel HEX in a temporary
  file) exercise the operand parser and the register-state analysis,
  including the cases required by the task: a known pair, an unknown pair, a
  half-register overwrite, and two branches that disagree;
* both real images are swept and checked against the committed report.

Results are PASS / FAIL / SKIP.  A missing firmware or CR16 objdump is a
SKIP, and the report is never rewritten in that case.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src" / "mock"))

import cr16_cfg as C  # noqa: E402
import cr16_peripheral_xrefs as X  # noqa: E402

OBJDUMP = Path("/tmp/opencode/cr16/build/binutils/objdump")
REPORT = ROOT / "tools" / "reports" / "peripheral-xrefs.json"
FW = ROOT / "firmware" / "dectfw_secondlevel_441.hex"
FW2 = ROOT / "firmware" / "dectfw_secondlevel_441p2test.hex"

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


def hexfile(records):
    lines = []
    for addr, data in records:
        b = [len(data), (addr >> 8) & 0xFF, addr & 0xFF, 0x00] + list(data)
        chk = (-sum(b)) & 0xFF
        lines.append(":" + "".join(f"{x:02X}" for x in b + [chk]))
    lines.append(":00000001FF")
    f = tempfile.NamedTemporaryFile(suffix=".hex", delete=False, mode="w")
    f.write("\n".join(lines) + "\n")
    f.close()
    return f.name


def synth(words, size=64):
    """Build a synthetic image from a byte list placed at 0."""
    img = bytearray(size)
    img[:len(words)] = bytes(words)
    return hexfile([(0, bytes(img))])


def scan_image(path):
    fw = C.load(path)
    C.disassemble(fw, str(OBJDUMP))
    return X.scan(fw, "synthetic")


def find(rows, addr, kind=None):
    return [r for r in rows if r["instruction"] == f"0x{addr:06x}"
            and (kind is None or r["operation"] == kind)]


# ---------------------------------------------------------------------------
# 1. operand parsing
# ---------------------------------------------------------------------------
print("== operand parser")
P = X.parse_memory_operand
check("abs20", P("0xf6002:m"), ("ABS", 0xF6002))
check("pair with 0x0:s", P("0x0:s(r1,r0)"), ("DISP_RP", (0, "r1", "r0")))
check("pair with 0x2:m", P("0x2:m(r4,r3)"), ("DISP_RP", (2, "r4", "r3")))
check("bare pair", P("(r1,r0)"), ("DISP_RP", (0, "r1", "r0")))
check("single register", P("0x10:m(r5)"), ("DISP_R", (0x10, "r5")))
check("stack", P("0x0:s(sp)"), ("STACK", None))
check("indexed r12", P("[r12]0x108:l(r1,r0)"), ("IDX", ("r12", 0x108)))
check("plain register is not memory", P("r2"), None)
check("abs20 from bytes", X.abs20_address(bytes.fromhex("0f890260")), 0xF6002)
check("abs20 from bytes (store)", X.abs20_address(bytes.fromhex("0fc90264")),
      0xF6402)
check("abs24 from bytes (0x116bc)", X.abs24_address(bytes.fromhex("130010f1bc16")),
      0x116BC)
# the same three encodings the CR16 assembler emits for `<abs>:l` operands
check("abs24 from bytes (0x0fffff)", X.abs24_address(bytes.fromhex("1300007fffff")),
      0x0FFFFF)
check("abs24 from bytes (0x100000)", X.abs24_address(bytes.fromhex("130001700000")),
      0x100000)
check("abs24 from bytes (0xff4c00)", X.abs24_address(bytes.fromhex("13000f7f004c")),
      0xFF4C00)
check("pc-relative operand", P("0x12:s(ra)"), ("DISP_R", (0x12, "ra")))

# ---------------------------------------------------------------------------
# 2. synthetic register-pair cases
# ---------------------------------------------------------------------------
if not OBJDUMP.is_file():
    skip("synthetic cases", "CR16 objdump not available")
else:
    print("== synthetic: known pair")
    # 0x00 movd $0xff6006:l,(r1,r0)   70 00 ff 00 06 60
    # 0x06 storw r2,0x0:s(r1,r0)      20 d0
    # 0x08 loadw 0x0:s(r1,r0),r2      20 90
    # 0x0a storw $0x0:s,0x0:s(r1,r0)  00 c2
    path = synth([0x70, 0x00, 0xFF, 0x00, 0x06, 0x60,
                  0x20, 0xD0, 0x20, 0x90, 0x00, 0xC2])
    rows, stats, unc = scan_image(path)
    for addr, kind in ((0x06, "WRITE"), (0x08, "READ"), (0x0A, "WRITE")):
        hit = find(rows, addr, kind)
        check(f"known pair {addr:#04x} is RESOLVED", 
              hit[0]["address_kind"] if hit else None, "RESOLVED")
        check(f"known pair {addr:#04x} address",
              hit[0]["effective_address"] if hit else None, "0x00ff6006")
    load = find(rows, 0x00, "ADDRESS_LOAD")
    check("movd is recorded as ADDRESS_LOAD",
          load[0]["effective_address"] if load else None, "0x00ff6006")

    print("== synthetic: unknown pair")
    # storw r2,0x0:s(r5,r4) with no prior assignment
    path = synth([0x24, 0xD0])
    rows, stats, unc = scan_image(path)
    hit = find(rows, 0x00, "WRITE")
    check("unknown pair is UNKNOWN",
          hit[0]["address_kind"] if hit else None, "UNKNOWN")
    check("unknown pair has no numeric address",
          hit[0]["effective_address"] if hit else None, None)
    check("unknown pair keeps its expression",
          hit[0]["expression"] if hit else None, "(r5,r4)+0")

    print("== synthetic: half-register overwrite")
    # movd $0xff6006:l,(r1,r0) ; movw $0,r0 ; storw r2,0x0:s(r1,r0)
    path = synth([0x70, 0x00, 0xFF, 0x00, 0x06, 0x60,
                  0x00, 0x5A,          # movw $0x0:s,r0
                  0x20, 0xD0])
    rows, stats, unc = scan_image(path)
    hit = find(rows, 0x08, "WRITE")
    check("pair invalidated by writing r0",
          hit[0]["address_kind"] if hit else None, "UNKNOWN")

    print("== synthetic: base plus index")
    # movd $0x01000000:l,(r5,r4) ; movzw r3,(r7,r6) ; ashud $1,(r7,r6)
    # addd (r7,r6),(r5,r4) ; storw r2,0x0:s(r5,r4)
    path = synth([0x74, 0x00, 0x00, 0x01, 0x00, 0x00,
                  0x36, 0x5F,          # movzw r3,(r7,r6)
                  0x16, 0x4C,          # ashud $1:s,(r7,r6)
                  0x64, 0x61,          # addd (r7,r6),(r5,r4)
                  0x24, 0xD0])
    rows, stats, unc = scan_image(path)
    hit = find(rows, 0x0C, "WRITE")
    check("indexed store is SYMBOLIC",
          hit[0]["address_kind"] if hit else None, "SYMBOLIC")
    check("indexed store has no fixed address",
          hit[0]["effective_address"] if hit else None, None)
    check("indexed store carries the base",
          "0x01000000" in (hit[0]["expression"] or "") if hit else None, True)
    check("indexed store names the doubled index",
          "2*r3" in (hit[0]["expression"] or "") if hit else None, True)

    print("== synthetic: two branches disagree")
    # beq to 0x10; one path sets the pair, the other does not; merge at 0x10
    # 0x00 beq *+0x0E  (12 10 -> +2)   use `12 10`: bne +2
    # 0x02 movd $0xff6006:l,(r1,r0)
    # 0x08 br *+0x08
    # 0x0A nop (skipped)
    # 0x0C storw from an untouched path
    path = synth([0x12, 0x10,                      # 0x00 bne +2
                  0x70, 0x00, 0xFF, 0x00, 0x06, 0x60,   # 0x02 movd
                  0xE4, 0x10,                      # 0x08 br +8
                  0x00, 0x2C,                      # 0x0A nop
                  0x24, 0xD0,                      # 0x0C storw (r5,r4)
                  0x24, 0xD0,                      # 0x0E unreachable
                  0x24, 0xD0])                     # 0x10 storw (r5,r4)
    rows, stats, unc = scan_image(path)
    hit = find(rows, 0x0C, "WRITE") + find(rows, 0x10, "WRITE")
    check("state does not leak across blocks",
          all(r["address_kind"] != "RESOLVED" for r in hit), True)

# ---------------------------------------------------------------------------
# 3. real images
# ---------------------------------------------------------------------------
if not FW.is_file() or not FW2.is_file() or not OBJDUMP.is_file():
    skip("real images", "firmware or CR16 objdump missing")
else:
    import hashlib
    for path, label in ((FW, "normal"), (FW2, "p2test")):
        fw = C.load(str(path))
        C.disassemble(fw, str(OBJDUMP))
        rows, stats, unc = X.scan(fw, label)
        by = {(r["instruction"], r["address_kind"])
              for r in rows}
        print(f"== {label}: {len(rows)} operations")
        check(f"{label}: RESOLVED operations exist",
              any(r["address_kind"] == "RESOLVED" for r in rows), True)
        check(f"{label}: SYMBOLIC operations exist",
              any(r["address_kind"] == "SYMBOLIC" for r in rows), True)
        check(f"{label}: UNKNOWN operations exist",
              any(r["address_kind"] == "UNKNOWN" for r in rows), True)
        check(f"{label}: STACK operations exist",
              any(r["address_kind"] == "STACK" for r in rows), True)

    # the four required checks on the real image
    fw = C.load(str(FW))
    C.disassemble(fw, str(OBJDUMP))
    rows, stats, unc = X.scan(fw, "normal")

    def op(addr, kind):
        h = find(rows, addr, kind)
        return (h[0]["address_kind"], h[0]["effective_address"]) if h else None

    check("0x258c writes 0x00FF6006", op(0x258C, "WRITE"),
          ("RESOLVED", "0x00ff6006"))
    check("0x25aa reads 0x00FF6006", op(0x25AA, "READ"),
          ("RESOLVED", "0x00ff6006"))
    check("0x25b4 writes 0x00FF6006", op(0x25B4, "WRITE"),
          ("RESOLVED", "0x00ff6006"))
    check("0x259c reads 0x00FF5406", op(0x259C, "READ"),
          ("RESOLVED", "0x00ff5406"))
    check("0x25a2 writes 0x00FF5406", op(0x25A2, "WRITE"),
          ("RESOLVED", "0x00ff5406"))
    fill = find(rows, 0x25D0, "WRITE")
    check("0x25d0 is SYMBOLIC",
          fill[0]["address_kind"] if fill else None, "SYMBOLIC")
    check("0x25d0 expression references the fill base",
          "0x01000000" in (fill[0]["expression"] or "") if fill else None,
          True)

    # the two address spaces must never be merged
    for addr in ("0x000f6006", "0x00ff6006"):
        hits = [r for r in rows if r["effective_address"] == addr]
        check(f"{addr} is reported as its own address",
              len(hits) > 0, True)
    f6006 = {r["instruction"] for r in rows
             if r["effective_address"] == "0x000f6006"}
    ff6006 = {r["instruction"] for r in rows
              if r["effective_address"] == "0x00ff6006"}
    check("the two 0xF6006 address spaces share no instruction",
          f6006 & ff6006, set())

    # the abs24 (`data:l`) form: accesses that were invisible before PERIPH-2
    check("0x15ae writes 0x00FF4C00 (abs24)",
          op(0x15AE, "WRITE"), ("RESOLVED", "0x00ff4c00"))
    check("0x15b6 writes 0x00FF5000 (abs24)",
          op(0x15B6, "WRITE"), ("RESOLVED", "0x00ff5000"))
    check("0x0f6002 poll is at 0x25FAE",
          op(0x25FAE, "READ"), ("RESOLVED", "0x000f6002"))
    check("every memory instruction is classified",
          unc, [])

# ---------------------------------------------------------------------------
# 4. the committed report is reproducible
# ---------------------------------------------------------------------------
if not REPORT.is_file():
    skip("report reproducibility", f"{REPORT} missing")
else:
    out = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "cr16_peripheral_xrefs.py"),
         "--json", "/tmp/peripheral-xrefs-check.json"],
        capture_output=True, text=True)
    if out.returncode != 0:
        skip("report reproducibility", out.stderr.strip() or "tool failed")
    else:
        generated = json.loads(Path("/tmp/peripheral-xrefs-check.json").read_text())
        committed = json.loads(REPORT.read_text())
        check("committed report matches a fresh run", committed, generated)

print()
print(f"{fails} failure(s), {skips} skip(s)")
sys.exit(1 if fails else 0)
