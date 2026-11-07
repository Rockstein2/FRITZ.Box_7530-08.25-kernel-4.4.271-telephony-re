#!/usr/bin/env python3
"""Reconstruct the CR16C exception/dispatch table of the SC14448 firmware.

`INTBASE` is `0x24` in both second-level images.  The reference project
TobleMiner/dialog-cr16c-uart-boot (`device/vectors.s`) shows the encoding:

    vector_table_fixup:
        loadd 0x0(r1,r0), (r5,r4)
        lshd $-1, (r5,r4)          ; shift right by one bit
        stord (r5,r4), 0x0(r1,r0)

so the stored 32-bit value is the handler byte address **divided by two**.
The tool therefore reports both the stored value and `value * 2`.

For each of the 32 entries it records the raw bytes, the decoded instruction
at the computed address, the block it belongs to, whether that block ends in
`retx`, and the processor registers the handler writes (which is the first
evidence about what the vector is for).

A matching numbering with the reference project is a *candidate* only: the
reference targets SC14441.

Usage:
    python3 tools/cr16_vector_map.py --json tools/reports/cr16-vector-map.json
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src" / "mock"))

import cr16_cfg as C  # noqa: E402
import cr16_peripheral_xrefs as X  # noqa: E402
from cr16_boot_memory_map import parse_ihex  # noqa: E402

TOOL_VERSION = "cr16-vector-map/1"
UPSTREAM_SHA = "3d041a683c57fee585e04edc503cd7348f54c4a9"
OBJDUMP = Path("/tmp/opencode/cr16/build/binutils/objdump")
IMAGES = [
    ("normal", ROOT / "firmware" / "dectfw_secondlevel_441.hex"),
    ("p2test", ROOT / "firmware" / "dectfw_secondlevel_441p2test.hex"),
]
INTBASE = 0x24
NVECTORS = 32

# Names from the reference `device/irq.h` `vector_table_t`, used only as a
# candidate label.
REFERENCE_NAMES = [
    "reserved00", "nmi", "reserved02", "reserved03", "reserved04",
    "svc_trap", "dvz_trap", "flg_trap", "bpt_trap", "trc_trap",
    "und_trap", "reserved11", "iad_trap", "reserved13", "dbg_trap",
    "ise_int", "access12_int", "keyb_int", "reserved_int18",
    "ct_classd_int", "uart_ri_int", "uart_ti_int", "spi_int", "tim0_int",
    "tim1_int", "clk100_int", "dip_int", "ad_int", "spi2", "dsp_int",
    "reserved30", "reserved31",
]


def handler_facts(fw, blocks, rows_by_addr, target):
    """Describe the code at `target`: first insn, block end, registers."""
    if target not in fw.insns:
        return {"in_image": False}
    start = None
    for s, addrs in blocks.items():
        if target in addrs:
            start = s
            break
    block = blocks.get(start, [])
    last = fw.insns[block[-1]] if block else None
    mem = []
    for a in block:
        for r in rows_by_addr.get(a, []):
            mem.append({"instruction": r["instruction"],
                        "operation": r["operation"],
                        "address": r["effective_address"]})
    first = fw.insns[target]
    return {
        "in_image": True,
        "first_instruction": f"{first.mnemonic} {first.operands}",
        "block_start": f"0x{start:06x}",
        "block_size": len(block),
        "ends_with_retx": bool(last and last.mnemonic == "retx"),
        "last_instruction": f"{last.mnemonic} {last.operands}" if last else None,
        "memory_operations": mem,
    }


def build(image_name, path):
    mem, blocks_mem, _, errors, _ovl = parse_ihex(path, strict=True)
    fw = C.load(str(path))
    C.disassemble(fw, str(OBJDUMP))
    rows, _st, _unc, _unsup = X.scan(fw, image_name)
    rows_by_addr = {}
    for r in rows:
        rows_by_addr.setdefault(int(r["instruction"], 16), []).append(r)
    blocks = X.blocks_of(fw)

    vectors = []
    for n in range(NVECTORS):
        off = INTBASE + 4 * n
        raw = bytes(mem.get(off + k, 0) for k in range(4))
        stored = int.from_bytes(raw, "little")
        target = stored * 2
        vectors.append({
            "index": n,
            "reference_name": REFERENCE_NAMES[n],
            "table_address": f"0x{off:04x}",
            "raw": raw.hex(),
            "stored": f"0x{stored:08x}",
            "handler_address": f"0x{target:08x}",
            "handler_even": target % 2 == 0,
            "handler": handler_facts(fw, blocks, rows_by_addr, target),
        })
    return {
        "file": path.name,
        "intbase": f"0x{INTBASE:04x}",
        "table_extent": f"0x{INTBASE:04x}-0x{INTBASE + 4 * NVECTORS - 1:04x}",
        "parse_errors": errors,
        "vectors": vectors,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    missing = [str(p) for _, p in IMAGES if not p.is_file()]
    if missing:
        print(f"SKIP: firmware missing: {missing}", file=sys.stderr)
        return 2
    if not OBJDUMP.is_file():
        print("SKIP: CR16 objdump not available", file=sys.stderr)
        return 2

    report = {
        "tool": TOOL_VERSION,
        "upstream": {"repo": "https://github.com/TobleMiner/"
                             "dialog-cr16c-uart-boot",
                     "commit": UPSTREAM_SHA,
                     "files": ["device/vectors.s", "device/irq.h",
                               "device/crt0.s"],
                     "encoding": "stored value * 2 = handler byte address "
                                 "(vectors.s vector_table_fixup: lshd $-1)"},
        "caution": "the vector numbering is a candidate from SC14441 "
                   "hardware; a match is not proof for SC14448",
        "images": {},
    }
    for name, path in IMAGES:
        report["images"][name] = build(name, path)

    text = json.dumps(report, indent=1, sort_keys=True) + "\n"
    if args.json:
        args.json.write_text(text)
        print(f"wrote {args.json}")
    else:
        print(text)
    for name, entry in report["images"].items():
        ids = [v for v in entry["vectors"] if v["handler"]["in_image"]]
        print(f"{name}: {len(entry['vectors'])} vectors, "
              f"{len(ids)} resolve to code")
    return 0


if __name__ == "__main__":
    sys.exit(main())
