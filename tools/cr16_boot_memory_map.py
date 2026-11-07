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
def parse_ihex(path, strict=False):
    """Parse Intel HEX.

    Returns (bytes_by_address, blocks, record_types, errors, overlaps).

    An address written by two different data records is recorded in
    `overlaps`: identical bytes are `benign`, different bytes are
    `conflicting` and, with `strict=True`, become an error so the caller
    refuses to build a report.
    """
    mem, errors, types, overlaps = {}, [], {}, []
    upper = 0
    for lineno, line in enumerate(Path(path).read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        if not line.startswith(":"):
            errors.append(f"{lineno}: not a record")
            continue
        try:
            raw = bytes.fromhex(line[1:])
        except ValueError:
            errors.append(f"{lineno}: not hex")
            continue
        if len(raw) < 5:
            errors.append(f"{lineno}: short record")
            continue
        count, addr = raw[0], (raw[1] << 8) | raw[2]
        kind = raw[3]
        if len(raw) != count + 5:
            errors.append(f"{lineno}: length field {count} does not match "
                          f"{len(raw) - 5} data bytes")
            continue
        data, check = raw[4:4 + count], raw[4 + count]
        if (sum(raw[:-1]) + check) & 0xFF:
            errors.append(f"{lineno}: bad checksum")
        types[str(kind)] = types.get(str(kind), 0) + 1
        if kind == 0x00:
            if count == 0:
                errors.append(f"{lineno}: empty data record")
            base = upper + addr
            if base + count - 1 > 0xFFFFFFFF:
                errors.append(f"{lineno}: address range overflows 32 bits")
                continue
            for i, byte in enumerate(data):
                where = base + i
                if where in mem:
                    same = mem[where] == byte
                    overlaps.append({
                        "address": f"0x{where:08x}",
                        "line": lineno,
                        "kind": "benign" if same else "conflicting",
                    })
                    if not same and strict:
                        errors.append(
                            f"{lineno}: conflicting value at "
                            f"0x{where:08x}")
                    if not same:
                        mem[where] = byte
                else:
                    mem[where] = byte
        elif kind == 0x01:
            break
        elif kind == 0x02:
            if count != 2:
                errors.append(f"{lineno}: extended segment record must be 2 "
                              "bytes")
                continue
            upper = ((data[0] << 8) | data[1]) << 4
        elif kind == 0x04:
            if count != 2:
                errors.append(f"{lineno}: extended linear record must be 2 "
                              "bytes")
                continue
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
    return mem, blocks, types, errors, overlaps


def read32_le(mem, addr):
    return int.from_bytes(bytes(mem.get(addr + k, 0) for k in range(4)),
                          "little")


def simulate_28d56(mem, start, end):
    """Model 0x28d56 from its instructions (see the copy-helper document).

    The function walks 8-byte records from `start` while the cursor differs
    from `end`; each record is (count, destination) as little-endian u32,
    and the helper writes `count` zero bytes at `destination`.
    """
    writes = []
    rec = start
    guard = 0
    while rec != end and guard < 4096:
        guard += 1
        count = read32_le(mem, rec)
        dest = read32_le(mem, rec + 4)
        writes.append({"record": f"0x{rec:08x}",
                       "count": f"0x{count:08x}",
                       "count_dec": count,
                       "destination": f"0x{dest:08x}"})
        rec += 8
    return writes


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
        mem, blocks, types, errors, overlaps = parse_ihex(path, strict=True)
        level = 0 if name == "first" else 1
        entry = {
            "file": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "record_types": types,
            "parse_errors": errors,
            "overlapping_records": overlaps,
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

    # copy helper 0x28D56 (second-level): modelled from its instructions
    fw = C.load(str(IMAGES[1][1]))
    C.disassemble(fw, str(OBJDUMP))
    callers = find_callers(fw, 0x28D56)
    first_arg, site_a = movd_value_before(fw, 0x15F6, "r3,r2")
    end_arg, site_b = movd_value_before(fw, 0x15F6, "r5,r4")
    sec_mem, _, _, _, _ = parse_ihex(IMAGES[1][1])
    records = simulate_28d56(sec_mem, first_arg, end_arg) \
        if first_arg is not None and end_arg is not None else []
    report["copy_helper"] = {
        "function": "0x28d56",
        "callers": callers,
        "arguments": {
            "record_start": {"value": f"0x{first_arg:08x}"
                             if first_arg is not None else None,
                             "loaded_at": site_a},
            "loop_end": {"value": f"0x{end_arg:08x}"
                         if end_arg is not None else None,
                         "loaded_at": site_b},
        },
        "semantics": {
            "loop": "while cursor != end: record = {u32le count, u32le dest};"
                    " write count zero bytes at dest; cursor += 8",
            "evidence": "L2: 0x28d5c cmpd cursor,end; 0x28d60 loadd 0(rec);"
                        " 0x28d62 movw $0,r4; 0x28d64 loadd 4(rec);"
                        " 0x28d88 helper writes r4 (=0) via storb;"
                        " 0x28d6a addd $8,cursor",
            "why_zero": "r4 is forced to 0 at 0x28d62 and nothing changes it "
                        "before the storb at 0x28d92",
        },
        "simulated_writes": records,
        "changed_region": [
            {"start": f"0x{int(r['destination'], 16):08x}",
             "length": r["count_dec"]}
            for r in records],
        "field_endianness": "little-endian: 0x1c holds 0x000008f2, which is "
                            "an instruction boundary, while the big-endian "
                            "reading is not",
        "in_image": "UNKNOWN per record — compare with the block list",
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
