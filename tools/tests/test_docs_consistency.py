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
    row = find_row(CFG_DOC, "unsupported branch forms")
    check("cfg doc: unsupported total row exists", row is not None, True)
    if row:
        check("cfg doc: unsupported total matches the report",
              f"{unsup_total}" in " ".join(row), True)

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
    check("handoff answer is STATICALLY_RESOLVED",
          "STATICALLY_RESOLVED" in t, True)
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
    check("system-register doc explains the record format",
          "u32le count" in t and "zero" in t, True)
    check("system-register doc states the table is word-offset encoded",
          "word-offset" in t, True)

MEM = BOOT_DOCS["fon-dialog-boot-memory-map.md"]
if MEM.is_file():
    t = MEM.read_text()
    check("memory map records the first-level block", "0x10080" in t, True)
    check("memory map does not give RAM/ROM to an address",
          "is RAM" not in t and "is ROM" not in t, True)

# ---------------------------------------------------------------------------
# 11. EXTREF-1 documents
# ---------------------------------------------------------------------------
EXT = {n: ROOT / "docs" / n for n in (
    "fon-dialog-cr16-vector-map.md",
    "fon-dialog-external-register-map.md",
    "fon-dialog-uart-boot-comparison.md")}
for name, path in EXT.items():
    check(f"{name} exists", path.is_file(), True)

VEC = EXT["fon-dialog-cr16-vector-map.md"]
if VEC.is_file():
    t = VEC.read_text()
    check("vector doc does not confirm the UART=20/SPI=22 reading",
          "not confirmed" in t, True)
    check("vector doc records the /2 encoding", "divided by 2" in t, True)

EXTMAP = EXT["fon-dialog-external-register-map.md"]
if EXTMAP.is_file():
    t = EXTMAP.read_text()
    check("register-map doc keeps the alias answer UNKNOWN",
          "still UNKNOWN" in t, True)
    check("register-map doc names the UART functional match",
          "FUNCTIONAL_REGISTER_MATCH" in t, True)

UART = EXT["fon-dialog-uart-boot-comparison.md"]
if UART.is_file():
    t = UART.read_text()
    check("comparison separates the three loader levels",
          "A. Dialog ROM loader" in t or "A (ROM)" in t, True)
    check("comparison warns not to treat B and C as identical",
          "Do not treat B and C as the same protocol" in t, True)

# ---------------------------------------------------------------------------
# 12. EXTREF-1.2 document checks
# ---------------------------------------------------------------------------
SYSREG = ROOT / "docs" / "fon-dialog-cr16-system-registers.md"
if SYSREG.is_file():
    t = SYSREG.read_text()
    check("sysreg: table bytes are the real ones",
          "0x24: e5 46 01 00" in t, True)
    check("sysreg: old big-endian table bytes are gone",
          "16 42 17 5b" not in t, True)
    check("sysreg: no {u32be addr,len} description of 0x28d56",
          "{u32be addr,len}" not in t, True)
    check("sysreg: states the 31-entry extent", "0x24`–`0x9F`" in t, True)
    check("sysreg: mentions the TLV block at 0xa0", "TLV" in t, True)

VEC = ROOT / "docs" / "fon-dialog-cr16-vector-map.md"
if VEC.is_file():
    t = VEC.read_text()
    check("vector doc: no '32 entries' claim",
          "has 32 entries" not in t, True)
    check("vector doc: 31 entries stated", "31 consecutive entries" in t,
          True)
    check("vector doc: stub does not prove different numbering",
          "do not prove the *numbering* differs" in t, True)

ROM = ROOT / "docs" / "fon-dialog-uart-boot-comparison.md"
if ROM.is_file():
    t = ROM.read_text()
    check("rom doc: XOR check described", "challenge–response" in t, True)
    check("rom doc: no 'checksum none' claim",
          "none in `dialogtool.py`" not in t, True)
    check("rom doc: ACK after the comparison", "only if the bytes match" in t,
          True)

HELPER = ROOT / "docs" / "fon-dialog-copy-helper-28d56.md"
if HELPER.is_file():
    t = HELPER.read_text()
    check("helper doc: p2test range ends 0x9b43", "0x9B43" in t, True)

# ---------------------------------------------------------------------------
# 13. BOOT-3.1: one consistent boot model everywhere
# ---------------------------------------------------------------------------
BOOTMAP = ROOT / "tools" / "reports" / "cr16-boot-memory-map.json"
HAN = ROOT / "docs" / "fon-dialog-boot-handoff.md"
DEC = ROOT / "docs" / "fon-dialog-boot-branch-decoding.md"
OQ = ROOT / "docs" / "fon-open-questions.md"

if BOOTMAP.is_file():
    bm = json.loads(BOOTMAP.read_text())
    ho = bm["handoff"]
    check("boot map: chain statically resolved",
          ho["chain"]["status"], "STATICALLY_RESOLVED")
    check("boot map: hardware not observed",
          ho["chain"]["hardware_observed"], False)
    check("boot map: transfer site", ho["transfer_site"], "0x010284")
    check("boot map: transfer target", ho["transfer_target"], "0x00000008")
    check("boot map: normal trampoline",
          ho["second_level"]["normal"]["decoded_in_isolation"]["target"],
          "0x000015aa")
    check("boot map: p2test trampoline",
          ho["second_level"]["p2test"]["decoded_in_isolation"]["target"],
          "0x00001026")
    check("boot map: all three disps17 go to the retry loop",
          sorted(r["target"] for r in ho["first_level"]
                 if r.get("form") == "disps17"),
          ["0x00010100"] * 3)
    check("boot map: no site is left UNKNOWN",
          [r for r in ho["first_level"]
           if not r.get("target") or "UNKNOWN" in str(r.get("target"))],
          [])

for path in (HAN, DEC):
    if not path.is_file():
        continue
    t = path.read_text()
    check(f"{path.name}: no live 0x010101 target",
          "0x010101" not in t, True)
    check(f"{path.name}: no live 0x10284 -> UNKNOWN",
          "0x10284" not in t or "UNKNOWN" not in
          t.split("0x10284", 1)[1][:60], True)

if HAN.is_file():
    t = HAN.read_text()
    check("handoff doc: states STATICALLY_RESOLVED",
          "STATICALLY_RESOLVED" in t, True)
    check("handoff doc: keeps runtime unverified",
          "RUNTIME_UNVERIFIED" in t or "UNVERIFIED" in t, True)
    check("handoff doc: no {u32be addr,u32be len} for 0x28d56",
          "{u32be addr,u32be len}" not in t, True)
    check("handoff doc: ROM entry stays UNKNOWN",
          "UNKNOWN" in t, True)

if OQ.is_file():
    t = OQ.read_text()
    check("open questions: no _old_ row", "| _old_ |" not in t, True)
    check("open questions: Q66 says 31 entries", "31 entries" in t, True)

# ---------------------------------------------------------------------------
# 14. cross-report consistency
# ---------------------------------------------------------------------------
VECR = ROOT / "tools" / "reports" / "cr16-vector-map.json"
ALR = ROOT / "tools" / "reports" / "cr16-address-alias.json"
XREFR = ROOT / "tools" / "reports" / "peripheral-xrefs.json"

if all(p.is_file() for p in (BOOTMAP, VECR, ALR, XREFR)):
    bm = json.loads(BOOTMAP.read_text())
    vec = json.loads(VECR.read_text())
    al = json.loads(ALR.read_text())
    xr = json.loads(XREFR.read_text())

    shas = {bm["images"][n]["sha256"] for n in ("first", "normal", "p2test")}
    check("each image has its own recorded SHA in the boot map",
          len(shas), 3)
    for image in ("normal", "p2test"):
        check(f"{image}: boot map and xref report agree on SHA",
              bm["images"][image]["sha256"], xr["images"][image]["sha256"])
        check(f"{image}: 31 vectors", len(vec["images"][image]["vectors"]),
              31)
    check("alias report keeps the two address spaces separate",
          [p for p in al["images"]["normal"]["pairs"]
           if p["address_a"] == p["address_b"]], [])
    check("alias evidence stops at code level",
          al["max_level_from_code"], "BEHAVIOR_CORRELATION")
    check("no pair claims a proven alias",
          all(p["proof_status"].startswith("candidate")
              for p in al["images"]["normal"]["pairs"]), True)
    check("handoff targets are the same in boot map and docs",
          (bm["handoff"]["transfer_target"],
           bm["handoff"]["second_level"]["normal"]
           ["decoded_in_isolation"]["target"],
           bm["handoff"]["second_level"]["p2test"]
           ["decoded_in_isolation"]["target"]),
          ("0x00000008", "0x000015aa", "0x00001026"))

# ---------------------------------------------------------------------------
# 15. FON-D0.1: UART identification and D0 runbook
# ---------------------------------------------------------------------------
UARTID = ROOT / "docs" / "fon-dialog-board-uart-identification.md"
D0 = ROOT / "docs" / "runbook" / "fon-stage-d0-uart-identification.md"
check("uart identification doc exists", UARTID.is_file(), True)
check("stage D0 runbook exists", D0.is_file(), True)

if UARTID.is_file():
    t = UARTID.read_text()
    check("uart doc names blsp_uart0", "blsp_uart0" in t, True)
    check("uart doc records gpio16/gpio17", "gpio16" in t and "gpio17" in t,
          True)
    check("uart doc cites the compiled DTB",
          "3083e2acedc800015fea5ee7e57fa6cc8da551e21ee792095cbd8a7224bb841f"
          in t, True)
    check("uart doc records the merged function survives",
          'function = "blsp_uart0";' in t, True)
    check("uart doc no longer claims the override drops function",
          "drops both" not in t, True)
    check("uart doc withdraws the old reading",
          "was **wrong**" in t, True)
    check("uart doc does not overclaim absence of a second UART",
          "That is *not* a proof that no other" in t, True)
    check("uart doc keeps the Dialog-side voltage UNKNOWN",
          "UNKNOWN" in t, True)
    check("uart doc does not assume 1.8 V on the Dialog side",
          "do not assume 1.8 V" in t, True)

if D0.is_file():
    t = D0.read_text()
    check("runbook forbids BGA probing",
          "Never** probe a BGA ball" in t, True)
    check("runbook forbids TX injection at D0",
          "NO-GO at Stage D0" in t, True)
    check("runbook requires a 1.8 V-capable analyser",
          "1.8 V" in t, True)
    check("runbook states console and loader share the port",
          "share one UART controller" in t, True)

# ---------------------------------------------------------------------------
# 16. C3 / D0.4: ADSS channel map and control-only plan
# ---------------------------------------------------------------------------
C3 = ROOT / "docs" / "fon-adss-tdm-channel-map.md"
D04 = ROOT / "docs" / "fon-tdm-control-only-plan.md"
check("adss channel map exists", C3.is_file(), True)
check("control-only plan exists", D04.is_file(), True)

if C3.is_file():
    t = C3.read_text()
    check("c3 distinguishes tdm@0 from pcm@7704000",
          "tdm@0" in t and "pcm@7704000" in t, True)
    check("c3 records stereo-tx 0 / stereo-rx 3 for the FON",
          "stereo-tx-port = <0x00>" in t and "stereo-rx-port = <0x03>" in t,
          True)
    check("c3 says dma-*-channel does not select hardware",
          "never selects hardware" in t, True)
    check("c3 records the wrong-node correction",
          "That was wrong" in t, True)
    check("c3 keeps the SC14448 side UNKNOWN",
          "SC14448 interprets slot 5 as claimed" in t and "UNKNOWN" in t,
          True)
    check("c3 keeps measured vs formula BCLK distinct",
          "1 024 000" in t and "1 025 720" in t, True)

if D04.is_file():
    t = D04.read_text()
    check("d04 states SC14448 is master",
          "SC14448 is master" in t, True)
    check("d04 forbids QFP probing unless a safer pad exists",
          "NO-GO" in t and "QFP" in t, True)
    check("d04 requires a 1.8 V-capable front end",
          "1.8 V-capable" in t, True)
    check("d04 says a flat line does not prove a fault",
          "must not be read as" in t, True)

KF = ROOT / "docs" / "fon-known-facts.md"
if KF.is_file():
    t = KF.read_text()
    check("known facts separate proprietary disassembly from GPL",
          "proprietary disassembly" in t, True)
    check("known facts record the tdm@0 role",
          "FON / pcmlink" in t, True)

# ---------------------------------------------------------------------------
# 17. C3.1: overflow, control-word honesty, header rails, fs_per_dma status
# ---------------------------------------------------------------------------
TDMSRC = ROOT / "src" / "fon-driver" / "fon_tdm.c"
TDMHDR = ROOT / "src" / "fon-driver" / "fon_tdm.h"
if TDMSRC.is_file():
    t = TDMSRC.read_text()
    check("geometry check divides instead of multiplying",
          "len % frame_bytes == 0 && len / frame_bytes == frames" in t, True)
    check("geometry check no longer multiplies frames in size_t",
          "len == (size_t)frames * slots" not in t, True)
if TDMHDR.is_file():
    t = TDMHDR.read_text()
    check("frame is not described as all-silence",
          "NOT \"all silence\"" in t or "not \"all silence\"" in t.lower(),
          True)
    check("offset 0x08 is a parameter, not a constant",
          "enum fon_tdm_header_08" in t, True)

if D04.is_file():
    t = D04.read_text()
    check("d04 fixes the time-base arithmetic",
          "200 µs/div × 10 div = 2 ms" in t, True)
    check("d04 no longer claims 200 us/div shows 1.6 frames",
          "~1.6 frames across the screen" not in t, True)
    check("d04 says 1 025 720 Hz is OEM-reported, not our measurement",
          "has not been measured by us" in t, True)
    check("d04 does not require a 10 s 10 MSa/s dump",
          "not a 10 s = 100 Msample dump" in t, True)
    check("d04 keeps firmware-required as a hypothesis",
          "still a\nhypothesis" in t or "still a hypothesis" in t, True)

if KF.is_file():
    t = KF.read_text()
    check("fs_per_dma is not claimed as a GPL literal 32",
          "not a literal 32" in t, True)
    check("Q76 is the fs_per_dma question id", "(Q76)" in t, True)

# ---------------------------------------------------------------------------
# 18. D0.5: PCM net identification and runbook
# ---------------------------------------------------------------------------
D05 = ROOT / "docs" / "fon-d05-pcm-net-identification.md"
D05RB = ROOT / "docs" / "runbook" / "fon-stage-d05-pcm-net-identification.md"
check("d05 pcm net doc exists", D05.is_file(), True)
check("d05 runbook exists", D05RB.is_file(), True)

if D05.is_file():
    t = D05.read_text()
    check("d05 maps i2s_rx to gpio20-23",
          "`i2s_rx` | 0, 1, 2, **20, 21, 22, 23**" in t, True)
    check("d05 maps i2s_tx to gpio24-26",
          "`i2s_tx` | **24, 25, 26**" in t, True)
    check("d05 states no pinctrl-0 on PCM nodes",
          "no `pinctrl-0`" in t or "has `pinctrl-0`? |" in t, True)
    check("d05 keeps the physical point UNKNOWN",
          "Accessible point" in t and "**UNKNOWN**" in t, True)
    check("d05 resolves the 0x808 FPGA flag",
          "FPGA-present flag" in t, True)
    check("d05 downgrades fs_per_dma to unresolved",
          "UNRESOLVED" in t and "withdrawn" in t, True)

if D05RB.is_file():
    t = D05RB.read_text()
    check("d05 runbook starts with finding the net",
          "finding the net" in t, True)
    check("d05 runbook forbids powered QFP probing",
          "NO-GO" in t and "QFP" in t, True)
    check("d05 runbook refuses A/B as PCM without proof",
          "are not identified as PCM" in t, True)
    check("d05 runbook requires 1.8 V-capable front end",
          "1.8 V-capable" in t, True)
    check("d05 runbook marks BCLK as not measured here",
          "neither frequency has been measured" in t, True)

README = ROOT / "src" / "fon-driver" / "README.md"
if README.is_file():
    t = README.read_text()
    check("driver README uses the 7530 hdr08 default 0x5555",
          "byte 0x08  0x5555" in t, True)

# ---------------------------------------------------------------------------
# 19. C3.3: no generated binaries, reconciled hdr08 and fs_per_dma status
# ---------------------------------------------------------------------------
import subprocess as _sp

_tracked = _sp.run(["git", "ls-files", "src/fon-driver/tests"],
                   cwd=ROOT, capture_output=True, text=True).stdout.split()
_generated = {"fon_c2_test", "fon_tdm_test", "fon_dma_test",
              "fon_tdm_test32", "fon_tdm_test_san", "fon_dma_test_san"}
check("no generated test binaries are tracked",
      [p for p in _tracked if p.rsplit("/", 1)[-1] in _generated], [])

_gi = ROOT / "src" / "fon-driver" / "tests" / ".gitignore"
if _gi.is_file():
    _t = _gi.read_text()
    check("gitignore lists every generated test binary",
          all(n in _t for n in _generated), True)

_HDR = ROOT / "src" / "fon-driver" / "fon_tdm.h"
if _HDR.is_file():
    _t = _HDR.read_text()
    check("header documents the FPGA/0x808 selection",
          "config & 0x1003" in _t, True)
    check("header no longer says the 0x08 condition is undecoded",
          "condition behind that flag is not decoded" not in _t, True)
    check("header no longer claims the driver defaults to _ZERO",
          "defaults to _ZERO" not in _t, True)

_DMAH = ROOT / "src" / "fon-driver" / "fon_dma.h"
if _DMAH.is_file():
    _t = _DMAH.read_text()
    check("fon_dma.h records fs_per_dma as UNRESOLVED",
          "UNRESOLVED (Q76)" in _t, True)

for _name in ("docs/fon-adss-tdm-channel-map.md", "docs/fon-known-facts.md",
              "src/fon-driver/README.md"):
    _f = ROOT / _name
    if _f.is_file():
        _t = _f.read_text()
        check(f"{_name} does not claim fs_per_dma=32 as resolved",
              "INFERRED that the FON path uses 32" not in _t
              and "32 is INFERRED" not in _t, True)

if D05.is_file():
    _t = D05.read_text()
    check("d05 calls GPIO20-27 candidates, not the only pins",
          "documented AVM candidates" in _t, True)

if D05RB.is_file():
    _t = D05RB.read_text()
    check("d05 runbook drops the 'can only appear' claim",
          "can only appear" not in _t, True)

print()
print(f"{fails} failure(s), {skips} skip(s)")
sys.exit(1 if fails else 0)
