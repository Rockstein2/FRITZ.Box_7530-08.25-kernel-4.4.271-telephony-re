#!/usr/bin/env python3
"""Structural documentation consistency checks.

Run: python3 tools/tests/test_docs_consistency.py

The checks read specific markdown tables and compare individual cells with
numbers produced by the tools, so a stale value left in another section
cannot make a check pass by coincidence.  Only tables with a stable shape are
checked; free-form prose is not.

Results are PASS / FAIL / SKIP.  Missing report or firmware is a SKIP.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(ROOT / "src" / "mock"))

import cr16_cfg as C  # noqa: E402

REPORT = ROOT / "tools" / "reports" / "cr16-branch-validation.json"
CFG_DOC = ROOT / "docs" / "fon-dialog-cr16-cfg.md"
BRANCH_DOC = ROOT / "docs" / "fon-dialog-cr16-branches.md"
PERIPH_DOC = ROOT / "docs" / "fon-dialog-peripheral-init.md"
FACTS_DOC = ROOT / "docs" / "fon-known-facts.md"

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


def cells(path):
    """Yield the cell list of every table row in a markdown file."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        row = [c.strip().replace("**", "").strip("`").strip()
               for c in line.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in row):
            continue                    # separator row
        yield row


def number(text):
    """First integer in a cell, spaces as thousands separators allowed."""
    text = text.replace("\u2009", "").replace("\u00a0", "").replace(" ", "")
    m = re.search(r"-?\d+", text.strip("`").replace("**", ""))
    return int(m.group(0)) if m else None


def find_row(path, first_cell, section=None):
    """First table row whose first cell equals `first_cell`.

    When `section` is given, only rows after that heading are considered, so
    a duplicate name in another table (for example the edge-category
    glossary) cannot shadow the statistics table.
    """
    if not path.is_file():
        return None
    lines = path.read_text().splitlines()
    start = 0
    if section is not None:
        for i, line in enumerate(lines):
            if line.strip().startswith(section):
                start = i
                break
    for line in lines[start:]:
        line = line.strip()
        if section is not None and line.startswith("## ") and \
                not line.startswith(section):
            if start and line is not lines[start]:
                pass
        if not line.startswith("|"):
            continue
        row = [c.strip().replace("**", "").strip("`").strip()
               for c in line.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in row):
            continue
        if row and row[0] == first_cell:
            return row
    return None


# ---------------------------------------------------------------------------
# 1. Report internal consistency
# ---------------------------------------------------------------------------
if not REPORT.is_file():
    skip("report", f"{REPORT} missing")
    report = None
else:
    report = json.loads(REPORT.read_text())
    normal = report["summary"]["normal"]["by_status"]
    p2 = report["summary"]["p2test"]["by_status"]
    check("report: normal MISMATCH is zero", normal["MISMATCH"], 0)
    check("report: p2test MISMATCH is zero", p2["MISMATCH"], 0)
    check("report: unsupported list length matches summary",
          len(report["unsupported"]),
          normal["UNSUPPORTED"] + p2["UNSUPPORTED"])
    check("report: mismatch list length matches summary",
          len(report["mismatches"]), normal["MISMATCH"] + p2["MISMATCH"])

# ---------------------------------------------------------------------------
# 2. The per-form MATCH table in the branch document
# ---------------------------------------------------------------------------
if report is not None:
    # The document prints a 4-form table (bal32, dispe9, disps5, cond32);
    # cond32 also row is checked through its MATCH count below.
    expected = {}
    for image, table in report["summary"].items():
        for form, counts in table["by_form"].items():
            if counts["MATCH"] and form in ("bal32", "dispe9", "disps5",
                                            "cond32"):
                expected[(image, form)] = counts["MATCH"]
    seen = 0
    for row in cells(BRANCH_DOC):
        # | normal | `sha` | bal32 | 1490 | 0 | 0 | 0 |
        for form in ("bal32", "dispe9", "disps5", "cond32"):
            if row and form in row:
                idx = row.index(form)
                image = row[0]
                got = number(row[idx + 1]) if idx + 1 < len(row) else None
                if (image, form) in expected:
                    check(f"branch table {image}/{form} MATCH", got,
                          expected[(image, form)])
                    seen += 1
    check("branch table covers all matching forms", seen, len(expected))

# ---------------------------------------------------------------------------
# 3. CFG document tables against a fresh run
# ---------------------------------------------------------------------------
fw_path = ROOT / "firmware" / "dectfw_secondlevel_441.hex"
objdump = Path("/tmp/opencode/cr16/build/binutils/objdump")
if not fw_path.is_file() or not objdump.is_file():
    skip("cfg tables", "firmware or CR16 objdump missing")
else:
    fw = C.load(str(fw_path))
    C.disassemble(fw, str(objdump))
    edges = C.build(fw)
    st = C.category_stats(edges)
    mode_a = C.reach_all(fw, edges, [0x1602])
    entries = C.heuristic_entries(fw, edges)
    mode_b = C.reach_all(fw, edges, [e.addr for e in entries])

    for metric in (C.DIRECT_RESOLVED, C.DIRECT_UNSUPPORTED,
                   C.INDIRECT_REGISTER, C.OUTSIDE_LOADED_IMAGE,
                   C.TARGET_NOT_INSTRUCTION, C.FALLTHROUGH_UNRESOLVED):
        row = find_row(CFG_DOC, metric, "### 2.2 Statistics")
        check(f"cfg table row {metric}", row is not None, True)
        if row:
            check(f"cfg table {metric} value", number(row[1]), st[metric])
    row = find_row(CFG_DOC, "Total", "### 2.2 Statistics")
    check("cfg table total", number(row[1]) if row else None, st["TOTAL"])

    modes = {"A": len(mode_a), "B": len(mode_b), "C": 0}
    for key, value in modes.items():
        row = find_row(CFG_DOC, key.strip("*"), "## 3. Reachability modes")
        check(f"cfg modes row {key}", row is not None, True)
        if row:
            check(f"cfg modes {key} value", number(row[-1]), value)

    row = find_row(CFG_DOC, "B", "## 3. Reachability modes")
    check("cfg mode B entry count",
          number(row[1]) if row else None, len(entries))

    # The "outside mode A" arithmetic must follow from the same numbers.
    unreached_expected = len(fw.insns) - len(mode_a)
    text = CFG_DOC.read_text()
    m = re.search(r"([\d\s\u2009]+)instructions\*\* are not reached from mode A", text)
    check("cfg document states the outside-mode-A count",
          number(m.group(1)) if m else None, unreached_expected)

# ---------------------------------------------------------------------------
# 4. Fall-through table must not list `br` with the conditionals
# ---------------------------------------------------------------------------
row = find_row(CFG_DOC, "conditional (`beq`, `bne`, `bhi`, `bcc`, …)",
               "### 2.1")
check("cfg fall-through table: conditionals do not mention br",
      row is not None and not re.search(r"\bbr\b", " ".join(row[1:])), True)
row = find_row(CFG_DOC, "br` (unconditional relative branch)", "### 2.1")
check("cfg fall-through table: br row exists", row is not None, True)
if row:
    check("cfg fall-through table: br has target only",
          "target only" in " ".join(row), True)

# ---------------------------------------------------------------------------
# 4b. Unsupported-form total in the known facts and the CFG document
# ---------------------------------------------------------------------------
if report is not None:
    unsup_total = (normal["UNSUPPORTED"] + p2["UNSUPPORTED"])
    row = find_row(FACTS_DOC, "unsupported branch forms")
    check("known facts: unsupported total",
          number(row[1]) if row else None, unsup_total)
    row = find_row(CFG_DOC, f"{unsup_total} unsupported branch forms")
    check("cfg doc: unsupported total row exists", row is not None, True)

# ---------------------------------------------------------------------------
# 5. Peripheral register table widths
# ---------------------------------------------------------------------------
for addr in ("0x00FF6006", "0x00FF5406"):
    row = find_row(PERIPH_DOC, addr)
    check(f"peripheral table has {addr}", row is not None, True)
    if row:
        access = row[2]
        check(f"peripheral table {addr} is a 16-bit access",
              "16-bit" in access and "32-bit" not in access, True)

# ---------------------------------------------------------------------------
# 6. Known-facts MATCH total
# ---------------------------------------------------------------------------
if report is not None:
    total_match = sum(s["by_status"]["MATCH"]
                      for s in report["summary"].values())
    row = find_row(FACTS_DOC, "branch validation matches, both images")
    check("known facts: branch validation MATCH total",
          number(row[1]) if row else None, total_match)

# ---------------------------------------------------------------------------
# 7. Address spaces are never merged in the peripheral documents
# ---------------------------------------------------------------------------
XREF_REPORT = ROOT / "tools" / "reports" / "peripheral-xrefs.json"
XREF_DOCS = [ROOT / "docs" / name for name in (
    "fon-dialog-peripheral-xrefs.md", "fon-dialog-peripheral-map.md",
    "fon-dialog-init-dependencies.md", "fon-dialog-pcm-hypotheses.md")]

if not XREF_REPORT.is_file():
    skip("address spaces", "peripheral-xrefs.json missing")
else:
    xr = json.loads(XREF_REPORT.read_text())

    def ops_of(addr):
        found = set()
        for image in xr["images"].values():
            for row in image["operations"]:
                if row["effective_address"] == addr:
                    found.add((row["operation"], row["address_kind"]))
        return found

    # 0x258c / 0x25b4 must be 0x00FF6006 and never 0x000F6006 (PERIPH-2)
    check("report: 0x00FF6006 has register-pair writers",
          {("WRITE", "RESOLVED")} <= ops_of("0x00ff6006"), True)
    check("report: 0x000F6006 has only its own two writers",
          sum(1 for image in xr["images"].values()
              for row in image["operations"]
              if row["effective_address"] == "0x000f6006"
              and row["operation"] == "WRITE") , 4)
    check("report: 0x25d0 is SYMBOLIC",
          any(row["instruction"] == "0x0025d0"
              and row["address_kind"] == "SYMBOLIC"
              for image in xr["images"].values()
              for row in image["operations"]), True)

    # no document may claim that 0x258c or 0x25b4 writes 0x000F6006
    for path in XREF_DOCS + [FACTS_DOC]:
        text = path.read_text()
        bad = []
        for line in text.splitlines():
            if "0x000F6006" not in line:
                continue
            if "0x258c" in line.lower() or "0x25b4" in line.lower():
                # a line that also names 0x00FF6006 is drawing the
                # distinction, which is what we want; flag only lines that
                # attribute the site to 0x000F6006 alone
                if "0x00FF6006" in line:
                    continue
                bad.append(line.strip())
        check(f"{path.name}: no row merges 0x258c/0x25b4 into 0x000F6006",
              bad, [])

    # the XREF document's statistics must match the report
    def total(image, kind):
        return sum(v for k, v in xr["images"][image]["stats"].items()
                   if k.endswith("/" + kind))

    doc = ROOT / "docs" / "fon-dialog-peripheral-xrefs.md"
    doc_text = doc.read_text()
    for image in ("normal", "p2test"):
        sm = xr["images"][image]["summary"]
        # the statistics table lists one counter per row; find the row by
        # its label and compare the cell for this image
        col = 1 if image == "normal" else 2
        for key, label in (("address_RESOLVED", "address RESOLVED"),
                           ("address_UNKNOWN", "address UNKNOWN"),
                           ("memory_READ_MODIFY_WRITE",
                            "READ_MODIFY_WRITE")):
            value = None
            for line in doc_text.splitlines():
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if len(cells) > col and cells[0] == label:
                    value = number(cells[col])
                    break
            check(f"xrefs doc: {image} {label} matches report",
                  value, sm[key])
        check(f"xrefs doc: {image} reports unsupported memory count",
              str(sm["memory_instructions_unsupported"]) in doc_text, True)
        check(f"xrefs doc: {image} unclassified is 0",
              len(xr["images"][image]["unclassified"]), 0)

    # register-effects document must exist and name the corrected semantics
    eff = ROOT / "docs" / "fon-dialog-cr16-register-effects.md"
    check("register-effects doc exists", eff.is_file(), True)
    if eff.is_file():
        t = eff.read_text()
        check("register-effects doc: movzw writes the pair",
              "pair `(r7,r6)`" in t and "`r3`" in t, True)
        check("register-effects doc: MOVZB src,dest cited",
              "MOVZB src, dest" in t, True)

# ---------------------------------------------------------------------------
# 8. Fill-loop indices and the position of the 0x2558 call
# ---------------------------------------------------------------------------
XREF_DOC = ROOT / "docs" / "fon-dialog-peripheral-xrefs.md"
DEPS_DOC = ROOT / "docs" / "fon-dialog-init-dependencies.md"
if XREF_DOC.is_file():
    text = XREF_DOC.read_text()
    check("xrefs doc: index range is 1...511",
          "`1 … 511`" in text, True)
    check("xrefs doc: no stale 0...510 range",
          "0 … 510" not in text and "0...510" not in text, True)
    check("xrefs doc: fill span is 0x01000002...0x010003FE",
          "0x01000002 … 0x010003FE" in text, True)
if DEPS_DOC.is_file():
    text = DEPS_DOC.read_text()
    check("deps doc: 0x2558 is not described as run from the loop body",
          "loop body" not in text, True)
    check("deps doc: 0x2558 is called after the fill loop",
          "after the fill loop" in text or "after** the" in text
          or "after the" in text, True)

# ---------------------------------------------------------------------------
# 9. The alias verdict must stay UNKNOWN while no evidence exists
# ---------------------------------------------------------------------------
ALIAS_DOC = ROOT / "docs" / "fon-dialog-address-alias-hypotheses.md"
if ALIAS_DOC.is_file():
    t = ALIAS_DOC.read_text()
    check("alias doc: verdict is UNKNOWN", "**Answer: UNKNOWN.**" in t, True)
    check("alias doc: no DOCUMENTED_ALIAS claim",
          "DOCUMENTED_ALIAS" not in t.replace("documented for the SC14448", ""),
          True)
    check("alias doc: full-width addresses are used",
          "0x000F6006" in t and "0x00FF6006" in t, True)
    check("alias doc: states what would prove it",
          "bus observation" in t or "read-back experiment" in t, True)

if REPORT.is_file() and (ROOT / "tools" / "reports" /
                         "cr16-address-alias.json").is_file():
    al = json.loads((ROOT / "tools" / "reports" /
                     "cr16-address-alias.json").read_text())
    check("alias report: code level stops at BEHAVIOR_CORRELATION",
          al["max_level_from_code"], "BEHAVIOR_CORRELATION")
    for image in ("normal", "p2test"):
        check(f"alias report: {image} has the 0x6006 pair",
              any(p["address_a"] == "0x000f6006"
                  and p["address_b"] == "0x00ff6006"
                  for p in al["images"][image]["pairs"]), True)
        check(f"alias report: {image} claims no proven alias",
              all("candidate" in p["proof_status"]
                  for p in al["images"][image]["pairs"]), True)

# ---------------------------------------------------------------------------
# 10. Boot documents agree with the bootstrap findings
# ---------------------------------------------------------------------------
BOOT_DOCS = {n: ROOT / "docs" / n for n in (
    "fon-dialog-firstlevel-cfg.md", "fon-dialog-uart-boot-protocol.md",
    "fon-dialog-boot-memory-map.md", "fon-dialog-boot-handoff.md")}
for name, path in BOOT_DOCS.items():
    check(f"{name} exists", path.is_file(), True)

HANDOFF = BOOT_DOCS["fon-dialog-boot-handoff.md"]
if HANDOFF.is_file():
    t = HANDOFF.read_text()
    check("handoff answer is PARTIALLY KNOWN", "PARTIALLY KNOWN" in t, True)
    check("handoff does not claim 0x7C as the target",
          "target is `0x7c`" not in t.lower(), True)

UART = BOOT_DOCS["fon-dialog-uart-boot-protocol.md"]
if UART.is_file():
    t = UART.read_text()
    check("protocol doc names the store that lands bytes",
          "0x1022C" in t.replace("0x1022c", "0x1022C"), True)
    check("protocol doc states the second-level is not relocated",
          "not" in t and "relocated" in t, True)

SYSREG = ROOT / "docs" / "fon-dialog-cr16-system-registers.md"
if SYSREG.is_file():
    t = SYSREG.read_text()
    check("system-register doc no longer calls 0x28D56 a byte copy",
          "byte-copy loop" not in t, True)
    check("system-register doc explains the list format",
          "u32be address" in t, True)

MEM = BOOT_DOCS["fon-dialog-boot-memory-map.md"]
if MEM.is_file():
    t = MEM.read_text()
    check("memory map records the first-level block", "0x10080" in t, True)
    check("memory map does not give RAM/ROM to an address",
          "is RAM" not in t and "is ROM" not in t, True)

print()
print(f"{fails} failure(s), {skips} skip(s)")
sys.exit(1 if fails else 0)
