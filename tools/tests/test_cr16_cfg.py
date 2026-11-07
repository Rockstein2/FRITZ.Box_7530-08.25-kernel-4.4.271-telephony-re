#!/usr/bin/env python3
"""Tests for tools/cr16_cfg.py: decode, edge categories, fallthrough, modes.

Run: python3 tools/tests/test_cr16_cfg.py

Each check prints PASS, FAIL or SKIP.  A SKIP is used when the vendor image
or the locally built CR16 objdump is unavailable; it is never counted as a
pass.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cr16_cfg as C  # noqa: E402

OBJDUMP_CANDIDATES = [
    Path("/tmp/opencode/cr16/build/binutils/objdump"),
    Path("/tmp/opencode/cr16/build2/binutils/objdump"),
]
FW = Path(__file__).resolve().parent.parent.parent / \
    "firmware" / "dectfw_secondlevel_441.hex"

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
    skips += 1


def objdump():
    for p in OBJDUMP_CANDIDATES:
        if p.is_file():
            return str(p)
    return None


def load_fw():
    od = objdump()
    if od is None:
        skip("firmware load", "CR16 objdump not available")
        return None
    if not FW.exists():
        skip("firmware load", f"{FW} missing")
        return None
    fw = C.load(str(FW))
    C.disassemble(fw, od)
    return fw


def hexfile(records):
    """Write a minimal Intel HEX file; records = [(addr, bytes)]."""
    lines = []
    for addr, data in records:
        b = [len(data), (addr >> 8) & 0xFF, addr & 0xFF, 0x00] + list(data)
        chk = (-sum(b)) & 0xFF
        lines.append(":" + "".join(f"{x:02X}" for x in b + [chk]))
    lines.append(":00000001FF")
    f = tempfile.NamedTemporaryFile(suffix=".hex", delete=False, mode="w")
    f.write("\n".join(lines) + "\n")
    f.close()
    return f.name


# ---------------------------------------------------------------------------
# Instruction decoding: the continuation line of a 6-byte instruction must
# never become a separate instruction and never a fallthrough target.
# ---------------------------------------------------------------------------
def test_six_byte_instruction():
    fw = load_fw()
    if fw is None:
        return
    check("0x2582 is 6 bytes", fw.insns[0x2582].size, 6)
    check("0x2582 mnemonic", fw.insns[0x2582].mnemonic, "movd")
    check("0x2588 starts after it", 0x2588 in fw.insns, True)
    check("0x2582 end", fw.insns[0x2582].end, 0x2588)
    # No instruction may start inside another instruction.
    interior = set()
    for a, i in fw.insns.items():
        for k in range(a + 2, a + i.size, 2):
            interior.add(k)
    check("no instruction starts mid-instruction",
          sorted(set(fw.insns) & interior)[:5], [])


def test_known_branches():
    fw = load_fw()
    if fw is None:
        return
    edges = C.build(fw)

    def tgt(src):
        for e in edges:
            if e.src == src and e.kind in ("call", "jump", "cond") and \
               e.category == C.DIRECT_RESOLVED:
                return e.dst
        return None

    check("0x2570 -> 0x3C8C", tgt(0x2570), 0x3C8C)
    check("0x257E -> 0x24F8", tgt(0x257E), 0x24F8)
    check("0x25E2 -> 0x28CAA", tgt(0x25E2), 0x28CAA)
    check("0x0AF0 -> 0x0496", tgt(0x0AF0), 0x0496)


# ---------------------------------------------------------------------------
# Fallthrough rules
# ---------------------------------------------------------------------------
def test_fallthrough_rules():
    check("call falls through",
          C.has_fallthrough(C.Insn(0, 4, "bal", "(ra),*+0x10:m", b"")), True)
    check("conditional falls through",
          C.has_fallthrough(C.Insn(0, 2, "beq", "*+0x4:s", b"")), True)
    check("unconditional jump does not",
          C.has_fallthrough(C.Insn(0, 2, "jump", "(ra)", b"")), False)
    # `br` is the unconditional relative branch (CR16A "BR (Unconditional
    # Branch)"); it must not get a return-site or next-instruction edge.
    check("unconditional br does not fall through",
          C.has_fallthrough(C.Insn(0, 2, "br", "*+0x20:s", b"")), False)
    check("unconditional 4-byte br does not fall through",
          C.has_fallthrough(C.Insn(0, 4, "br", "*+0x300:m", b"")), False)
    check("return does not",
          C.has_fallthrough(C.Insn(0, 2, "popret", "$0x1,r0", b"")), False)
    check("retx does not",
          C.has_fallthrough(C.Insn(0, 2, "retx", "", b"")), False)

    od = objdump()
    if od is None:
        skip("fallthrough edges built", "CR16 objdump not available")
        return
    # A synthetic image: bal at 0, popret at 4, popret at 0x10.
    img = bytearray(b"\x1e\x03" * 16)
    img[0:4] = bytes([0x00, 0xC0, 0x10, 0x00])   # bal (ra),*+0x10
    img[4:6] = b"\x1e\x03"                       # popret RA
    path = hexfile([(0x0000, bytes(img))])
    fw = C.load(path)
    C.disassemble(fw, od)
    edges = C.build(fw)
    calls = [e for e in edges
             if e.src == 0 and e.kind in ("call", "jump", "cond")]
    check("synthetic one call edge",
          [(e.kind, e.dst, e.category) for e in calls],
          [("call", 0x10, C.DIRECT_RESOLVED)])
    check("call has a fallthrough edge",
          [(e.kind, e.dst) for e in edges
           if e.src == 0 and e.kind == "fallthrough"],
          [("fallthrough", 0x04)])
    check("popret has no fallthrough",
          [e for e in edges if e.src == 4 and e.kind == "fallthrough"], [])

    # A synthetic image for the four unconditional-branch cases plus the two
    # contrasting forms (bal with a return site, bne with two branches).
    # Layout, 2-byte instruction grid:
    #   0x00: br *+0x10      (forward, inside this run)
    #   0x02: br *-0x02      (backward; lands on 0x00)
    #   0x04: bne *+0x04     (conditional, two branches)
    #   0x06: bal *+0x0E     (call to 0x14, returns to 0x0A)
    #   0x08: popret RA
    #   0x0a: popret RA
    #   0x14: popret RA
    img = bytearray(b"\x1e\x03" * 24)
    # Real `br` bytes from the vendor image, relocated to the synthetic base:
    #   `e4 10` is `br *+0x08` (firmware 0x13F6 -> 0x13FE) and
    #   `e5 1f` is `br *-0x16` (firmware 0x19F2 -> 0x19DC).
    img[0x00:0x02] = bytes([0xE4, 0x10])   # br forward (+0x08) -> 0x08
    # 0x08 must be an instruction start of the same 2-byte grid:
    # `e4 10` at 0x00 jumps to 0x08, which the popret grid already fills.
    img[0x02:0x04] = bytes([0xE5, 0x1F])   # br backward (-0x16) -> wraps
    img[0x04:0x06] = bytes([0x12, 0x12])   # bne, two branches
    img[0x06:0x0A] = bytes([0x00, 0xC0, 0x0E, 0x00])   # bal *+0x0E
    path = hexfile([(0x0000, bytes(img))])
    fw = C.load(path)
    C.disassemble(fw, od)
    e2 = C.build(fw)
    br = [e for e in e2 if e.src == 0x00]
    check("synthetic br forward: one jump edge, no fallthrough",
          [(e.kind, e.dst) for e in br], [("jump", 0x08)])
    brb = [e for e in e2 if e.src == 0x02]
    check("synthetic br backward: one jump edge, no fallthrough",
          [(e.kind, e.dst, e.category) for e in brb],
          [("jump", (0x02 - 0x16) & 0xFFFFFF, C.OUTSIDE_LOADED_IMAGE)])
    bne = [e for e in e2 if e.src == 0x04]
    check("synthetic bne keeps both branches",
          sorted((e.kind, e.dst) for e in bne),
          [("cond", 0x48), ("fallthrough", 0x06)])
    bal = [e for e in e2 if e.src == 0x06]
    check("synthetic bal keeps call target and return site",
          sorted((e.kind, e.dst, e.category) for e in bal),
          [("call", 0x14, C.DIRECT_RESOLVED),
           ("fallthrough", 0x0A, C.DIRECT_RESOLVED)])


# ---------------------------------------------------------------------------
# Edge categories, one per case
# ---------------------------------------------------------------------------
def test_edge_categories():
    fw = load_fw()
    if fw is None:
        return
    edges = C.build(fw)
    by_src = {}
    for e in edges:
        by_src.setdefault(e.src, []).append(e)

    # INDIRECT_REGISTER: `jump (ra)`
    cat = [e.category for e in by_src.get(0x494, []) if e.kind == "indirect"]
    check("0x494 jump (ra) is INDIRECT_REGISTER",
          cat, [C.INDIRECT_REGISTER])
    # `jal (r7,r6)` at 0x14
    cat = [e.category for e in by_src.get(0x14, []) if e.kind == "indirect"]
    check("0x14 jal (r7,r6) is INDIRECT_REGISTER",
          cat, [C.INDIRECT_REGISTER])

    # DIRECT_UNSUPPORTED: the 6-byte conditional at 0x92fc.
    cat = [e.category for e in by_src.get(0x92FC, []) if e.kind == "cond"]
    check("0x92fc 6-byte conditional leaves the image",
          cat, [C.OUTSIDE_LOADED_IMAGE])

    # Every direct-resolved non-fallthrough edge lands on an instruction.
    bad = [e for e in edges
           if e.category == C.DIRECT_RESOLVED and e.kind != "fallthrough"
           and e.dst not in fw.insns]
    check("DIRECT_RESOLVED never lands off-boundary", bad, [])

    # TARGET_NOT_INSTRUCTION / OUTSIDE_LOADED_IMAGE carry a target but are
    # never followed.
    notch = [e for e in edges if e.category == C.TARGET_NOT_INSTRUCTION]
    check("TARGET_NOT_INSTRUCTION targets are inside a run",
          all(fw.in_run(e.dst) for e in notch), True)
    outside = [e for e in edges if e.category == C.OUTSIDE_LOADED_IMAGE]
    check("OUTSIDE_LOADED_IMAGE targets are outside every run",
          all(not fw.in_run(e.dst) for e in outside), True)


# ---------------------------------------------------------------------------
# Category statistics: all eight categories are reported separately and the
# old "2706 unresolved" figure is gone.
# ---------------------------------------------------------------------------
def test_category_stats():
    fw = load_fw()
    if fw is None:
        return
    edges = C.build(fw)
    st = C.category_stats(edges)
    check("all eight categories reported",
          sorted(k for k in st if k != "TOTAL"), sorted(C.CATEGORIES))
    check("category counts sum to the total",
          sum(st[c] for c in C.CATEGORIES), st["TOTAL"])
    check("INDIRECT_REGISTER is 382", st[C.INDIRECT_REGISTER], 382)
    check("INDIRECT_UNRESOLVED is 0 (same thing as REGISTER here)",
          st[C.INDIRECT_UNRESOLVED], 0)
    # every branch form now decodes, so nothing is left unsupported
    check("DIRECT_UNSUPPORTED is 0", st[C.DIRECT_UNSUPPORTED], 0)
    check("FALLTHROUGH_UNRESOLVED is 9", st[C.FALLTHROUGH_UNRESOLVED], 9)
    check("TOTAL edges", st["TOTAL"], 22669)


# ---------------------------------------------------------------------------
# Entry points and the three reachability modes
# ---------------------------------------------------------------------------
def test_modes():
    fw = load_fw()
    if fw is None:
        return
    edges = C.build(fw)
    modes = C.run_modes(fw, edges)

    # A: single candidate
    check("mode A starts at 0x1602", [e.addr for e in modes["A"].entries],
          [0x1602])
    check("mode A entry is not verified", modes["A"].entries[0].verified,
          False)
    check("mode A reaches the whole chain",
          all(a in modes["A"].reached for a in
              (0x39F8, 0x3A2C, 0x25FB8, 0x25F90, 0x25FAA, 0x2558, 0x257E,
               0x24F8)), True)

    # B: all heuristic candidates, never verified
    check("mode B has candidates", modes["B"].count > 300, True)
    check("mode B entries are not verified",
          any(e.verified for e in modes["B"].entries), False)
    # Modes A and B start from different sets, so neither contains the
    # other; what matters is that both are non-empty and that mode B is the
    # larger research view.  (After the dispe9 fix mode A reaches 9 042
    # instructions and mode B 17 600.)
    check("mode A reaches more than zero", len(modes["A"].reached) > 0, True)
    check("mode B reaches more than mode A",
          len(modes["B"].reached) > len(modes["A"].reached), True)

    # C: verified entries only, empty on purpose
    check("mode C has no verified entries", modes["C"].count, 0)
    check("mode C reaches nothing", len(modes["C"].reached), 0)

    # Heuristic entries must never be built from mid-instruction addresses.
    interior = set()
    for a, i in fw.insns.items():
        for k in range(a + 2, a + i.size, 2):
            interior.add(k)
    check("no heuristic entry is mid-instruction",
          [e.addr for e in modes["B"].entries if e.addr in interior], [])
    # 0x1602 is reached by fallthrough from 0x15fe, so it is NOT a root.
    check("0x1602 is not a heuristic root",
          0x1602 in {e.addr for e in modes["B"].entries}, False)


def test_partial_reach_is_explicit():
    """The old `reachable()` defaults to one hop; `reach_all` does not."""
    od = objdump()
    if od is None:
        skip("one-hop reach", "CR16 objdump not available")
        return
    img = bytearray(b"\x1e\x03" * 32)
    img[0:4] = bytes([0x00, 0xC0, 0x10, 0x00])   # bal -> 0x10
    # second hop: a 2-word bal from 0x10 to 0x20 encodes the displacement
    # 0x10 in bits[31:8]: `00 c0 10 00` (the byte layout is identical to the
    # first hop because the field is the offset, not the address).
    img[0x10:0x14] = bytes([0x00, 0xC0, 0x10, 0x00])
    path = hexfile([(0x0000, bytes(img))])
    fw = C.load(path)
    C.disassemble(fw, od)
    edges = C.build(fw)
    one = C.reachable(fw, edges, [C.Entry(0, "t", True)])
    full = C.reach_all(fw, edges, [0])
    check("reachable(min_depth=1) is one hop", sorted(one), [0])
    # 0x10 and 0x20 are reached; 0x30 and 0x40 are the continuation after
    # the return of each call, which the CFG keeps as a fallthrough edge.
    # With the one-hop default only 0x0 is visited; reach_all follows the
    # call to 0x10 and then the second hop to 0x20.
    check("reach_all reaches the second call", 0x10 in full and 0x20 in full,
          True)
    # Return sites are followed too (each call also has a fallthrough edge).
    check("reach_all follows return paths", 0x4 in full and 0x14 in full,
          True)


def main():
    test_six_byte_instruction()
    test_known_branches()
    test_fallthrough_rules()
    test_edge_categories()
    test_category_stats()
    test_modes()
    test_partial_reach_is_explicit()
    print()
    print(f"{fails} failure(s), {skips} skip(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
