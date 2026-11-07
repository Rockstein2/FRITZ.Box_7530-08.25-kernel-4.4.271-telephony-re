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


def functional_notes(name, rows):
    """Notes that depend on the access sequence, not just the address.

    Each note states what was observed, so a reader can check it.
    """
    notes = []
    if name.startswith("UART_CTRL_REG"):
        reads = [r for r in rows if r["operation"] == "READ"]
        writes = [r for r in rows if r["operation"] == "WRITE"]
        if reads:
            notes.append(f"{len(reads)} read(s) of the control/status word")
        if writes:
            notes.append(f"{len(writes)} read-modify-write(s)")
    if name == "UART_RX_TX_REG":
        notes.append("data register: read and written as a 16-bit word")
    if name.startswith("UART_CLEAR"):
        notes.append("written with a constant 1 to clear a flag")
    if name == "WATCHDOG_REG":
        notes.append("written with 0xff inside a wait loop "
                     "(kicked repeatedly while polling)")
    if name.startswith("RESET_INT_PENDING_REG"):
        notes.append("written with one bit set to clear that pending IRQ")
    if name.startswith("CLK_AMBA_REG") or name.startswith("CLK_PER10"):
        notes.append("clock divider/enable bits")
    if name.startswith("P0_") or name.startswith("P1_") or \
            name.startswith("P2_") or name.startswith("P3_"):
        notes.append("GPIO port direction/mode/data")
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
            if notes and level == "ACCESS_MATCH":
                level = "FUNCTIONAL_REGISTER_MATCH"
            entry["evidence"] = level
            entry["functional_notes"] = notes
        elif entry["low_bit_matches"]:
            # the exact address is absent, but the low 20 bits appear
            # under another high half: that is the aliasing question
            entry["evidence"] = "LOW_BITS_ONLY"
            entry["functional_notes"] = []
        else:
            entry["evidence"] = "NOT_FOUND_IN_OUR_IMAGE"
            entry["functional_notes"] = []
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
