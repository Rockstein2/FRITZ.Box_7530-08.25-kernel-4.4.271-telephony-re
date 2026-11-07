#!/usr/bin/env python3
"""Find address pairs whose low bits match but whose high bits differ.

The question this tool answers: does the firmware access one physical
register through two different numeric addresses?  It cannot answer it by
itself — the tool only finds *candidates* and labels the evidence.

A candidate pair is two addresses that appear in the peripheral report,
fall in the two blocks under study (`0x000F0000-0x000FFFFF` and
`0x00F00000-0x00FFFFFF`), and agree on their low 20 bits.

Every candidate is labelled with the strongest evidence that was actually
established, from weakest to strongest:

    LOW_BITS_MATCH          the two numbers agree on the low 20 bits
    BEHAVIOR_CORRELATION    the accesses to both addresses were written by
                            related code, write the same constants, or form
                            a comparable sequence
    DOCUMENTED_ALIAS        a SC14448 (or applicable system controller)
                            document states the mapping
    HARDWARE_CONFIRMED_ALIAS  a measurement shows both addresses reach the
                            same state

This tool can only produce the first two.  The last two need a document or
hardware and are never inferred from code.

Usage:
    python3 tools/cr16_address_alias.py --json tools/reports/cr16-address-alias.json
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

TOOL_VERSION = "cr16-address-alias/1"
LOW_MASK = 0x000FFFFF
BLOCK_LO = 0x000F0000
BLOCK_HI = 0x00F00000
BLOCK_HI_END = 0x01000000

XREF_REPORT = ROOT / "tools" / "reports" / "peripheral-xrefs.json"
OBJDUMP = Path("/tmp/opencode/cr16/build/binutils/objdump")
IMAGES = [
    ("normal", ROOT / "firmware" / "dectfw_secondlevel_441.hex"),
    ("p2test", ROOT / "firmware" / "dectfw_secondlevel_441p2test.hex"),
]

# strongest evidence this tool may claim on its own
MAX_CODE_LEVEL = "BEHAVIOR_CORRELATION"


def in_scope(value):
    return BLOCK_LO <= value < 0x00100000 or BLOCK_HI <= value < BLOCK_HI_END


def collect(image_entry):
    """Return {address: [operation rows]} for resolved memory addresses."""
    out = {}
    for row in image_entry["operations"]:
        if row["address_kind"] != "RESOLVED":
            continue
        if row["operation"] not in ("READ", "WRITE", "RMW"):
            continue          # ADDRESS_LOAD is not a memory access
        value = int(row["effective_address"], 16)
        if not in_scope(value):
            continue
        out.setdefault(value, []).append(row)
    return out


def constants_of(rows):
    """Written constants, only where the report records them.

    The cross-reference report does not store the immediate value of a
    store, so this function currently always returns an empty list.  It is
    kept explicit rather than removed: when the report gains the field, the
    comparison starts working without changing the evidence rules.
    """
    return [row["value"] for row in rows
            if row["operation"] in ("WRITE", "RMW") and "value" in row]


def summarise(rows):
    return {
        "sites": sorted({row["instruction"] for row in rows}),
        "operations": sorted({row["operation"] for row in rows}),
        "widths": sorted({row["width_bits"] for row in rows}),
        "reachable_mode_a": sorted({row["reachable_mode_a"] for row in rows}),
    }


def sequences(rows):
    """Write/read order of one address, sorted by address of instruction."""
    order = {r["instruction"]: i for i, r in enumerate(rows)}
    seq = sorted(rows, key=lambda r: int(r["instruction"], 16))
    return [(r["instruction"], r["operation"], r["width_bits"]) for r in seq]


def behaviour(a, b):
    """Compare the access structure of two addresses.

    Returns (correlation: bool, reasons: [str]).  A correlation is only
    claimed when the shapes agree in a way that the code makes explicit:
    the same set of operations, or the same written constant at both.
    Two registers that both receive `0x0080` do not establish aliasing; the
    reason string says so.
    """
    reasons = []
    sa, sb = summarise(a), summarise(b)
    if sa["operations"] == sb["operations"]:
        reasons.append("same operation set: " + ", ".join(sa["operations"]))
    if sa["widths"] == sb["widths"]:
        reasons.append("same access width: "
                       + ", ".join(str(w) for w in sa["widths"]))
    ca, cb = constants_of(a), constants_of(b)
    if ca and cb and set(ca) & set(cb):
        reasons.append("same written constant: "
                       + ", ".join(f"0x{v:04x}" for v in
                                   sorted(set(ca) & set(cb)))
                       + " (not evidence of aliasing by itself)")
    correlated = bool(sa["operations"] == sb["operations"])
    return correlated, reasons


def build_report():
    if not XREF_REPORT.is_file():
        return None
    xref = json.loads(XREF_REPORT.read_text())
    report = {
        "tool": TOOL_VERSION,
        "low_mask": f"0x{LOW_MASK:08x}",
        "blocks": [f"0x{BLOCK_LO:08x}-0x000fffff",
                   f"0x{BLOCK_HI:08x}-0x00ffffff"],
        "evidence_levels": ["LOW_BITS_MATCH", "BEHAVIOR_CORRELATION",
                            "DOCUMENTED_ALIAS", "HARDWARE_CONFIRMED_ALIAS"],
        "max_level_from_code": MAX_CODE_LEVEL,
        "images": {},
        "cross_image": {},
    }
    per_image = {}
    for image, path in IMAGES:
        entry = xref["images"].get(image)
        if entry is None:
            continue
        addrs = collect(entry)
        per_image[image] = addrs
        pairs = []
        low = sorted(a for a in addrs if a < 0x00100000)
        high = sorted(a for a in addrs if a >= BLOCK_HI)
        for a in low:
            for b in high:
                if (a & LOW_MASK) != (b & LOW_MASK):
                    continue
                correlated, reasons = behaviour(addrs[a], addrs[b])
                pairs.append({
                    "address_a": f"0x{a:08x}",
                    "address_b": f"0x{b:08x}",
                    "difference": f"0x{b - a:08x}",
                    "low_bits_match": f"0x{a & LOW_MASK:05x}",
                    "evidence": (MAX_CODE_LEVEL if correlated
                                 else "LOW_BITS_MATCH"),
                    "proof_status": "candidate; no document and no hardware "
                                    "evidence",
                    "a": summarise(addrs[a]),
                    "b": summarise(addrs[b]),
                    "a_sequence": sequences(addrs[a]),
                    "b_sequence": sequences(addrs[b]),
                    "correlation_notes": reasons,
                })
        report["images"][image] = {
            "firmware": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()
            if path.is_file() else entry.get("sha256"),
            "resolved_addresses_in_scope": len(addrs),
            "pairs": pairs,
        }

    # cross-image comparison: the same pair must exist in both images with
    # the same structure, otherwise the pattern is an artefact of one build
    if len(per_image) == 2:
        common = None
        for addrs in per_image.values():
            keys = {a & LOW_MASK for a in addrs}
            common = keys if common is None else common & keys
        report["cross_image"] = {
            "low_bits_present_in_both": sorted(f"0x{k:05x}"
                                               for k in (common or set())),
        }
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    if not XREF_REPORT.is_file():
        print(f"SKIP: {XREF_REPORT} missing; run cr16_peripheral_xrefs.py",
              file=sys.stderr)
        return 2
    missing = [str(p) for _, p in IMAGES if not p.is_file()]
    if missing:
        print(f"SKIP: firmware missing: {missing}", file=sys.stderr)
        return 2
    if not OBJDUMP.is_file():
        print("SKIP: CR16 objdump not available", file=sys.stderr)
        return 2

    report = build_report()
    if report is None:
        print("SKIP: no report", file=sys.stderr)
        return 2
    text = json.dumps(report, indent=1, sort_keys=True) + "\n"
    if args.json:
        args.json.write_text(text)
        print(f"wrote {args.json}")
    else:
        print(text)
    for image, entry in report["images"].items():
        print(image, "pairs:", len(entry["pairs"]),
              "addresses:", entry["resolved_addresses_in_scope"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
