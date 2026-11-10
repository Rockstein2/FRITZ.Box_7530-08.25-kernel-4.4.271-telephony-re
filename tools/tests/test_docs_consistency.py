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
DOCS = ROOT / "docs"
HISTORY = DOCS / "history"
RUNBOOK = DOCS / "runbook"
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(ROOT / "src" / "mock"))

import cr16_cfg as C  # noqa: E402

REPORT = ROOT / "tools" / "reports" / "cr16-branch-validation.json"
CFG_DOC = HISTORY / "fon-dialog-cr16-cfg.md"
BRANCH_DOC = HISTORY / "fon-dialog-cr16-branches.md"
PERIPH_DOC = HISTORY / "fon-dialog-peripheral-init.md"
FACTS_DOC = DOCS / "fon-known-facts.md"

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
XREF_DOCS = [HISTORY / name for name in (
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
    check("report: encoded 0x000F6006 is preserved for four writes",
          sum(1 for image in xr["images"].values()
              for row in image["operations"]
              if row.get("encoded_address") == "0x000f6006"
              and row["operation"] == "WRITE"), 4)
    check("report: encoded 0x000F6006 resolves to 0x00FF6006",
          all(row["effective_address"] == "0x00ff6006"
              for image in xr["images"].values()
              for row in image["operations"]
              if row.get("encoded_address") == "0x000f6006"), True)
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

    doc = HISTORY / "fon-dialog-peripheral-xrefs.md"
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
    eff = HISTORY / "fon-dialog-cr16-register-effects.md"
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
XREF_DOC = HISTORY / "fon-dialog-peripheral-xrefs.md"
DEPS_DOC = HISTORY / "fon-dialog-init-dependencies.md"
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
ALIAS_DOC = HISTORY / "fon-dialog-address-alias-hypotheses.md"
if ALIAS_DOC.is_file():
    t = ALIAS_DOC.read_text()
    check("alias doc: address space is resolved",
          "address-space part is RESOLVED" in t, True)
    check("alias doc: physical identity remains candidate",
          "Physical identity remains CANDIDATE." in t, True)
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
BOOT_DOCS = {n: HISTORY / n for n in (
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

SYSREG = HISTORY / "fon-dialog-cr16-system-registers.md"
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
EXT = {n: HISTORY / n for n in (
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
    check("register-map doc reports the resolved effective address",
          "SAME_ARCHITECTURAL_ADDRESS" in t, True)
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
SYSREG = HISTORY / "fon-dialog-cr16-system-registers.md"
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

VEC = HISTORY / "fon-dialog-cr16-vector-map.md"
if VEC.is_file():
    t = VEC.read_text()
    check("vector doc: no '32 entries' claim",
          "has 32 entries" not in t, True)
    check("vector doc: 31 entries stated", "31 consecutive entries" in t,
          True)
    check("vector doc: stub does not prove different numbering",
          "do not prove the *numbering* differs" in t, True)

ROM = HISTORY / "fon-dialog-uart-boot-comparison.md"
if ROM.is_file():
    t = ROM.read_text()
    check("rom doc: XOR check described", "challenge–response" in t, True)
    check("rom doc: no 'checksum none' claim",
          "none in `dialogtool.py`" not in t, True)
    check("rom doc: ACK after the comparison", "only if the bytes match" in t,
          True)

HELPER = HISTORY / "fon-dialog-copy-helper-28d56.md"
if HELPER.is_file():
    t = HELPER.read_text()
    check("helper doc: p2test range ends 0x9b43", "0x9B43" in t, True)

# ---------------------------------------------------------------------------
# 13. BOOT-3.1: one consistent boot model everywhere
# ---------------------------------------------------------------------------
BOOTMAP = ROOT / "tools" / "reports" / "cr16-boot-memory-map.json"
HAN = HISTORY / "fon-dialog-boot-handoff.md"
DEC = HISTORY / "fon-dialog-boot-branch-decoding.md"
OQ = DOCS / "fon-open-questions.md"

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
    check("open questions: no resolved rows", "| answered |" not in t, True)
    check("open questions: resolved Q66 removed", "| Q66 |" not in t, True)

if FACTS_DOC.is_file():
    t = FACTS_DOC.read_text()
    check("known facts: vector table has 31 entries",
          "**31** entries" in t, True)

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
UARTID = HISTORY / "fon-dialog-board-uart-identification.md"
D0 = RUNBOOK / "fon-stage-d0-uart-identification.md"
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
C3 = HISTORY / "fon-adss-tdm-channel-map.md"
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

KF = DOCS / "fon-known-facts.md"
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
D05 = HISTORY / "fon-d05-pcm-net-identification.md"
D05RB = RUNBOOK / "fon-stage-d05-pcm-net-identification.md"
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

for _name in ("docs/history/fon-adss-tdm-channel-map.md",
              "docs/fon-known-facts.md",
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

# ---------------------------------------------------------------------------
# 20. D0.6: reset path, pinmux, inverter, startup sequence, read-only runbook
# ---------------------------------------------------------------------------
_d06 = {
    "reset": HISTORY / "fon-d06-dect-reset-path.md",
    "pinmux": HISTORY / "fon-d06-pcm-pinmux.md",
    "inverter": HISTORY / "fon-d06-inverter-hypotheses.md",
    "startup": HISTORY / "fon-d06-sc14448-startup-sequence.md",
    "readonly": RUNBOOK / "fon-stage-d06-readonly.md",
    "oem_dtb": RUNBOOK / "fon-oem-dtb-extraction.md",
}
for _k, _f in _d06.items():
    check(f"d06 {_k} doc exists", _f.is_file(), True)

_t = _d06["reset"].read_text() if _d06["reset"].is_file() else ""
check("d06 records assert=0 at the API", "assert = 0" in _t, True)
check("d06 records the profile slot +0x28", "profile+0x28" in _t, True)
check("d06 keeps electrical polarity UNKNOWN",
      "Electrical level at the SC14448 pin" in _t, True)
check("d06 puts UART init before reset release",
      "0xb80 < 0xb9c" in _t and "GPIO40 = 0" in _t, True)
check("d06 does not promote API value to pad level",
      "| Pad electrical level | **UNKNOWN** | **UNKNOWN**" in _t, True)

_t = _d06["pinmux"].read_text() if _d06["pinmux"].is_file() else ""
check("d06 pinmux records pinconfig by pcmlink",
      "dakota_gpio_pinconfig" in _t, True)
check("d06 pinmux disproves the earlier 'no pinmux' claim",
      "DISPROVED" in _t, True)
check("d06 pinmux records compiled FUNC_SEL values",
      "AVM_DEF_HW_FUNCTION_PINMUX2 = 2" in _t
      and "AVM_DEF_HW_FUNCTION_PINMUX3 = 3" in _t, True)
check("d06 pinmux keeps AVM API transformation unresolved",
      "API pass-through **UNKNOWN**" in _t, True)
check("d06 pinmux gives the TLMM base", "0x01000000" in _t, True)

_t = _d06["inverter"].read_text() if _d06["inverter"].is_file() else ""
check("d06 inverter does not claim reset",
      "UNKNOWN — not assumed" in _t, True)
check("d06 inverter keeps the truth-table measurement",
      "A high → Y low" in _t, True)
check("d06 inverter measurement is OpenWrt-only",
      "under OpenWrt only" in _t
      and "cannot be extrapolated to working" in _t, True)

_t = _d06["startup"].read_text() if _d06["startup"].is_file() else ""
check("d06 startup lists the reset links", "RESET release" in _t, True)
check("d06 startup marks clocks as UNKNOWN",
      "Firmware runs | SC14448" in _t, True)

_t = _d06["readonly"].read_text() if _d06["readonly"].is_file() else ""
check("d06 read-only runbook refuses devmem commands",
      "not** given as a ready command" in _t, True)
check("d06 read-only runbook is passive",
      "No GPIO write, no TLMM write" in _t, True)

_t = _d06["oem_dtb"].read_text() if _d06["oem_dtb"].is_file() else ""
check("d06 OEM DTB records exact provenance",
      "0x98d038" in _t and "26963" in _t, True)
check("d06 OEM DTB records verified hash",
      "3083e2acedc800015fea5ee7e57fa6cc8da551e21ee792095cbd8a7224bb841f"
      in _t, True)
check("d06 OEM DTB extraction reconstructs EVA LZMA",
      "lzma_header = src[28:33]" in _t
      and "payload = src[36:36 + compressed_size]" in _t, True)
check("d06 OEM DTB remains outside Git",
      "Do not add the extracted `.dtb`" in _t, True)

# ---------------------------------------------------------------------------
# 21. layered documentation structure and relative links
# ---------------------------------------------------------------------------
SUMMARY = DOCS / "fon-d06-summary.md"
check("d06 summary doc exists", SUMMARY.is_file(), True)
if SUMMARY.is_file():
    _t = SUMMARY.read_text()
    check("d06 summary records the API/electrical distinction",
          "API arguments 0/1 must not be promoted" in _t, True)
    check("d06 summary lists the three layers",
          "`history/`" in _t and "`runbook/`" in _t, True)
    check("d06 summary keeps active reset NO-GO",
          "does **not** authorize GPIO40 output/toggle" in _t, True)

_root_current = {
    "README.md", "fon-known-facts.md", "fon-open-questions.md",
    "fon-go-no-go.md", "fon-d06-summary.md", "fon-adss-clock-reset.md",
    "fon-dialog-minimal-loader.md", "fon-tdm-control-only-plan.md",
    "fon-e0-summary.md", "fon-sc14448-pcmlink-protocol.md",
    "fon-e1-summary.md", "fon-e2-summary.md", "fon-e3-summary.md",
    "fon-e32-summary.md", "fon-e33-summary.md", "fon-e34-summary.md",
    "fon-e35-summary.md",
}
_root_analysis = [p.name for p in DOCS.glob("*.md")
                  if p.name not in _root_current]
check("no analysis documents left in the docs root",
      sorted(_root_analysis), [])

_broken = []
_link_re = re.compile(r'(?<!!)\[[^\]]*\]\(([^)]+)\)')
for _md in DOCS.rglob("*.md"):
    _text = _md.read_text()
    if "docs/../" in _text:
        _broken.append(f"{_md.relative_to(ROOT)}: docs/../ path")
    for _m in _link_re.finditer(_text):
        _target = _m.group(1).strip().split("#", 1)[0]
        if not _target or _target.startswith(
                ("http://", "https://", "mailto:", "tel:")):
            continue
        if not (_md.parent / _target).exists():
            _broken.append(f"{_md.relative_to(ROOT)}: {_target}")
check("all docs relative links resolve", sorted(_broken), [])

# ---------------------------------------------------------------------------
# 22. DOCS-EVIDENCE-REVIEW: stale conclusions and evidence classes
# ---------------------------------------------------------------------------
_facts = FACTS_DOC.read_text() if FACTS_DOC.is_file() else ""
_summary = SUMMARY.read_text() if SUMMARY.is_file() else ""
_oq = OQ.read_text() if OQ.is_file() else ""
_pinmux_history = (HISTORY / "fon-d06-pcm-pinmux.md")
_pinmux_text = (_pinmux_history.read_text()
                if _pinmux_history.is_file() else "")
_dtb_runbook = RUNBOOK / "fon-oem-dtb-extraction.md"
_dtb_text = _dtb_runbook.read_text() if _dtb_runbook.is_file() else ""

# Evidence classes are source classes, not truth status.
check("known facts: RUNTIME split into RUNTIME-RO / HW-TEST",
      "| **RUNTIME-RO** |" in _facts
      and "| **HW-TEST** |" in _facts
      and "\n| **RUNTIME** |" not in _facts, True)
check("known facts: HW-TEST covers the module-load run",
      "**HW-TEST (§9d)**" in _facts, True)

# §7 rows sourced from pcmlink.ko must be DISASM, not GPL.
for _label in ("FON register transport", "Hook detection",
               "Ring control", "Line feed"):
    _row = find_row(FACTS_DOC, _label)
    check(f"known facts: {_label} is DISASM",
          (_row[2].startswith("DISASM")
           if _row and len(_row) > 2 else None), True)

# Stale CR16 conclusions must not survive in current facts.
for _stale in ("hand-off branch target | **UNKNOWN**",
               "0x24F8 (recursion)", "fills 512 words",
               "32 entries", "block at `0x000000` is data",
               "Piglet clock check is passive"):
    check(f"known facts: stale claim absent: {_stale}",
          _stale not in _facts, True)

check("known facts: 0x0 is not a valid entry, 0x8 is executable",
      "`0x000000` is not a valid entry point" in _facts
      and "`0x000008` is executable" in _facts, True)
_handoff = find_row(FACTS_DOC, "hand-off chain")
check("known facts: hand-off chain is static 0x10284 -> 0x8 -> 0x15AA/0x1026",
      _handoff is not None
      and "0x10284" in _handoff[1]
      and "0x8" in _handoff[1]
      and "0x15AA" in _handoff[1]
      and "0x1026" in _handoff[1]
      and "L3, static" in _handoff[2], True)

# Linux ownership is not a hardware FUNC_SEL readback.
for _text, _name in ((_facts, "known facts"), (_summary, "D0.6 summary"),
                     (_pinmux_text, "D0.6 pinmux history"),
                     (_oq, "open questions")):
    check(f"{_name}: MUX UNCLAIMED is not hardware proof",
          "MUX UNCLAIMED" not in _text
          or ("not a readback" in _text or "not a hardware register readback"
              in _text or "hardware `FUNC_SEL`" in _text), True)
for _stale in ("so **not muxed**", "decisive passive result",
               "the ADSS pads are not connected",
               "C0 already proved the ADSS pads are not muxed",
               "The absence of an I2S mux"):
    check(f"no stale mux conclusion: {_stale}",
          all(_stale not in p.read_text() for p in DOCS.rglob("*.md")), True)

# Piglet's GPIO API call is not proven side-effect free.
_piglet = find_row(FACTS_DOC, "Piglet clock check")
check("known facts: Piglet clock check has no explicit pinconfig",
      _piglet is not None and "dakota_gpio_ctrl" in _piglet[1]
      and "pinconfig" in _piglet[1], True)
_piglet_side = find_row(FACTS_DOC, "Piglet ctrl side effects")
check("known facts: Piglet ctrl side effects are UNKNOWN",
      _piglet_side is not None and _piglet_side[2] == "UNKNOWN", True)
check("D0.6 summary: Piglet ctrl side effects are UNKNOWN",
      (find_row(SUMMARY, "Piglet ctrl side effects") or
       [None, None, None])[2] == "UNKNOWN", True)

# Open questions reflect what is actually resolved.
for _closed in ("Q1", "Q6", "Q7", "Q51"):
    check(f"open questions: closed {_closed} removed",
          find_row(OQ, _closed) is None, True)
for _open in ("Q13", "Q39", "Q44", "Q47", "Q70", "Q76", "Q77",
              "Q79", "Q80", "Q81"):
    check(f"open questions: {_open} remains listed",
          find_row(OQ, _open) is not None, True)
_q47 = find_row(OQ, "Q47")
check("Q47: vector table found, hardware reset entry still open",
      _q47 is not None and "INTBASE" in _q47[1]
      and "vector table we have not found" not in _q47[1], True)
_q44 = find_row(OQ, "Q44")
check("Q44: narrowed to effective translation/alias",
      _q44 is not None and "effective bus address" in _q44[1]
      and "18, 19 or 20 bits" not in _q44[1], True)

# UART / GPIO16 distinction: the live OEM readback resolves the pin role.
check("known facts: GPIO16 live role is UART RX",
      "GPIO16" in _facts and "UART **RX**" in _facts
      and "Q78 is closed" in _facts, True)
check("open questions: closed Q78 removed",
      find_row(OQ, "Q78") is None, True)
check("known facts: OEM live TLMM readback is recorded",
      "TLMM_GPIO_CFG=0x00004a02" in _facts
      and "CFG=0x0000480a" in _facts
      and "CFG=0x0000480e" in _facts
      and "Codecslots=9" in _facts, True)

# OEM DTB provenance: three variants, selection not proven.
for _needle in ("0x98d038", "0x993990", "0x99a2e8",
                "subrevision", "Q80"):
    check(f"D0.6 summary: OEM DTB provenance records {_needle}",
          _needle in _summary, True)
check("OEM DTB runbook: three variants and selection caveat",
      all(x in _dtb_text for x in ("0x98d038", "0x993990", "0x99a2e8",
                                   "subrevision", "Q80")), True)
check("OEM DTB runbook: model alone is not selection proof",
      "model` string alone is not evidence of bootloader selection"
      in _dtb_text, True)

# ---------------------------------------------------------------------------
# 23. OEM 08.25 boot capture is primary reference, not history
# ---------------------------------------------------------------------------
_REF = DOCS / "reference" / "oem-08.25-boot"
_ref_rx = _REF / "rx.log"
_ref_tx = _REF / "tx.log"
_ref_readme = _REF / "README.md"
check("OEM capture: RX exists", _ref_rx.is_file(), True)
check("OEM capture: TX exists", _ref_tx.is_file(), True)
check("OEM capture: README exists", _ref_readme.is_file(), True)

if _ref_rx.is_file():
    _rx_bytes = _ref_rx.read_bytes()
    _rx_text = _rx_bytes.decode("utf-8")
    check("OEM capture: RX is a text file", b"\x00" not in _rx_bytes, True)
    for _needle in (
        "use_hw_config_to_set_gpios: hw_config: gpio_avm_dect_reset 40",
        "use_hw_config_to_set_gpios: hw_config: gpio_avm_dect_rd 16",
        "[piglet]slow: dect_loader-bootmode",
        "upload of 'dectfw_secondlevel_441.hex' successfull",
        "[piglet]TDM: FS: 8000 Hz CLK: 1024355 Hz",
        "mbox_dma_init: irq=107 hwirq=191",
    ):
        check(f"OEM capture: RX contains {_needle}", _needle in _rx_text, True)
    check("OEM capture: binary shared-UART blocks are summarized",
          "binary/non-text serial data block removed" in _rx_text, True)

if _ref_tx.is_file():
    _tx = _ref_tx.read_text(errors="replace")
    check("OEM capture: TX contains the device query",
          "cat /etc/version" in _tx, True)

# The repository is public: no original device identifiers may survive.
for _f in (_ref_rx, _ref_tx):
    if not _f.is_file():
        continue
    _b = _f.read_bytes()
    check(f"OEM capture: {_f.name} has no original MAC",
          re.search(rb"98:9b:cb:46:7b:[0-9a-f]{2}", _b, re.I) is None, True)
    check(f"OEM capture: {_f.name} has no original IPv6 suffix",
          re.search(rb"9a9b:cbff:fe46:7b[0-9a-f]{2}", _b, re.I) is None, True)
    check(f"OEM capture: {_f.name} has no original ULA prefix",
          b"fd86:e1a4:8ab4" not in _b, True)
    check(f"OEM capture: {_f.name} has no original RFPI",
          b"03136f6f50" not in _b, True)

if _ref_readme.is_file():
    _r = _ref_readme.read_text()
    check("OEM capture: README records original RX hash",
          "e854d392546b2013b2ff24a1193a5b0c3986cabce6ae4690d947b0bf5723bde0"
          in _r, True)
    check("OEM capture: README records the raw backup location",
          "evidence/oem-08.25/boot-logs/2026-11-08/" in _r, True)
    check("OEM capture: README states the repository is public",
          "GitHub repository is public" in _r, True)

_docs_index = (DOCS / "README.md").read_text()
check("docs index: reference layer exists",
      "`docs/reference/`" in _docs_index
      and "primary reference" in _docs_index, True)
check("known facts: OEM-CAPTURE class and HWS(2)",
      "| **OEM-CAPTURE** |" in _facts and "HWS(2)" in _facts, True)

# ---------------------------------------------------------------------------
# 24. FON-C0+ / C0+-R1 read-only TLMM clock probe
# ---------------------------------------------------------------------------
TOOL = ROOT / "tools" / "fon-tlmm-clock-probe"
for _name in ("Makefile", "README.md", ".gitignore",
              "fon-tlmm-clock-probe.c",
              "fon-tlmm-clock-probe-core.c",
              "fon-tlmm-clock-probe-core.h",
              "tests/test_core.c", "tests/check_readonly.py",
              "kernel/fon_tlmm_probe.c",
              "kernel/fon_tlmm_probe_logic.h",
              "kernel/tests/test_logic.c",
              "kernel/Makefile", "kernel/README.md"):
    check(f"C0+ tool file exists: {_name}", (TOOL / _name).is_file(), True)

OEM_TIMING_TEST = ROOT / "tools" / "tests" / "test_oem_tdm_timing.py"
_clock_doc = HISTORY / "fon-tdm-clock-software-check.md"
_c0_runbook = RUNBOOK / "fon-stage-c0plus-software-clock-probe.md"
_c0k_runbook = RUNBOOK / "fon-stage-c0plus-kernel-probe.md"
_c0_validation = HISTORY / "fon-c0plus-offline-validation.md"
_c0_safety = HISTORY / "fon-c0plus-kernel-safety-review.md"
_c0_build = HISTORY / "fon-c0plus-kernel-build-report.md"
check("C0+ OEM timing test exists", OEM_TIMING_TEST.is_file(), True)
check("C0+ safety review exists", _c0_safety.is_file(), True)
check("C0+ kernel build report exists", _c0_build.is_file(), True)
if _c0_safety.is_file():
    _st = _c0_safety.read_text()
    check("C0+ safety review records K1/K2 readiness",
          "K1" in _st and "K2" in _st and "NOT RUN" in _st, True)
if _c0_build.is_file():
    _bt = _c0_build.read_text()
    check("C0+ build report records vermagic and module hash",
          "6.12.112 SMP mod_unload ARMv7 p2v8" in _bt
          and "31173cc9eacf34c8487442cc1fd89270d3b48067fead164301b917ed79312a60"
          in _bt, True)
if OEM_TIMING_TEST.is_file():
    _ot = OEM_TIMING_TEST.read_text()
    check("C0+ OEM timing test encodes the Piglet magic",
          "PIGLET_MAGIC" in _ot and "0x10624DD3" in _ot, True)
    check("C0+ OEM timing test encodes the PCMLINK constant",
          "PCMLINK_CONST" in _ot and "0x82DE1B43DB34B6D7" in _ot, True)
    check("C0+ OEM timing test asserts 100 ms and 195 ms",
          "100 ms" in _ot and "195 ms" in _ot, True)
check("C0+ clock history exists", _clock_doc.is_file(), True)
check("C0+ userspace runbook exists", _c0_runbook.is_file(), True)
check("C0+-K kernel runbook exists", _c0k_runbook.is_file(), True)
check("C0+ validation record exists", _c0_validation.is_file(), True)

if _c0_validation.is_file():
    _vt = _c0_validation.read_text()
    check("C0+ validation records 52 synthetic passes",
          "52 PASS, 0 FAIL" in _vt, True)
    check("C0+ validation records 25 kernel-logic passes",
          "25 PASS, 0 FAIL" in _vt, True)
    check("C0+ validation records the source guard",
          "7 PASS, 0 FAIL" in _vt, True)
    check("C0+ validation records the OEM numeric test",
          "20 PASS, 0 FAIL" in _vt, True)
    check("C0+ validation records the kernel module build",
          "vermagic 6.12.112" in _vt and "not loaded" in _vt, True)
    check("C0+ validation records no router run",
          "Router run" in _vt and "NOT RUN" in _vt, True)

if _clock_doc.is_file():
    _ct = _clock_doc.read_text()
    for _needle in ("Piglet_noemif.ko", "Check_TDMInterface",
                    "100 ms", "5 * edges", "0x10624dd3",
                    "0x82de1b43db34b6d7", "195 ms", "0.1950079",
                    "[piglet]TDM", "[pcmlink]TDM",
                    "FSC and DCL are measured in sequential windows"):
        check(f"C0+ clock doc records {_needle}", _needle in _ct, True)
    check("C0+ clock doc rejects the old 0.38 s-only estimate",
          "0.38147" in _ct and "missed the `C` factor" in _ct, True)
    check("C0+ clock doc records the 100 us -> 100 ms R1 correction",
          "100 µs" in _ct and "100 ms" in _ct and "factor of 1000" in _ct,
          True)
    check("C0+ clock doc does not claim stock /dev/mem works",
          "cannot run on the stock image" in _ct, True)

# Current docs must no longer use the incorrect 100 us window.
for _p in (FACTS_DOC, DOCS / "fon-go-no-go.md", DOCS / "README.md",
           DOCS / "fon-d06-summary.md",
           HISTORY / "fon-d06-pcm-pinmux.md",
           TOOL / "README.md"):
    check(f"{_p.name}: stale 100 us window absent",
          "100 µs" not in _p.read_text() and "100 us" not in _p.read_text(),
          True)

if _c0_runbook.is_file():
    _rt = _c0_runbook.read_text()
    for _needle in ("CONFIG_DEVMEM", "NO-GO", "PROT_READ",
                    "writes MMIO", "cfg_changed=1",
                    "STATIC_OBSERVED", "DETECTED",
                    "hardware action"):
        check(f"C0+ userspace runbook records {_needle}", _needle in _rt, True)
    check("C0+ userspace runbook is marked prepared, not executed",
          "prepared, never executed" in _rt, True)

if _c0k_runbook.is_file():
    _kt = _c0k_runbook.read_text()
    for _needle in ("debugfs", "vermagic", "echo 1", "rmmod",
                    "GPIO40", "NO-GO", "20–50", "K1", "K2",
                    "EALREADY"):
        check(f"C0+-K runbook records {_needle}", _needle in _kt, True)
    check("C0+-K runbook is marked prepared, not executed",
          "prepared, never executed" in _kt, True)

_c0_control = (DOCS / "fon-tdm-control-only-plan.md").read_text()
_c0_passive = (RUNBOOK / "fon-tdm-passive-test.md").read_text()
check("C0+ control plan mentions the software probe",
      "C0+" in _c0_control and "software probe" in _c0_control, True)
check("C0+ control plan records the kernel-module preference",
      "one-shot kernel module" in _c0_control, True)
check("C0+ passive runbook says a scope is not the only method",
      "A scope is not the only way to detect input edges" in _c0_passive,
      True)
check("C0+ passive runbook mentions the one-shot kernel module",
      "one-shot kernel module" in _c0_passive, True)

for _qid, _needle in (("Q4", "software probe"), ("Q5", "4.1 MS/s"),
                      ("Q27", "software probe"), ("Q31", "C0+"),
                      ("Q37", "C0+-K")):
    _row = find_row(OQ, _qid)
    check(f"C0+ open question {_qid} remains listed and updated",
          _row is not None and _needle in " ".join(_row[1:]), True)

check("C0+ known facts record the 100 ms window",
      "100 ms" in _facts and "C0+-K" in _facts, True)
check("C0+ known facts record the stock CONFIG_DEVMEM blocker",
      "# CONFIG_DEVMEM is not set" in _facts, True)
check("C0+ go/no-go has a stage table",
      "Stage C0+" in (DOCS / "fon-go-no-go.md").read_text()
      and "C0+-K" in (DOCS / "fon-go-no-go.md").read_text(), True)
check("C0+ docs index links the userspace runbook",
      "runbook/fon-stage-c0plus-software-clock-probe.md" in _docs_index,
      True)
check("C0+ docs index links the kernel runbook",
      "runbook/fon-stage-c0plus-kernel-probe.md" in _docs_index, True)

_main = (TOOL / "fon-tlmm-clock-probe.c").read_text()
_kernel = (TOOL / "kernel" / "fon_tlmm_probe.c").read_text()
_core = (TOOL / "fon-tlmm-clock-probe-core.c").read_text()
_test = (TOOL / "tests" / "test_core.c").read_text()
check("C0+ userspace uses O_RDONLY", 'open("/dev/mem", O_RDONLY' in _main,
      True)
check("C0+ userspace has no PROT_WRITE", "PROT_WRITE" not in _main, True)
check("C0+ kernel skeleton uses readl", "readl(" in _kernel, True)
check("C0+ kernel skeleton has no writel", "writel(" not in _kernel, True)
_init = _kernel.split("static int __init fon_tlmm_probe_init")[1]
_init = _init.split("static void __exit")[0]
check("C0+ kernel module_init is idle",
      "run_measurement(" not in _init and "ioremap(" not in _init, True)
check("C0+ kernel module has a debugfs one-shot trigger",
      "debugfs_create_file" in _kernel and "run_measurement" in _kernel,
      True)
_klogic = (TOOL / "kernel" / "fon_tlmm_probe_logic.h").read_text()
check("C0+ kernel logic has separate frequency segments",
      "PROBE_SEGMENT_NS" in _klogic and "valid_segments" in _klogic, True)
check("C0+ kernel state machine rejects restarts",
      "PROBE_TRIGGER_RESULT_READY" in _klogic
      and "probe_trigger_can_start" in _klogic, True)
check("C0+ kernel command is strict one-shot",
      "EALREADY" in _kernel and "command[1] == '\\n'" in _kernel, True)
_all_c0 = _main + _kernel + _core + _test
for _needle in ("gpio_request", "gpiod_", "pinctrl_", "reset_control",
                "request_mem_region"):
    check(f"C0+ sources have no {_needle}", _needle not in _all_c0, True)
check("C0+ sources have no clk_* API call",
      re.search(r"(?<![A-Za-z0-9_])clk_", _all_c0) is None, True)
check("C0+ tests cover synthetic 8 kHz and 1.024 MHz",
      "8000" in _test and "1024000" in _test, True)
check("C0+ tests cover undersampling and gaps",
      "undersampled" in _test and "scheduler gap" in _test, True)
check("C0+ tests cover frequency change and stability",
      "frequency change" in _test and "timing_suspect" in _test, True)
check("C0+ source guard is wired into make test",
      "check_readonly.py" in (TOOL / "Makefile").read_text(), True)

# ---------------------------------------------------------------------------
# 25. FON-E0 SC14448/PCMLINK slot-5 research
# ---------------------------------------------------------------------------
_slot5 = TOOL.parent / "fon-slot5-protocol"
for _name in ("README.md", "fon_slot5.h", "fon_slot5.c",
              "tests/test_golden.c", "tests/check_offline.py", "Makefile"):
    check(f"E0 slot5 library file exists: {_name}",
          (_slot5 / _name).is_file(), True)

for _name in ("fon-e0-summary.md", "fon-sc14448-pcmlink-protocol.md"):
    check(f"E0 current document exists: {_name}",
          (DOCS / _name).is_file(), True)
for _name in ("fon-e0-tx-control-reconstruction.md",
              "fon-e0-rx-status-reconstruction.md",
              "fon-e0-analog-state-machine.md",
              "fon-e0-sc14448-firmware-search.md",
              "fon-e0-protocol-confidence.md"):
    check(f"E0 history document exists: {_name}",
          (HISTORY / _name).is_file(), True)

_proto = (DOCS / "fon-sc14448-pcmlink-protocol.md").read_text()
for _needle in ("build_slic_ctrl", "0x4000", "0x8000",
                "PutRxDMA", "0x00020008", "0xbad00000",
                "EOR #2", "Codecslots=9", "Codecslots=6",
                "slot-5", "8 kHz"):
    check(f"E0 protocol records {_needle}", _needle in _proto, True)

_e0sum = (DOCS / "fon-e0-summary.md").read_text()
for _q in ("Q16", "Q17", "Q30", "Q74", "Q75", "Q76"):
    check(f"E0 summary records {_q}", _q in _e0sum, True)

_fw = (HISTORY / "fon-e0-sc14448-firmware-search.md").read_text()
for _needle in ("0x000F6002", "0x00FF6006", "0x000F6006",
                "not found", "indirect", "cross-block"):
    check(f"E0 firmware search records {_needle}", _needle in _fw, True)

_q16 = find_row(OQ, "Q16")
_q17 = find_row(OQ, "Q17")
_q74 = find_row(OQ, "Q74")
_q75 = find_row(OQ, "Q75")
_q76 = find_row(OQ, "Q76")
check("Q16 remains open with Linux-side evidence",
      _q16 is not None and "Linux-side formula" in " ".join(_q16[1:])
      and "open" in " ".join(_q16[1:]), True)
check("Q17 remains open with Linux-side evidence",
      _q17 is not None and "Linux-side mapping" in " ".join(_q17[1:])
      and "open" in " ".join(_q17[1:]), True)
check("Q74 remains partial", _q74 is not None and "partially" in " ".join(_q74[1:]),
      True)
check("Q75 remains open", _q75 is not None and "still open" in " ".join(_q75[1:]),
      True)
check("Q76 remains open", _q76 is not None and "still open" in " ".join(_q76[1:]),
      True)

check("E0 tools index links the slot5 library",
      "fon-slot5-protocol/" in (ROOT / "tools" / "README.md").read_text(),
      True)
check("E0 docs index links the protocol",
      "fon-sc14448-pcmlink-protocol.md" in _docs_index, True)

# ---------------------------------------------------------------------------
# 26. FON-E1 cross-block dataflow / EOR #2
# ---------------------------------------------------------------------------
for _name in ("fon-e1-summary.md",
              "history/fon-e1-cross-block-dataflow.md",
              "history/fon-e1-indirect-dispatch.md",
              "history/fon-e1-pcm-handler-candidates.md",
              "history/fon-e1-normal-vs-p2test.md",
              "history/fon-e1-dma-byte-order.md"):
    check(f"E1 document exists: {_name}", (DOCS / _name).is_file(), True)

for _name in ("cr16-dataflow-normal.json", "cr16-dataflow-p2test.json",
              "cr16-indirect-candidates.json", "cr16-pcm-candidates.json"):
    check(f"E1 report exists: {_name}",
          (ROOT / "tools" / "reports" / _name).is_file(), True)

_dn = json.loads((ROOT / "tools" / "reports" /
                  "cr16-dataflow-normal.json").read_text())
_dp = json.loads((ROOT / "tools" / "reports" /
                  "cr16-dataflow-p2test.json").read_text())
check("E1 normal new-resolved count", _dn["newly_resolved_count"], 239)
check("E1 p2test new-resolved count", _dp["newly_resolved_count"], 239)
check("E1 normal state blocks", _dn["state_blocks"] > 0, True)
check("E1 p2test state blocks", _dp["state_blocks"] > 0, True)
check("E1 reports keep unknown counts", "new_stats" in _dn, True)

_df = (DOCS / "history" / "fon-e1-cross-block-dataflow.md").read_text()
check("E1 dataflow doc records new metrics",
      "239" in _df and "239" in _df and "750" in _df and "894" in _df, True)
check("E1 dataflow doc records false-positive flag",
      "outside the known internal range" in _df, True)
_de = (DOCS / "history" / "fon-e1-dma-byte-order.md").read_text()
check("E1 EOR doc records halfword pair swap",
      "adjacent 16" in _de and "0x08" in _de, True)
check("E1 EOR doc leaves wire order unknown",
      "physical wire order" in _de and "UNKNOWN" in _de, True)
_pc = (DOCS / "history" / "fon-e1-pcm-handler-candidates.md").read_text()
check("E1 PCM doc does not name 0x01000000 PCM buffer",
      "not named PCM" in _pc and "no resolved reader" in _pc, True)

for _qid in ("Q46", "Q53", "Q54", "Q55", "Q57", "Q74", "Q75"):
    _row = find_row(OQ, _qid)
    check(f"E1 question {_qid} remains listed", _row is not None, True)
_q74 = find_row(OQ, "Q74")
_q75 = find_row(OQ, "Q75")
check("E1 Q74 remains partial with raw/wire distinction",
      _q74 is not None and "partial" in " ".join(_q74[1:]).lower()
      and "physical wire" in " ".join(_q74[1:]).lower(), True)
check("E1 Q75 remains open",
      _q75 is not None and "still open" in " ".join(_q75[1:]), True)

check("E1 tools index links dataflow",
      "cr16_dataflow.py" in (ROOT / "tools" / "README.md").read_text(), True)
check("E1 summary is in docs index",
      "fon-e1-summary.md" in _docs_index, True)

# ---------------------------------------------------------------------------
# 27. FON-E2 interprocedural / table / IRQ
# ---------------------------------------------------------------------------
for _name in ("fon-e2-summary.md",
              "history/fon-e2-interprocedural-dataflow.md",
              "history/fon-e2-table-dispatch.md",
              "history/fon-e2-irq-callgraph.md",
              "history/fon-e2-firmware-handler-search.md",
              "history/fon-e2-loader-vs-pcm-buffer.md"):
    check(f"E2 document exists: {_name}", (DOCS / _name).is_file(), True)

for _name in ("cr16-interproc-normal.json", "cr16-interproc-p2test.json",
              "cr16-table-dispatch.json", "cr16-irq-paths.json",
              "cr16-fon-handler-candidates.json"):
    check(f"E2 report exists: {_name}",
          (ROOT / "tools" / "reports" / _name).is_file(), True)

_e2n = json.loads((ROOT / "tools" / "reports" /
                   "cr16-interproc-normal.json").read_text())
_e2p = json.loads((ROOT / "tools" / "reports" /
                   "cr16-interproc-p2test.json").read_text())
check("E2 normal function summaries", _e2n["function_entries"], 432)
check("E2 p2test function summaries", _e2p["function_entries"], 403)
check("E2 normal proven arguments",
      _e2n["proven_argument_propagations"], 43)
check("E2 p2test proven arguments",
      _e2p["proven_argument_propagations"], 22)
check("E2 reports keep source SHA",
      len(_e2n.get("sha256", "")) == 64
      and len(_e2p.get("sha256", "")) == 64, True)

_tab = json.loads((ROOT / "tools" / "reports" /
                   "cr16-table-dispatch.json").read_text())
for _image in ("normal", "p2test"):
    _s = _tab["images"][_image]["summary"]
    check(f"E2 {_image} table has no proven target",
          _s["proven_targets"], 0)
    check(f"E2 {_image} table keeps unresolved sites",
          _s["unresolved"] > 0, True)

_irq = json.loads((ROOT / "tools" / "reports" /
                   "cr16-irq-paths.json").read_text())
for _image in ("normal", "p2test"):
    check(f"E2 {_image} IRQ vectors",
          len(_irq["images"][_image]["vectors"]), 31)
    check(f"E2 {_image} IRQ has no PCM-named handler",
          _irq["images"][_image]["pcm_named_handlers"], 0)

_h = json.loads((ROOT / "tools" / "reports" /
                 "cr16-fon-handler-candidates.json").read_text())
check("E2 does not claim a slot-5 handler", _h["handler_found"], False)
check("E2 classifies 0x01000000 without naming it PCM",
      _h["classification"]["0x01000000"],
      "LOADER_OR_RAM_INIT_CANDIDATE")

_e2s = (DOCS / "fon-e2-summary.md").read_text()
for _needle in ("CONVERGED", "NON_CONVERGED", "146", "116", "25", "10",
                "382", "396", "31", "0x00ff4000", "generic_slotinterleave"):
    check(f"E2 summary records {_needle}", _needle in _e2s, True)

_e2o = (HISTORY / "fon-e2-interprocedural-dataflow.md").read_text()
check("E2 interprocedural doc records call/return CFG",
      "call ------> callee entry" in _e2o, True)
check("E2 interprocedural doc records convergence failure handling",
      "NON_CONVERGED" in _e2o, True)
_e2t = (HISTORY / "fon-e2-table-dispatch.md").read_text()
check("E2 table doc records no proven target",
      "| normal | 382 | 0 | 382 | 0 |" in _e2t, True)
_e2i = (HISTORY / "fon-e2-irq-callgraph.md").read_text()
check("E2 IRQ doc records the 31-vector table",
      "31" in _e2i and "dip_int" in _e2i, True)
_e2f = (HISTORY / "fon-e2-firmware-handler-search.md").read_text()
check("E2 handler doc records remaining indirect sites",
      "382" in _e2f and "385" in _e2f, True)
_e2l = (HISTORY / "fon-e2-loader-vs-pcm-buffer.md").read_text()
check("E2 loader doc does not name PCM buffer",
      "not a named PCM buffer" in _e2l, True)

check("E2 tools index links interprocedural tool",
      "cr16_interproc.py" in (ROOT / "tools" / "README.md").read_text(),
      True)
check("E2 summary is in docs index",
      "fon-e2-summary.md" in _docs_index, True)

# ---------------------------------------------------------------------------
# 28. FON-E3 soundness audit and focused traces
# ---------------------------------------------------------------------------
for _name in ("fon-e3-summary.md",
              "history/fon-e3-dataflow-correctness.md",
              "history/fon-e3-dsp-irq-reconstruction.md",
              "history/fon-e3-dip-pcm-reconstruction.md",
              "history/fon-e3-loader-runtime-boundary.md"):
    check(f"E3 document exists: {_name}", (DOCS / _name).is_file(), True)

for _name in ("cr16-e3-soundness-audit.json", "cr16-e3-dsp-paths.json",
              "cr16-e3-dip-paths.json", "cr16-e3-callsite-audit.json",
              "cr16-e3-handler-candidates.json"):
    check(f"E3 report exists: {_name}",
          (ROOT / "tools" / "reports" / _name).is_file(), True)

_e3s = json.loads((ROOT / "tools" / "reports" /
                   "cr16-e3-soundness-audit.json").read_text())
for _image, _old, _proven, _cand in (("normal", 25, 43, 58),
                                    ("p2test", 10, 22, 69)):
    _d = _e3s["images"][_image]
    check(f"E3 {_image}: old PROVEN audited", _d["old_proven"], _old)
    check(f"E3 {_image}: corrected PROVEN", _d["new_proven"], _proven)
    check(f"E3 {_image}: corrected CANDIDATE", _d["new_candidate"], _cand)

_e3d = json.loads((ROOT / "tools" / "reports" /
                   "cr16-e3-dsp-paths.json").read_text())
for _image in ("normal", "p2test"):
    _d = _e3d["images"][_image]
    check(f"E3 {_image}: 0xD6 pointer", _d["pointer_cell"]["image_u32"],
          "0x01027f80")
    check(f"E3 {_image}: pointer +0x58",
          _d["pointer_cell"]["plus_0x58"], "0x01027fd8")

_e3i = json.loads((ROOT / "tools" / "reports" /
                   "cr16-e3-dip-paths.json").read_text())
for _image in ("normal", "p2test"):
    _d = _e3i["images"][_image]
    check(f"E3 {_image}: F6006 read present",
          any(o.get("effective_address") == "0x00ff6006"
              for o in _d["memory_operations"]), True)
    check(f"E3 {_image}: F5402 write present",
          any(o.get("effective_address") == "0x00ff5402"
              for o in _d["memory_operations"]), True)
    check(f"E3 {_image}: F6006 extension result recorded",
          _d["f6006"]["alias_claim"],
          "SAME_ARCHITECTURAL_ADDRESS_BY_ABS20_EXTENSION")

_e3h = json.loads((ROOT / "tools" / "reports" /
                   "cr16-e3-handler-candidates.json").read_text())
for _image in ("normal", "p2test"):
    _d = _e3h["images"][_image]
    check(f"E3 {_image}: no slot-5 handler",
          _d["slot5_handler_found"], False)
    check(f"E3 {_image}: 0x01000000 unresolved",
          _d["0x01000000"]["classification"], "UNRESOLVED")
    check(f"E3 {_image}: 0x01000000 not PCM",
          _d["0x01000000"]["runtime_pcm_buffer_proven"], False)

_e3sum = (DOCS / "fon-e3-summary.md").read_text()
for _needle in ("11", "3", "43", "22", "382", "385", "0x01027F80",
                "0x01027FD8", "UNRESOLVED", "NON_CONVERGED"):
    check(f"E3 summary records {_needle}", _needle in _e3sum, True)
check("E3 tools index links the audit tool",
      "cr16_e3.py" in (ROOT / "tools" / "README.md").read_text(), True)
check("E3 summary is in docs index",
      "fon-e3-summary.md" in _docs_index, True)

# ---------------------------------------------------------------------------
# 29. FON-REF0 external Dialog/CR16/DECT reference registry
# ---------------------------------------------------------------------------
REFDIR = DOCS / "references"
for _name in ("README.md", "dialog-external-sources.md",
              "dialog-register-cross-reference.md",
              "dialog-pcm-comparison.md", "sc14480-memory-map.md",
              "fon-e3-reference-opportunities.md"):
    check(f"REF0 document exists: {_name}",
          (REFDIR / _name).is_file(), True)

_ref_sources = (REFDIR / "dialog-external-sources.md").read_text()
for _needle in ("902254883f702e9533e6591eb457a97ca6ace257",
                "4f9e07e0ffdc4d16026e7d66f5a270b84aa12e77",
                "98734603701c5c5bc886854a66264747029b5d8f",
                "686fc01b7bc925d744d6efdeee73348f3ced8375",
                "1e5ffbd8f1b2c45f256a95375aff201b5552f03a",
                "01be0fced7d4a0ad2c8fb72b6463d3e955072b6d1e219d96806ae6d8859ac5bf",
                "a0b0300cc0dc50ac98bff4c9021dcbb86ba7b063554f406ac8f65c84a51782d0",
                "NOT VERIFIED"):
    check(f"REF0 registry records {_needle}", _needle in _ref_sources, True)

_ref_regs = (REFDIR / "dialog-register-cross-reference.md").read_text()
for _needle in ("0xFF481E", "0xFF4856", "0xFF4858", "0xFF4868",
                "SAME_ADDRESS_DIFFERENT_CHIP", "UNKNOWN", "CONFLICT",
                "0x000F6006", "0x00FF6006"):
    check(f"REF0 register table records {_needle}",
          _needle in _ref_regs, True)

_ref_pcm = (REFDIR / "dialog-pcm-comparison.md").read_text()
for _needle in ("1.152", "1.536", "2.304", "4.608", "1.024355",
                "physical wire order", "NOT FOUND"):
    check(f"REF0 PCM document records {_needle}", _needle in _ref_pcm, True)

_ref_sc = (REFDIR / "sc14480-memory-map.md").read_text()
for _needle in ("0x01000000", "0x010003FF", "0x01000002",
                "0x01027F80", "0x01027FD8", "DSP_INT_REG",
                "0x00FF5402", "0x00FF6002", "0x00FF6006",
                "URST", "0x000F0000", "0x00FF0000", "0x1001"):
    check(f"REF0 SC14480 doc records {_needle}",
          _needle in _ref_sc, True)

_ref_opps = (REFDIR / "fon-e3-reference-opportunities.md").read_text()
for _needle in ("r2", "r6", "JAL", "RETX", "DIP", "Phoenix",
                "ABI_MISMATCH"):
    check(f"REF0 E3 opportunities records {_needle}",
          _needle in _ref_opps, True)

_ref_facts = (DOCS / "fon-known-facts.md").read_text()
for _needle in ("SC14CVMDECT", "0xFF481E", "1.152", "1.024",
                "GCC CR16 ABI", "QEMU CR16C", "AHA_MEMORY"):
    check(f"REF0 known facts records {_needle}", _needle in _ref_facts, True)

_ref_index = (DOCS / "README.md").read_text()
for _needle in ("references/README.md",
                "references/dialog-external-sources.md",
                "references/dialog-register-cross-reference.md",
                "references/dialog-pcm-comparison.md",
                "references/sc14480-memory-map.md",
                "references/fon-e3-reference-opportunities.md"):
    check(f"REF0 docs index links {_needle}", _needle in _ref_index, True)

for _p in (REFDIR.rglob("*")):
    if _p.is_file():
        check(f"REF0 no PDF/source copy: {_p.name}",
              _p.suffix.lower() not in (".pdf", ".zip", ".tar", ".gz",
                                        ".bz2", ".xz", ".bin", ".hex"),
              True)

print()
print(f"{fails} failure(s), {skips} skip(s)")
sys.exit(1 if fails else 0)
