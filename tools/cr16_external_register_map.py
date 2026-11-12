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

TOOL_VERSION = "cr16-external-register-map/2"
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


def reloc_abs20(value):
    """CR16 abs20 ISA expansion (E3.2): values above 0xEFFFF map to
    0xFF0000..0xFFFFFF; this is an ISA rule, not a hardware alias proof."""
    value &= 0xFFFFF
    return value | 0xF00000 if value > 0xEFFFF else value


def architectural_match_status(low_form, ref_addr):
    """Classify a low-20-bit match under the ISA rule only."""
    if 0xF0000 <= low_form <= 0xFFFFF and reloc_abs20(low_form) == ref_addr:
        return "SAME_ARCHITECTURAL_ADDRESS_BY_RELOC_ABS20"
    if low_form == ref_addr:
        return "EXACT_ARCHITECTURAL_ADDRESS"
    return "LOW_BITS_ONLY_NO_ISA_RULE"


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


# Structured evidence.  Each observation names an image, a site, a mnemonic
# and the operands that must be present.  `build()` re-reads the instruction
# at that site and compares; if anything does not match, the entry is
# reported as MANUALLY_CORRELATED (an expert annotation) instead of
# FUNCTIONAL_REGISTER_MATCH (checked by the tool).
MANUAL_EVIDENCE = {
    "UART_CTRL_REG": {
        "our_address": "0x000f4900",
        "observations": [
            {"image": "first", "site": "0x102ac", "mnemonic": "tbit",
             "operands": "$0x6:s,r0",
             "why": "receive status is bit 6, as UART_CTRL_REG_RI"},
            {"image": "first", "site": "0x102da", "mnemonic": "tbit",
             "operands": "$0x5:s,r0",
             "why": "transmit status is bit 5, as UART_CTRL_REG_TI"},
            {"image": "first", "site": "0x100ee", "mnemonic": "orw",
             "operands": "$0xc:s,r0",
             "why": "baud field bits 2-4 set to 3 (115200)"},
        ],
    },
    "UART_RX_TX_REG": {
        "our_address": "0x000f4902",
        "observations": [
            {"image": "first", "site": "0x102be", "mnemonic": "loadw",
             "operands": "0xf4902:m,r2",
             "why": "read returns the received byte"},
            {"image": "first", "site": "0x102ce", "mnemonic": "storw",
             "operands": "r2,0xf4902:m",
             "why": "write sends a byte"},
        ],
    },
    "UART_CLEAR_RX_INT_REG": {
        "our_address": "0x000f4906",
        "observations": [
            {"image": "first", "site": "0x102ba", "mnemonic": "storw",
             "operands": "$0x1:s,0xf4906:m",
             "why": "a write of 1 clears the receive flag"},
        ],
    },
    "UART_CLEAR_TX_INT_REG": {
        "our_address": "0x000f4904",
        "observations": [
            {"image": "first", "site": "0x102e4", "mnemonic": "storw",
             "operands": "$0x1:s,0xf4904:m",
             "why": "a write of 1 clears the transmit flag"},
        ],
    },
    "WATCHDOG_REG": {
        "our_address": "0x000f4c00",
        "expected_value": "0xff",
        "value_from_low_bits": "0x000f4c00",
        "observations": [
            {"image": "normal", "site": "0x28820", "mnemonic": "storw",
             "operands": "r0,0xf4c00:m",
             "why": "written with 0xff from the immediate tracked in the "
                    "block"},
        ],
        "width_note": "our 0x00ff4c00 uses storb (8-bit) and 0x000f4c00 "
                      "uses storw (16-bit); the value 0xff is the same, the "
                      "width is not",
    },
}


def written_constants(rows):
    """Immediate values our code stores, as seen in the report."""
    return [r["immediate"] for r in rows
            if r["operation"] in ("WRITE", "RMW") and r.get("immediate")]


def verify_observations(observations, firmware):
    """Re-read each named instruction; return (ok, [problems])."""
    problems = []
    for obs in observations:
        fw = firmware.get(obs["image"])
        if fw is None:
            problems.append(f"{obs['site']}: image {obs['image']} not loaded")
            continue
        addr = int(obs["site"], 16)
        insn = fw.insns.get(addr)
        if insn is None:
            problems.append(f"{obs['site']}: no instruction at that address")
            continue
        if insn.mnemonic != obs["mnemonic"]:
            problems.append(f"{obs['site']}: mnemonic is {insn.mnemonic}, "
                            f"expected {obs['mnemonic']}")
            continue
        want = obs["operands"].replace(" ", "")
        have = insn.operands.replace(" ", "")
        if have != want:
            problems.append(f"{obs['site']}: operands are {have!r}, "
                            f"expected {want!r}")
    return not problems, problems


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


def load_firmware():
    """Load and disassemble every image whose observations may be checked."""
    if not OBJDUMP.is_file():
        return {}
    sys.path.insert(0, str(ROOT / "src" / "mock"))
    import cr16_cfg as C
    out = {}
    for name, path in (("first", FIRST_LEVEL),
                       ("normal", ROOT / "firmware" /
                        "dectfw_secondlevel_441.hex"),
                       ("p2test", ROOT / "firmware" /
                        "dectfw_secondlevel_441p2test.hex")):
        if path.is_file():
            fw = C.load(str(path))
            C.disassemble(fw, str(OBJDUMP))
            out[name] = fw
    return out


def build(device_dir, xref_path, firmware=None):
    if not xref_path.is_file():
        return None
    if firmware is None:
        firmware = load_firmware()
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
                "architectural_status": architectural_match_status(a, addr),
                "accesses": {
                    image: [{"instruction": r["instruction"],
                             "operation": r["operation"],
                             "width_bits": r["width_bits"]}
                            for r in rows]
                    for image, rows in ours[a].items()}}
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
            entry["manual_verification"] = manual
            entry["functional_notes"] = notes
            entry["evidence"] = level
            if manual:
                ok, problems = verify_observations(
                    manual.get("observations", []), firmware)
                values_ok = True
                if manual.get("expected_value"):
                    consts = written_constants(all_rows)
                    alt = manual.get("value_from_low_bits")
                    if alt:
                        for a, by_image in ours.items():
                            if f"0x{a:08x}" == alt:
                                consts += written_constants(
                                    [r for rows in by_image.values()
                                     for r in rows])
                    expected = manual["expected_value"]
                    values_ok = expected in consts
                    entry["functional_notes"].append(
                        f"written value {expected} "
                        f"{'matches' if values_ok else 'does not match'}; "
                        f"observed {sorted(set(consts))}")
                entry["observation_check"] = {
                    "instructions_verified": ok,
                    "problems": problems,
                }
                if ok and values_ok:
                    entry["evidence"] = "FUNCTIONAL_REGISTER_MATCH"
                else:
                    entry["evidence"] = "MANUALLY_CORRELATED"
                    entry["functional_notes"].append(
                        "the annotation is not confirmed by the instructions "
                        "at the named sites, so the automatic level is not "
                        "granted")
        elif entry["low_bit_matches"]:
            # the exact address is absent, but the low 20 bits appear under
            # another high half: that is the aliasing question
            manual = MANUAL_EVIDENCE.get(d["name"])
            entry["manual_verification"] = manual
            if manual:
                ok, problems = verify_observations(
                    manual.get("observations", []), firmware)
                values_ok = True
                if manual.get("expected_value"):
                    consts = written_constants(rows)
                    alt = manual.get("value_from_low_bits")
                    if alt:
                        for a, by_image in ours.items():
                            if f"0x{a:08x}" == alt:
                                consts += written_constants(
                                    [r for rows in by_image.values()
                                     for r in rows])
                    values_ok = manual["expected_value"] in consts
                entry["observation_check"] = {
                    "instructions_verified": ok, "problems": problems}
                entry["functional_notes"] = [o["why"] for o in
                                             manual.get("observations", [])]
                entry["evidence"] = ("FUNCTIONAL_REGISTER_MATCH"
                                     if ok and values_ok
                                     else "MANUALLY_CORRELATED")
            else:
                entry["evidence"] = "LOW_BITS_ONLY"
                entry["functional_notes"] = []
                entry["observation_check"] = None
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
        "alias_conclusion": "UNKNOWN — no hardware evidence. A low-20-bit "
                            "match against an abs20-encoded site is the "
                            "SAME ARCHITECTURAL ADDRESS by the RELOC_ABS20 "
                            "ISA rule (E3.2: encoded 0xFxxxx expands to "
                            "effective 0x00FFxxxx); the physical SC14448 "
                            "register identity stays CANDIDATE",
        "alias_conclusion_isa_rule": "PROVEN_BY_ISA_IMPLEMENTATIONS",
        "alias_conclusion_physical": "UNKNOWN_NO_HARDWARE_EVIDENCE",
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
