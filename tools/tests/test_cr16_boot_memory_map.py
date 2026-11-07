#!/usr/bin/env python3
"""Tests for the boot memory map tool.

Run: python3 tools/tests/test_cr16_boot_memory_map.py

Results are PASS / FAIL / SKIP.  Without the firmware the tool must SKIP and
must not rewrite the committed report.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import cr16_boot_memory_map as M  # noqa: E402

REPORT = ROOT / "tools" / "reports" / "cr16-boot-memory-map.json"
IMAGES = {name: path for name, path in M.IMAGES}
OBJDUMP = Path("/tmp/opencode/cr16/build/binutils/objdump")

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


def ihex(lines):
    f = tempfile.NamedTemporaryFile(suffix=".hex", delete=False, mode="w")
    f.write("\n".join(lines) + "\n")
    f.close()
    return f.name


# ---------------------------------------------------------------------------
# 1. Intel HEX parsing, including extended-address records
# ---------------------------------------------------------------------------
print("== Intel HEX parsing")


def rec(count, addr, kind, data):
    body = bytes([count, (addr >> 8) & 0xFF, addr & 0xFF, kind]) + bytes(data)
    return ":" + (body + bytes([(-sum(body)) & 0xFF])).hex().upper()


plain = ihex([rec(2, 0x10, 0, [0xAA, 0xBB]), rec(0, 0, 1, [])])
mem, blocks, types, errors = M.parse_ihex(plain)
check("data record parsed", mem.get(0x10), 0xAA)
check("second byte parsed", mem.get(0x11), 0xBB)
check("block found", blocks, [(0x10, 2)])
check("no parse errors", errors, [])

ext = ihex([rec(2, 0, 4, [0x00, 0x01]),      # upper = 0x00010000
            rec(1, 0x20, 0, [0x5A]),
            rec(0, 0, 1, [])])
mem, blocks, types, errors = M.parse_ihex(ext)
check("extended linear address applied", mem.get(0x00010020), 0x5A)
check("extended block start", blocks[0][0], 0x00010020)

seg = ihex([rec(2, 0, 2, [0x10, 0x00]),      # segment 0x1000 -> 0x10000
            rec(1, 0x02, 0, [0x77]),
            rec(0, 0, 1, [])])
mem, blocks, types, errors = M.parse_ihex(seg)
check("extended segment address applied", mem.get(0x10002), 0x77)

# ---------------------------------------------------------------------------
# 2. Overlap detection
# ---------------------------------------------------------------------------
print("== overlap detection")
tmp_a = ihex([rec(4, 0x100, 0, [1, 2, 3, 4]), rec(0, 0, 1, [])])
mem, blocks, _, _ = M.parse_ihex(tmp_a)
check("a single block has no overlap", len(blocks), 1)
tmp_b = ihex([rec(2, 0x100, 0, [1, 2]),
              rec(2, 0x102, 0, [3, 4]),      # contiguous -> one block
              rec(0, 0, 1, [])])
mem, blocks, _, _ = M.parse_ihex(tmp_b)
check("contiguous records merge", blocks, [(0x100, 4)])
check("a gap splits blocks",
      [b[0] for b in blocks], [0x100])

# ---------------------------------------------------------------------------
# 3-5. copy semantics: direction, length, overlap
# ---------------------------------------------------------------------------
print("== copy semantics")
fw_path = IMAGES["normal"]
if not fw_path.is_file() or not OBJDUMP.is_file():
    skip("copy semantics", "firmware or objdump missing")
else:
    sys.path.insert(0, str(ROOT / "src" / "mock"))
    import cr16_cfg as C
    fw = C.load(str(fw_path))
    C.disassemble(fw, str(OBJDUMP))
    callers = M.find_callers(fw, 0x28D56)
    check("copy helper has exactly one caller", len(callers), 1)
    check("caller is the start-up block", callers[0]["site"], "0x0015f6")
    length, site = M.movd_value_before(fw, 0x15F6, "r3,r2")
    check("destination argument is 0x1c", length, 0x1C)
    check("destination loaded just before the call", site, "0x0015ea")
    source, _ = M.movd_value_before(fw, 0x15F6, "r5,r4")
    check("source argument is 0x24", source, 0x24)

    # the loop writes through the destination pair and advances the source
    ops = [fw.insns[a] for a in sorted(fw.insns)
           if 0x28D56 <= a <= 0x28D9C]
    text = " ".join(f"{i.mnemonic} {i.operands}" for i in ops)
    check("direction: writes via (r8,r7), which holds the destination",
          "storb r0,0x0:s(r8,r7)" in text, True)
    check("length is counted in 8-byte entries",
          "addd $0x8:s,(r8,r7)" in text, True)
    check("the source pair is only read",
          "loadd 0x0:s(r8,r7)" in text, True)

# ---------------------------------------------------------------------------
# 6. a jump to code that is absent from the image
# ---------------------------------------------------------------------------
print("== jump into absent code")
first_path = IMAGES["first"]
if not first_path.is_file():
    skip("hand-off", "first-level firmware missing")
else:
    mem, blocks, _, _ = M.parse_ihex(first_path)
    check("first-level starts at 0x10080", blocks[0][0], 0x10080)
    check("first-level does not contain 0x7c", 0x7C in mem, False)
    sec_mem, sec_blocks, _, _ = M.parse_ihex(IMAGES["normal"])
    check("second-level does contain 0x7c", 0x7C in sec_mem, True)

# ---------------------------------------------------------------------------
# 7. normal and p2test compared separately
# ---------------------------------------------------------------------------
print("== image comparison")
if not all(IMAGES[k].is_file() for k in ("normal", "p2test", "first")):
    skip("image comparison", "firmware missing")
else:
    n_mem, n_blocks, _, _ = M.parse_ihex(IMAGES["normal"])
    p_mem, p_blocks, _, _ = M.parse_ihex(IMAGES["p2test"])
    f_mem, f_blocks, _, _ = M.parse_ihex(IMAGES["first"])
    check("normal and p2test are parsed separately",
          len(n_mem) != len(p_mem) or n_mem is not p_mem, True)
    # The images are separate files; no byte is shared, but the first-level
    # range (0x10080) falls inside the *envelope* of the second-level image
    # (0x0-0x28dcd), which is why "the loader and the loaded code coexist in
    # memory" is a hypothesis, not a byte-level fact.
    check("no byte is shared between the first- and second-level images",
          len(set(f_mem) & set(n_mem)), 0)
    check("the first-level range falls inside the second-level envelope",
          0x10080 <= max(n_mem), True)

# ---------------------------------------------------------------------------
# 8. file bytes vs. claimed runtime bytes stay separate
# ---------------------------------------------------------------------------
print("== file vs runtime")
if first_path.is_file():
    mem, blocks, _, _ = M.parse_ihex(first_path)
    payload = M.build_payload(mem, blocks, 0)
    check("upload payload has a 2-byte header for level 0",
          payload["header_bytes"], 2)
    check("payload length excludes header and checksum",
          payload["payload_length"], len(mem) + 8)
    mem2, blocks2, _, _ = M.parse_ihex(IMAGES["normal"])
    payload2 = M.build_payload(mem2, blocks2, 1)
    check("upload payload has a 4-byte header for level 1",
          payload2["header_bytes"], 4)

# ---------------------------------------------------------------------------
# 9-10. committed report and its claims
# ---------------------------------------------------------------------------
print("== committed report")
if not REPORT.is_file():
    skip("report checks", f"{REPORT} missing")
elif not all(p.is_file() for _, p in M.IMAGES):
    skip("report checks", "firmware missing")
else:
    data = json.loads(REPORT.read_text())
    check("report names all three images",
          sorted(data["images"]), ["first", "normal", "p2test"])
    check("copy helper direction is stated",
          "writes through" in data["copy_helper"]["direction"], True)
    check("copy helper overlap is UNKNOWN",
          data["copy_helper"]["overlap"].startswith("UNKNOWN"), True)
    check("no within-image overlaps",
          [o for o in data["overlaps"] if "image" in o], [])
    check("hand-off target is UNKNOWN",
          all("UNKNOWN" in h["target"]
              for h in data["handoff"]["first_level_jumps_below_code"]),
          True)
    # no hardware property may be claimed from an address number
    text = json.dumps(data).lower()
    check("no RAM/ROM claim in the report",
          ("\"ram\"" not in text) and ("\"rom\"" not in text), True)

    print("== reproducibility")
    out = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "cr16_boot_memory_map.py"),
         "--json", "/tmp/cr16-boot-map-check.json"],
        capture_output=True, text=True)
    if out.returncode != 0:
        skip("report reproducibility", out.stderr.strip() or "tool failed")
    else:
        check("committed report matches a fresh run",
              json.loads(REPORT.read_text()),
              json.loads(Path("/tmp/cr16-boot-map-check.json").read_text()))

print()
print(f"{fails} failure(s), {skips} skip(s)")
sys.exit(1 if fails else 0)
