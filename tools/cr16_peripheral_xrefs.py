#!/usr/bin/env python3
"""Static cross-reference scanner for SC14448 peripheral addresses.

Scans both vendor images for every memory access whose **effective address is
known at analysis time**, and records it together with the evidence level.

What counts as "known":

* **abs20** operands (`loadw`/`storw`/`loadb`/`storb`/`loadd`/`stord` with a
  16-bit `:m` address and no base register): the address is
  `((byte0 & 0x0F) << 16) | word1`, complete inside the instruction —
  level L2.
* addresses loaded with `movd $imm:l,(rp)` — the literal is recorded as a
  base; the accesses that follow are only linked to it when the register
  pair is not overwritten in between (level L2 for the literal, the link
  itself is L2 with a documented rule).
* `movd`/`ld`-style 16-bit immediates that look like addresses are **not**
  resolved: they may be data or arithmetic constants.

Every other access (base register plus displacement, computed pointers) is
reported as `RUNTIME_ADDRESS` with the expression it uses, never with a
guessed numeric address.

Usage:
    python3 tools/cr16_peripheral_xrefs.py [--json PATH] [--ranges a-b,...]

The tool is read-only and works offline.  Firmware files are not written to
Git; only aggregates and the addresses that matter are reported.
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src" / "mock"))

import cr16_cfg as C  # noqa: E402

OBJDUMP = Path("/tmp/opencode/cr16/build/binutils/objdump")
IMAGES = [
    ("normal", ROOT / "firmware" / "dectfw_secondlevel_441.hex"),
    ("p2test", ROOT / "firmware" / "dectfw_secondlevel_441p2test.hex"),
]

ACCESS = {"loadw": ("read", 16), "storw": ("write", 16),
          "loadb": ("read", 8), "storb": ("write", 8),
          "loadd": ("read", 32), "stord": ("write", 32)}

ABS20_RE = re.compile(r"^(?:r\d+|\$0x[0-9a-f]+:s),0x([0-9a-f]+):m$")
ABS20_RE2 = re.compile(r"^0x([0-9a-f]+):m,(?:r\d+|\(r\d+,r\d+\))$")
LOADED_RE = re.compile(r"^0x([0-9a-f]+):m,r\d+$")
BASE_RE = re.compile(r"^(\d+):m\((r\d+),(r\d+)\)$")


def abs20(raw):
    """Absolute 20-bit address of an abs20 operand, from the bytes."""
    return ((raw[0] & 0x0F) << 16) | raw[2] | (raw[3] << 8)


def scan(fw, image):
    """Return (records, bases) for one image."""
    records = []
    bases = {}

    def add(addr, insn, kind, width, effective, evidence, note=""):
        records.append({
            "image": image,
            "address": f"{addr:#08x}",
            "bytes": insn.raw.hex(),
            "mnemonic": insn.mnemonic,
            "access": kind,
            "width": width,
            "effective_address": effective,
            "evidence": evidence,
            "note": note,
        })

    for addr, insn in sorted(fw.insns.items()):
        mn = insn.mnemonic
        if mn in ACCESS and insn.size == 4:
            kind, width = ACCESS[mn]
            m = ABS20_RE.match(insn.operands.replace(" ", "")) or \
                LOADED_RE.match(insn.operands.replace(" ", ""))
            if not m:
                m = ABS20_RE2.match(insn.operands.replace(" ", ""))
            if m and abs20(insn.raw) == int(m.group(1), 16):
                add(addr, insn, kind, width, f"0x{abs20(insn.raw):06x}",
                    "L2 abs20")
        if mn == "movd":
            m = re.search(r"\$0x([0-9a-f]+):l,\((r\d+),(r\d+)\)",
                          insn.operands)
            if m:
                value = int(m.group(1), 16)
                bases[(m.group(2), m.group(3))] = (value, addr, insn)
                add(addr, insn, "address_load", 32, f"0x{value:08x}",
                    "L2 movd literal", "loaded into a register pair")
        # base-register accesses: record the shape, not a guessed address
        m = BASE_RE.match(insn.operands.replace(" ", ""))
        if m and mn in ACCESS:
            rp = (m.group(2), m.group(3))
            if rp in bases:
                value, src, _ = bases[rp]
                eff = value + int(m.group(1))
                add(addr, insn, ACCESS[mn][0], ACCESS[mn][1],
                    f"0x{eff:08x}", "L2 movd base + displacement",
                    f"base set at {src:#x}")
            else:
                add(addr, insn, ACCESS[mn][0], ACCESS[mn][1],
                    f"({m.group(2)},{m.group(3)})+{m.group(1)}",
                    "RUNTIME_ADDRESS", "base register not known statically")
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path)
    ap.add_argument("--ranges", default="0x000F4000-0x000F7FFF,"
                                       "0x00FF4000-0x00FF7FFF,"
                                       "0x01000000-0x01001000")
    ap.add_argument("--objdump", type=Path, default=OBJDUMP)
    args = ap.parse_args()

    if not args.objdump.is_file():
        print("SKIP: CR16 objdump not available", file=sys.stderr)
        return 2
    missing = [str(p) for _, p in IMAGES if not p.is_file()]
    if missing:
        print(f"SKIP: firmware missing: {missing}", file=sys.stderr)
        return 2

    ranges = []
    for item in args.ranges.split(","):
        lo, hi = item.split("-")
        ranges.append((int(lo, 0), int(hi, 0)))

    report = {"tool": "cr16-peripheral-xrefs/1", "ranges": [], "images": {}}
    for image, path in IMAGES:
        fw = C.load(str(path))
        C.disassemble(fw, str(args.objdump))
        recs = scan(fw, image)
        stats = defaultdict(int)
        for r in recs:
            stats[(r["access"], r["evidence"])] += 1
        hits = []
        for r in recs:
            eff = r["effective_address"]
            if not eff.startswith("0x"):
                continue
            value = int(eff, 16)
            if any(lo <= value <= hi for lo, hi in ranges):
                hits.append(r)
        report["images"][image] = {
            "decoded_instructions": len(fw.insns),
            "records": len(recs),
            "by_kind": {f"{k[0]}/{k[1]}": v for k, v in sorted(stats.items())},
            "in_ranges": hits,
        }
    report["ranges"] = [f"{lo:#010x}-{hi:#010x}" for lo, hi in ranges]

    text = json.dumps(report, indent=1, sort_keys=True) + "\n"
    if args.json:
        args.json.write_text(text)
        print(f"wrote {args.json}")
    else:
        print(text)
    for image in report["images"]:
        print(f"{image}: {report['images'][image]['records']} records, "
              f"{len(report['images'][image]['in_ranges'])} in the ranges")
    return 0


if __name__ == "__main__":
    sys.exit(main())
