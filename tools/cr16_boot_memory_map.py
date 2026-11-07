#!/usr/bin/env python3
"""Reconstruct the SC14448 boot memory layout from the Intel HEX images.

The tool answers, for both images, *which bytes exist where* and *what the
loader writes where*.  It does not claim any hardware property (RAM, ROM,
peripherals) from an address number; every statement carries its evidence
level.

Evidence levels used here:

     L1  bytes present in the Intel HEX file
     L2  decode of an instruction that computes an address or length
     L3  control flow that reaches that instruction
     HYP a hypothesis that fits the code but is not proven

Usage:
    python3 tools/cr16_boot_memory_map.py --json tools/reports/cr16-boot-memory-map.json
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src" / "mock"))

import cr16_cfg as C  # noqa: E402

TOOL_VERSION = "cr16-boot-memory-map/1"
OBJDUMP = Path("/tmp/opencode/cr16/build/binutils/objdump")
IMAGES = [
    ("first", ROOT / "firmware" / "dectfw_firstlevel_441_slow.hex"),
    ("normal", ROOT / "firmware" / "dectfw_secondlevel_441.hex"),
    ("p2test", ROOT / "firmware" / "dectfw_secondlevel_441p2test.hex"),
]


# ---------------------------------------------------------------------------
# Intel HEX
# ---------------------------------------------------------------------------
def parse_ihex(path):
    """Return (bytes_by_address, blocks, record_types, errors)."""
    mem, errors, types = {}, [], {}
    upper = 0
    for lineno, line in enumerate(Path(path).read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        if not line.startswith(":"):
            errors.append(f"{lineno}: not a record")
            continue
        raw = bytes.fromhex(line[1:])
        if len(raw) < 5:
            errors.append(f"{lineno}: short record")
            continue
        count, addr, kind = raw[0], (raw[1] << 8) | raw[2], raw[3]
        data, check = raw[4:4 + count], raw[4 + count]
        if (sum(raw[:-1]) + check) & 0xFF:
            errors.append(f"{lineno}: bad checksum")
        types[str(kind)] = types.get(str(kind), 0) + 1
        if kind == 0x00:
            for i, byte in enumerate(data):
                mem[upper + addr + i] = byte
        elif kind == 0x01:
            break
        elif kind == 0x02:
            upper = ((data[0] << 8) | data[1]) << 4
        elif kind == 0x04:
            upper = ((data[0] << 8) | data[1]) << 16
        else:
            errors.append(f"{lineno}: unsupported type {kind}")
    blocks = []
    if mem:
        start = prev = min(mem)
        for a in sorted(mem)[1:]:
            if a != prev + 1:
                blocks.append((start, prev - start + 1))
                start = a
            prev = a
        blocks.append((start, prev - start + 1))
    return mem, blocks, types, errors


def build_payload(mem, blocks, level):
    """Rebuild the uploader payload: blocks of {u32be addr, u32be len}."""
    out = bytearray()
    for addr, length in blocks:
        out += addr.to_bytes(4, "big") + length.to_bytes(4, "big")
        out += bytes(mem[addr + i] for i in range(length))
    header = 2 if level == 0 else 4
    return {
        "header_bytes": header,
        "payload_length": len(out),
        "outer_header_hex": len(out).to_bytes(header, "big").hex(),
        "total_with_checksum": header + len(out) + 1,
        "first_block_header_hex": out[:8].hex(),
    }


# ---------------------------------------------------------------------------
# code facts
# ---------------------------------------------------------------------------
def find_callers(fw, target):
    """Direct branches/calls that resolve to `target`."""
    found = []
    for addr, insn in sorted(fw.insns.items()):
        if insn.mnemonic not in (C.COND | C.JUMPS | C.CALLS):
            continue
        t, form, status = C.decode_insn(addr, insn.mnemonic, insn.raw[:6])
        if status == "DIRECT" and t == target:
            found.append({"site": f"0x{addr:06x}",
                          "instruction": f"{insn.mnemonic} {insn.operands}"})
    return found


def movd_value_before(fw, addr, pair):
    """Value loaded into `pair` by the nearest preceding `movd $imm,pair`."""
    for back in range(addr - 2, addr - 0x20, -2):
        insn = fw.insns.get(back)
        if insn is None:
            continue
        m = re.match(r"^\$0x([0-9a-f]+):l,\((%s)\)$" % re.escape(pair),
                     insn.operands.replace(" ", ""))
        if m:
            return int(m.group(1), 16), f"0x{back:06x}"
        if insn.mnemonic == "leave" or insn.mnemonic in C.RETS:
            break
    return None, None


def firstlevel_facts(fw):
    """The facts the first-level image establishes, each with its site."""
    facts = []

    def add(site, what, level="L2"):
        facts.append({"site": f"0x{site:06x}", "fact": what, "level": level})

    add(0x10080, "read CFG, clear bit 8 (andw $0xFEFF), write CFG")
    add(0x1008C, "read PSR, clear bits 9 and 11 (andw $0xF5FF), write PSR")
    add(0x10098, "storb $0x30,0xf4020")
    add(0x100A0, "0xf400e: clear bits 0-2, set bit 0")
    add(0x100AE, "0xf4000: clear bits 0-2, set bit 0")
    add(0x100BC, "0xf4000: clear bits 3-4, set bit 3")
    add(0x100CA, "sbitw $0,0xf4838")
    add(0x100CE, "0xf4836: set bits 0-1")
    add(0x100D8, "0xf4836: clear bits 2-3, set bit 2")
    add(0x100E6, "0xf4900 (UART): clear bits 2-4, set bits 2-3")
    add(0x100F4, "sbitw $0 / $1 on 0xf4900")
    add(0x100FC, "sbitw $7 on 0xf4000")
    add(0x10100, "retry loop entry: r2 = 2")
    add(0x1029C, "receive one byte: poll bit 6 of 0xf4900, "
                 "timeout 0xC350, read 0xf4902 -> r2, return r0=1")
    add(0x102C6, "send one byte: write r2 to 0xf4902, poll bit 5 of "
                 "0xf4900, timeout 0xC350, signal 0xf4904")
    add(0x1011E, "read a u32be header into (r13)")
    add(0x1014C, "cmpd $0,(r13): zero header -> length path")
    add(0x10180, "block loop; xorb accumulates a checksum in r11")
    add(0x1019A, "4-byte big-endian value built into (r12): the destination "
                 "pointer")
    add(0x101E2, "4-byte big-endian value built into (r8,r7): the block "
                 "length")
    add(0x1022C, "storb r2,0x0:s(r12): each received byte is stored at the "
                 "header address; (r12) advances at 0x10234")
    add(0x10254, "0xf4836 writes and cbitw on 0xf4838")
    add(0x10278, "set CFG bit 8 (orw $0x100)")
    add(0x10284, "6-byte br, target form not decoded (Q51)")
    add(0x1028A, "send 0x15 then r3")
    add(0x1029C - 0, "shared RX/TX entry points")
    return facts


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

    report = {"tool": TOOL_VERSION, "images": {}, "copy_helper": {},
              "overlaps": [], "handoff": {}}

    for name, path in IMAGES:
        mem, blocks, types, errors = parse_ihex(path)
        level = 0 if name == "first" else 1
        entry = {
            "file": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "record_types": types,
            "parse_errors": errors,
            "data_bytes": len(mem),
            "min_address": f"0x{min(mem):08x}" if mem else None,
            "max_address": f"0x{max(mem):08x}" if mem else None,
            "blocks": [{"address": f"0x{a:08x}", "length": n,
                        "length_hex": f"0x{n:x}"} for a, n in blocks],
            "upload": build_payload(mem, blocks, level),
            "evidence": "L1 for every byte and block address",
        }
        if name == "first":
            fw = C.load(str(path))
            C.disassemble(fw, str(OBJDUMP))
            entry["code_range"] = [f"0x{min(fw.insns):06x}",
                                   f"0x{max(fw.insns):06x}"]
            entry["facts"] = firstlevel_facts(fw)
        report["images"][name] = entry

    # copy helper 0x28D56 (second-level): direction, length, ranges
    fw = C.load(str(IMAGES[1][1]))
    C.disassemble(fw, str(OBJDUMP))
    callers = find_callers(fw, 0x28D56)
    length, site = movd_value_before(fw, 0x15F6, "r3,r2")
    source, src_site = movd_value_before(fw, 0x15F6, "r5,r4")
    report["copy_helper"] = {
        "function": "0x28d56",
        "callers": callers,
        "calling_convention": {
            "dst_pair": "(r3,r2)",
            "src_list_pair": "(r5,r4)",
            "length_unit": "count of {u32be addr,u32be len} entries, "
                           "not bytes",
            "evidence": "L2: 0x28d5c cmpd (r10,r9),(r8,r7) compares the "
                        "two pairs; 0x28d60 loadd 0x0(r8,r7) reads addr, "
                        "0x28d64 loadd 0x4(r8,r7) reads len; 0x28d6a "
                        "addd $8,(r8,r7) advances by one 8-byte header",
        },
        "destination_argument": {
            "value": f"0x{length:08x}" if length is not None else None,
            "loaded_at": site,
        },
        "source_argument": {
            "value": f"0x{source:08x}" if source is not None else None,
            "loaded_at": src_site,
        },
        "direction": "the loop at 0x28d90 writes through (r8,r7) into the "
                     "destination pair (r3,r2); the source is only read",
        "overlap": "UNKNOWN — the destination is (r3,r2), which the call "
                   "loads with 0x1c; whether the block list at (r5,r4) is "
                   "above or below it is not resolved here",
        "reaches_0x24": "UNKNOWN — no instruction in 0x28d56..0x28d9c "
                        "names 0x24",
    }

    # overlaps between the images' own byte ranges
    ranges = []
    for name, entry in report["images"].items():
        for block in entry["blocks"]:
            a = int(block["address"], 16)
            ranges.append((a, a + block["length"], name, block["address"]))
    ranges.sort()
    # only an overlap *within one image* is a real defect of that image
    for i in range(len(ranges) - 1):
        a1, b1, n1, s1 = ranges[i]
        a2, b2, n2, s2 = ranges[i + 1]
        if a2 < b1 and n1 == n2:
            report["overlaps"].append({
                "image": n1, "address_a": s1, "address_b": s2,
                "overlap": f"0x{a2:08x}-0x{min(b1, b2) - 1:08x}",
            })
    report["cross_image_note"] = (
        "the first-level image sits at 0x10080 and the second-level images "
        "start at 0x0, so they do not share a byte range in the files; any "
        "statement about them sharing memory at run time is a hypothesis")

    # hand-off facts
    report["handoff"] = {
        "first_level_jumps_below_code": [
            {"site": "0x1017c", "bytes": "e01885ff",
             "target_form": "0x18 4-byte conditional/branch family",
             "target": "UNKNOWN (Q51)"},
            {"site": "0x10298", "bytes": "e01869fe",
             "target_form": "same family", "target": "UNKNOWN (Q51)"},
        ],
        "second_level_start": {
            "normal": "0x15bc (system-register setup begins; 0x15aa is the "
                      "block entry, no caller in the image)",
            "p2test": "0x103a",
        },
        "upload_destination": {
            "proven": "the loader stores each byte at the address carried in "
                      "the block header (0x1022C), so the second-level image "
                      "lands at its declared addresses",
            "not_proven": "the control transfer into the loaded code",
            "evidence": "L2 for the store, UNKNOWN for the branch",
        },
        "evidence": "L3 for the block boundaries, UNKNOWN for the hand-off "
                    "target",
    }

    text = json.dumps(report, indent=1, sort_keys=True) + "\n"
    if args.json:
        args.json.write_text(text)
        print(f"wrote {args.json}")
    else:
        print(text)
    for name, entry in report["images"].items():
        print(name, entry["data_bytes"], "bytes in",
              len(entry["blocks"]), "block(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
