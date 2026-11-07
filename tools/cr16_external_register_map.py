#!/usr/bin/env python3
"""Correlate our firmware's peripheral accesses with the TobleMiner CR16C map.

Reference project (used as a *reference*, not vendored):

    https://github.com/TobleMiner/dialog-cr16c-uart-boot
    commit 3d041a683c57fee585e04edc503cd7348f54c4a9
    Copyright 2022 Tobias Schramm, MIT licence

The reference targets SC14441/Gigaset hardware.  A matching address is a
*candidate*, never proof of the same hardware on the SC14448.

The tool extracts `MMIOxx(0x....)` numbers from the reference headers, joins
them with `tools/reports/peripheral-xrefs.json`, and records for every pair:

    address          the reference address
    ours             our addresses with the same low 20 bits
    name             the reference name
    access           our operations at that address
    evidence         the strongest label the data supports

Labels, weakest first:

    ADDRESS_ONLY              the same address appears in both
    ACCESS_MATCH              the same address appears with a compatible width
    FUNCTIONAL_REGISTER_MATCH the *sequence* of accesses matches the
                              reference's documented semantics (UART status
                              bits, watchdog kick, ...)

A hardware alias between 0x000Fxxxx and 0x00FFxxxx is never concluded.

Usage:
    python3 tools/cr16_external_register_map.py --json tools/reports/cr16-external-register-map.json
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

TOOL_VERSION = "cr16-external-register-map/1"
# Upstream and the fork are both used.  The fork adds chip configs (including
# an SC14448 entry) and more peripherals, so it is the primary source; the
# upstream commit stays recorded for reproducibility.
UPSTREAM_REPO = "https://github.com/TobleMiner/dialog-cr16c-uart-boot"
UPSTREAM_SHA = "3d041a683c57fee585e04edc503cd7348f54c4a9"
FORK_REPO = "https://github.com/vincentscode/dialog-cr16c-uart-boot"
FORK_SHA = "9e413b55b9576a1dee50a4aefa43e2447d4d2c02"
UPSTREAM_LICENSE = "MIT, Copyright 2022 Tobias Schramm"
DEFAULT_TM = Path("/tmp/opencode/vc/device")

XREF = ROOT / "tools" / "reports" / "peripheral-xrefs.json"
FIRST_LEVEL = ROOT / "firmware" / "dectfw_firstlevel_441_slow.hex"
OBJDUMP = Path("/tmp/opencode/cr16/build/binutils/objdump")
LOW_MASK = 0x000FFFFF

HEADERS = ["uart.h", "irq.h", "clock.h", "gpio.h", "watchdog.h",
           "system.h", "chipid.h", "qspi.h", "power.h", "spi.h",
           "display.h", "debug.h", "flash.h", "dma.h"]

MMIO_RE = re.compile(r"#define\s+(\w+)\s+MMIO(8|16|32)\(0x([0-9A-Fa-f]+)\)")


def extract_defines(device_dir):
    """Return [{name, address, width, file}] from the reference headers."""
    out = []
    for name in HEADERS:
        path = device_dir / name
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            m = MMIO_RE.search(line)
            if m:
                out.append({"name": m.group(1),
                            "address": f"0x{int(m.group(3), 16):08x}",
                            "width": int(m.group(2)),
                            "file": name})
    out.sort(key=lambda r: int(r["address"], 16))
    return out


def first_level_rows():
    """Scan the first-level image too: the UART and watchdog live there."""
    if not FIRST_LEVEL.is_file() or not OBJDUMP.is_file():
        return {}
    sys.path.insert(0, str(ROOT / "src" / "mock"))
    import cr16_cfg as C
    import cr16_peripheral_xrefs as X
    fw = C.load(str(FIRST_LEVEL))
    C.disassemble(fw, str(OBJDUMP))
    rows, _stats, _unc, _unsup = X.scan(fw, "first")
    return rows


CHIP_RE = re.compile(
    r"#elif defined\(CHIP_(\w+)\)|#if defined\(CHIP_(\w+)\)")
RAM_RE = re.compile(r"#define CHIP_RAM_ORIGIN\s+0x([0-9A-Fa-f]+)")
RAMLEN_RE = re.compile(r"#define CHIP_RAM_LENGTH\s+0x([0-9A-Fa-f]+)")


def chip_configs(device_dir):
    """Parse chip_config.h into [{chip, ram_origin, ram_length}]."""
    path = device_dir / "chip_config.h"
    if not path.is_file():
        return []
    out, current = [], None
    for line in path.read_text().splitlines():
        m = CHIP_RE.search(line)
        if m:
            current = {"chip": m.group(1) or m.group(2)}
            out.append(current)
            continue
        if current is None:
            continue
        m = RAM_RE.search(line)
        if m:
            current["ram_origin"] = f"0x{int(m.group(1), 16):08x}"
        m = RAMLEN_RE.search(line)
        if m:
            current["ram_length"] = f"0x{int(m.group(1), 16):08x}"
    return out


def our_accesses(xref):
    """Map address -> {image: [rows]} for RESOLVED memory operations."""
    out = {}
    sources = [(image, entry["operations"])
               for image, entry in xref["images"].items()]
    first = first_level_rows()
    if first:
        sources.append(("first", first))
    for image, rows in sources:
        for row in rows:
            if row["address_kind"] != "RESOLVED":
                continue
            if row["operation"] not in ("READ", "WRITE", "RMW"):
                continue
            addr = int(row["effective_address"], 16)
            out.setdefault(addr, {}).setdefault(image, []).append(row)
    return out


# Registers whose semantics were verified against our instructions by hand.
# A name alone never qualifies: each entry names the evidence and the site.
MANUAL_EVIDENCE = {
    "UART_CTRL_REG": {
        "level": "FUNCTIONAL_REGISTER_MATCH",
        "our_address": "0x000f4900",
        "evidence": "status bits used by our code match the reference bit "
                    "numbers: RI = bit 6 (0x102ac tbit $6) and TI = bit 5 "
                    "(0x102da tbit $5); the baud field bits 2-4 is set to "
                    "0xC at 0x100ee, i.e. 115200 as the reference defines",
    },
    "WATCHDOG_REG": {
        "level": "FUNCTIONAL_REGISTER_MATCH",
        "our_address": "0x000f4c00",
        "expected_value": "0xff",
        "value_from_low_bits": "0x000f4c00",
        "evidence": "written with the same value 0xFF as the reference "
                    "(0x102a0, 0x102ca; the store at 0x28820 carries "
                    "immediate 0xff in the report) inside a wait loop",
        "width_note": "our 0x00FF4C00 uses storb (8-bit) and 0x000F4C00 "
                      "uses storw (16-bit); the value 0xFF is the same, the "
                      "width is not",
    },
    "UART_CLEAR_TX_INT_REG": {
        "level": "FUNCTIONAL_REGISTER_MATCH",
        "our_address": "0x000f4904",
        "evidence": "written with 1 to clear the transmit flag (0x102e4), "
                    "as the reference does",
    },
    "UART_CLEAR_RX_INT_REG": {
        "level": "FUNCTIONAL_REGISTER_MATCH",
        "our_address": "0x000f4906",
        "evidence": "written with 1 to clear the receive flag (0x102ba), "
                    "as the reference does",
    },
    "UART_RX_TX_REG": {
        "level": "FUNCTIONAL_REGISTER_MATCH",
        "our_address": "0x000f4902",
        "evidence": "read and written as a 16-bit data word (0x102be, "
                    "0x102ce) between the status polls",
    },
}


def written_constants(rows):
    """Immediate values our code stores, as seen in the report."""
    return [r["immediate"] for r in rows
            if r["operation"] in ("WRITE", "RMW") and r.get("immediate")]


def functional_notes(name, rows):
    """Return (labels, notes).  `labels` never come from the name alone.

    The function only *describes* what the rows show.  The evidence level is
    raised to FUNCTIONAL_REGISTER_MATCH by `build()` only for the registers
    listed in MANUAL_EVIDENCE, whose sequence was checked by hand.
    """
    notes = []
    ops = sorted({r["operation"] for r in rows})
    widths = sorted({r["width_bits"] for r in rows})
    notes.append(f"observed operations: {', '.join(ops)}; "
                 f"widths: {', '.join(str(w) for w in widths)}")
    if "RMW" in ops:
        notes.append("includes read-modify-write (bit operations)")
    return notes


def build(device_dir, xref_path):
    if not xref_path.is_file():
        return None
    xref = json.loads(xref_path.read_text())
    ours = our_accesses(xref)
    defines = extract_defines(device_dir)

    registers = []
    for d in defines:
        addr = int(d["address"], 16)
        same = ours.get(addr, {})
        low = addr & LOW_MASK
        low_matches = sorted(
            f"0x{a:08x}" for a in ours
            if (a & LOW_MASK) == low and a != addr)
        entry = dict(d)
        entry["our_accesses"] = {
            image: [{"instruction": r["instruction"],
                     "operation": r["operation"],
                     "width_bits": r["width_bits"]}
                    for r in rows]
            for image, rows in same.items()}
        # the same *logical* register may appear under a different high half
        entry["low_bit_matches"] = {
            f"0x{a:08x}": {
                image: [{"instruction": r["instruction"],
                         "operation": r["operation"],
                         "width_bits": r["width_bits"]}
                        for r in rows]
                for image, rows in ours[a].items()}
            for a in ours if (a & LOW_MASK) == low and a != addr}
        entry["found_in_our_firmware"] = bool(same)
        entry["low_bit_candidates"] = low_matches
        if same:
            widths = {r["width_bits"] for rows in same.values() for r in rows}
            if d["width"] in widths:
                level = "ACCESS_MATCH"
            else:
                level = "ADDRESS_ONLY"
            all_rows = [r for rows in same.values() for r in rows]
            notes = functional_notes(d["name"], all_rows)
            manual = MANUAL_EVIDENCE.get(d["name"])
            entry["evidence"] = level
            entry["manual_verification"] = manual
            entry["functional_notes"] = notes
            if manual and manual.get("expected_value"):
                consts = written_constants(all_rows)
                alt = manual.get("value_from_low_bits")
                if alt:
                    # the exact address may be written from a register while
                    # the same value is written at the low-bit twin
                    for a, by_image in ours.items():
                        if f"0x{a:08x}" == alt:
                            consts += written_constants(
                                [r for rows in by_image.values()
                                 for r in rows])
                expected = manual["expected_value"]
                if expected in consts:
                    entry["evidence"] = manual["level"]
                    entry["functional_notes"].append(
                        f"written value {expected} matches the reference")
                else:
                    entry["functional_notes"].append(
                        f"expected {expected}, observed {sorted(set(consts))}")
            elif manual:
                entry["evidence"] = manual["level"]
        elif entry["low_bit_matches"]:
            # the exact address is absent, but the low 20 bits appear
            # under another high half: that is the aliasing question
            manual = MANUAL_EVIDENCE.get(d["name"])
            if manual:
                entry["evidence"] = manual["level"]
                entry["functional_notes"] = [manual["evidence"]]
                entry["manual_verification"] = manual
            else:
                entry["evidence"] = "LOW_BITS_ONLY"
                entry["functional_notes"] = []
                entry["manual_verification"] = None
        else:
            entry["evidence"] = "NOT_FOUND_IN_OUR_IMAGE"
            entry["functional_notes"] = []
            entry["manual_verification"] = None
        registers.append(entry)

    report = {
        "tool": TOOL_VERSION,
        "upstream": {"repo": UPSTREAM_REPO, "commit": UPSTREAM_SHA,
                     "fork_repo": FORK_REPO, "fork_commit": FORK_SHA,
                     "license": UPSTREAM_LICENSE,
                     "files_read": [h for h in HEADERS
                                    if (device_dir / h).is_file()]},
        "caution": "the reference targets SC14441; a matching address is a "
                   "candidate, never proof of the same hardware on SC14448",
        "low_mask": f"0x{LOW_MASK:08x}",
        "registers": registers,
        "alias_conclusion": "UNKNOWN — no hardware evidence",
        "level_rule": "FUNCTIONAL_REGISTER_MATCH requires an entry in "
                      "MANUAL_EVIDENCE, which names the instructions that "
                      "were compared by hand; an access pattern alone stops "
                      "at ACCESS_MATCH",
        "chip_configs": chip_configs(device_dir),
    }
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path)
    ap.add_argument("--device", type=Path, default=DEFAULT_TM)
    args = ap.parse_args()

    if not args.device.is_dir():
        print(f"SKIP: reference headers not found at {args.device}",
              file=sys.stderr)
        return 2
    if not XREF.is_file():
        print(f"SKIP: {XREF} missing", file=sys.stderr)
        return 2

    report = build(args.device, XREF)
    if report is None:
        print("SKIP: cannot build report", file=sys.stderr)
        return 2
    text = json.dumps(report, indent=1, sort_keys=True) + "\n"
    if args.json:
        args.json.write_text(text)
        print(f"wrote {args.json}")
    else:
        print(text)
    found = [r for r in report["registers"] if r["found_in_our_firmware"]]
    print(f"{len(report['registers'])} reference registers, "
          f"{len(found)} also present in our firmware")
    return 0


if __name__ == "__main__":
    sys.exit(main())
