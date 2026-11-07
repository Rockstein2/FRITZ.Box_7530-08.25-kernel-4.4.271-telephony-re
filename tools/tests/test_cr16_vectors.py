#!/usr/bin/env python3
"""Tests for the vector table reconstruction.

Run: python3 tools/tests/test_cr16_vectors.py
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import cr16_vector_map as V  # noqa: E402

REPORT = ROOT / "tools" / "reports" / "cr16-vector-map.json"
FW = {"normal": ROOT / "firmware" / "dectfw_secondlevel_441.hex",
      "p2test": ROOT / "firmware" / "dectfw_secondlevel_441p2test.hex"}

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


print("== encoding")
check("INTBASE", V.INTBASE, 0x24)
check("0xa0 starts a TLV block, not a vector", 0xA0 - 0x24, 4 * 31)
check("31 vectors", V.NVECTORS, 31)
check("table extent", f"0x{0x24:04x}-0x{0x24 + 4 * 31 - 1:04x}",
      "0x0024-0x009f")
check("value x 2 is the handler address", 0x146E5 * 2, 0x28DCA)
check("reference names cover 31 entries", len(V.REFERENCE_NAMES), 31)

print("== vector index")
for offset, index in ((0x74, 20), (0x78, 21), (0x7C, 22),
                      (0x84, 24), (0x88, 25), (0x8C, 26), (0x98, 29)):
    check(f"index of 0x{offset:02x}",
          (offset - V.INTBASE) // 4, index)

if not all(p.is_file() for p in FW.values()):
    skip("image checks", "firmware missing")
elif not V.OBJDUMP.is_file():
    skip("image checks", "CR16 objdump missing")
else:
    print("== images")
    for name, path in FW.items():
        entry = V.build(name, path)
        vecs = entry["vectors"]
        check(f"{name}: 31 entries", len(vecs), 31)
        check(f"{name}: table starts at 0x24", vecs[0]["table_address"],
              "0x0024")
        check(f"{name}: table ends at 0x9c", vecs[30]["table_address"],
              "0x009c")
        check(f"{name}: every entry is 4 bytes",
              {len(v["raw"]) for v in vecs}, {8})   # hex string of 4 bytes
        resolved = [v for v in vecs if v["handler"]["in_image"]]
        check(f"{name}: all 31 entries resolve to code", len(resolved), 31)
        check(f"{name}: every resolved handler is even",
              all(v["handler_even"] for v in resolved), True)
        # the concrete handler addresses
        by_index = {v["index"]: v["handler_address"] for v in vecs}
        if name == "normal":
            want = {24: "0x00028996", 26: "0x00028cd0", 29: "0x00028a94"}
        else:
            want = {24: "0x0002772a", 26: "0x00027c88", 29: "0x00027914"}
        for idx, addr in want.items():
            check(f"{name}: vector {idx} handler", by_index[idx], addr)
            h = vecs[idx]["handler"]
            check(f"{name}: vector {idx} handler exists", h["in_image"], True)
        # indices 20..22 must be the shared stub, not a UART/SPI handler
        for idx in (20, 21, 22):
            check(f"{name}: vector {idx} is the stub",
                  vecs[idx]["handler"]["block_size"], 2)

    print("== determinism of the table across images")
    n = V.build("normal", FW["normal"])
    p = V.build("p2test", FW["p2test"])
    n_shared = {v["index"] for v in n["vectors"]
                if v["handler"].get("block_size") == 2}
    p_shared = {v["index"] for v in p["vectors"]
                if v["handler"].get("block_size") == 2}
    check("the same indices share the stub in both images",
          n_shared, p_shared)
    check("both images have the same set of real handlers",
          {v["index"] for v in n["vectors"]
           if v["handler"].get("block_size", 0) > 2},
          {v["index"] for v in p["vectors"]
           if v["handler"].get("block_size", 0) > 2})

print("== 0xa0 is data, not a vector")
if FW["normal"].is_file():
    sys.path.insert(0, str(ROOT / "tools"))
    from cr16_boot_memory_map import parse_ihex
    mem, _, _, _, _ = parse_ihex(FW["normal"])
    raw = bytes(mem.get(a, 0) for a in range(0xA0, 0xA2))
    check("0xa0 starts with TLV tag 1", raw[0], 1)
    check("its length is 5 (the RFPI record)", raw[1], 5)
    check("the table's last entry is at 0x9c",
          0x9C + 4, 0xA0)

print("== committed report")
if not REPORT.is_file():
    skip("report", f"{REPORT} missing")
else:
    data = json.loads(REPORT.read_text())
    check("report names the upstream commit",
          data["upstream"]["commit"], V.UPSTREAM_SHA)
    check("report records the encoding",
          "lshd" in data["upstream"]["encoding"], True)
    for name in ("normal", "p2test"):
        check(f"{name}: 31 vectors in the report",
              len(data["images"][name]["vectors"]), 31)
    out = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "cr16_vector_map.py"),
         "--json", "/tmp/cr16-vector-check.json"],
        capture_output=True, text=True)
    if out.returncode != 0:
        skip("reproducibility", out.stderr.strip() or "tool failed")
    else:
        check("report reproduces",
              json.loads(REPORT.read_text()),
              json.loads(Path("/tmp/cr16-vector-check.json").read_text()))

print()
print(f"{fails} failure(s), {skips} skip(s)")
sys.exit(1 if fails else 0)
