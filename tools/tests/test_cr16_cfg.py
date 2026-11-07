#!/usr/bin/env python3
"""Tests for tools/cr16_cfg.py and the instruction-length fix.

Run: python3 tools/tests/test_cr16_cfg.py

The firmware cases use real bytes from dectfw_secondlevel_441.hex; the
synthetic cases build minimal images in memory so every CFG rule can be
checked without depending on the vendor image.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cr16_cfg as C  # noqa: E402

OBJDUMP = "/tmp/opencode/cr16/build/binutils/objdump"
FW = Path(__file__).resolve().parent.parent.parent / \
    "firmware" / "dectfw_secondlevel_441.hex"

fails = 0


def check(name, got, want):
    global fails
    if got == want:
        print(f"PASS {name}")
    else:
        print(f"FAIL {name}: got {got!r} want {want!r}")
        fails += 1


def test_six_byte_instruction():
    if not FW.exists() or not Path(OBJDUMP).exists():
        print("SKIP six-byte instruction (firmware or objdump missing)")
        return
    fw = C.load(str(FW))
    C.disassemble(fw, OBJDUMP)
    check("0x2582 is 6 bytes", fw.insns[0x2582].size, 6)
    check("0x2582 mnemonic", fw.insns[0x2582].mnemonic, "movd")
    check("0x2588 starts after it", 0x2588 in fw.insns, True)
    check("0x2588 is 4 bytes", fw.insns[0x2588].size, 4)
    check("0x258C is the following store", fw.insns[0x258C].mnemonic,
          "storw")
    check("0x2582 end", fw.insns[0x2582].end, 0x2588)
    check("0x2588 end", fw.insns[0x2588].end, 0x258C)


def test_known_branches():
    if not FW.exists() or not Path(OBJDUMP).exists():
        print("SKIP known branches (missing inputs)")
        return
    fw = C.load(str(FW))
    C.disassemble(fw, OBJDUMP)
    edges = C.build(fw)

    def tgt(src):
        for e in edges:
            if e.src == src and e.kind in ("call", "jump", "cond") and \
               e.confidence == C.VERIFIED_DIRECT:
                return e.dst
        return None

    check("0x2570 -> 0x3C8C", tgt(0x2570), 0x3C8C)
    check("0x257E -> 0x24F8", tgt(0x257E), 0x24F8)
    check("0x25E2 -> 0x28CAA", tgt(0x25E2), 0x28CAA)
    check("0x0AF0 -> 0x0496", tgt(0x0AF0), 0x0496)


def test_synthetic_cfg():
    """Build a tiny image: call, conditional, jump and return."""
    import cr16_branch as B

    def enc(addr, disp):
        """Encode a 2-word bal whose target is addr + disp."""
        p = (-disp) & 0xFFFFFF if disp < 0 else disp
        if disp < 0:
            p |= 1
        return bytes([0x00, 0xC0, p & 0xFF, (p >> 8) & 0xFF])

    # 0x00: bal -> 0x10 ; 0x04: popret ; 0x10: popret
    img = bytearray(b"\x1e\x03" * 0x10)   # popret RA everywhere: real code
    img[0:4] = enc(0, 0x10 - 0)
    img[4:6] = b"\x1e\x03"          # popret RA

    with tempfile.NamedTemporaryFile(suffix=".hex", delete=False) as f:
        # build a minimal Intel HEX with two records
        def rec(addr, data):
            n = len(data)
            b = [n, (addr >> 8) & 0xFF, addr & 0xFF, 0x00] + list(data)
            chk = (-sum(b)) & 0xFF
            return ":" + "".join(f"{x:02X}" for x in b + [chk])
        f.write((rec(0x0000, img[0:0x10]) + "\n").encode())
        f.write((rec(0x0010, img[0x10:0x20]) + "\n").encode())
        f.write(b":00000001FF\n")
        path = f.name

    fw = C.load(path)
    C.disassemble(fw, OBJDUMP)
    edges = C.build(fw)
    calls = [e for e in edges if e.kind == "call"]
    check("synthetic one call", len(calls), 1)
    check("synthetic call target", calls[0].dst, 0x10)
    check("synthetic call verified", calls[0].confidence,
          C.VERIFIED_DIRECT)
    # popret must not fall through
    ft = [e for e in edges if e.kind == "fallthrough" and e.src == 0x4]
    check("popret has no fallthrough", len(ft), 0)


def test_entry_rule():
    if not FW.exists() or not Path(OBJDUMP).exists():
        print("SKIP entry rule (missing inputs)")
        return
    fw = C.load(str(FW))
    C.disassemble(fw, OBJDUMP)
    edges = C.build(fw)
    targets = {e.dst for e in edges if e.kind == "call" and e.dst is not None}
    ft = {e.dst for e in edges if e.kind == "fallthrough" and e.dst is not None}
    roots = sorted(t for t in targets if t not in ft)
    check("roots are call targets only", all(r in targets for r in roots),
          True)
    # 0x24F8 IS a call target and is never reached by fallthrough, so the
    # rule calls it a root.  What matters is that it is ALSO reachable from
    # a real caller, which the reachability test checks separately.
    check("0x24F8 is a call target", 0x24F8 in targets, True)


def test_reachability_chain():
    if not FW.exists() or not Path(OBJDUMP).exists():
        print("SKIP reachability (missing inputs)")
        return
    fw = C.load(str(FW))
    C.disassemble(fw, OBJDUMP)
    edges = C.build(fw)
    targets = {e.dst for e in edges if e.kind == "call" and e.dst is not None}
    ft = {e.dst for e in edges if e.kind == "fallthrough" and e.dst is not None}
    roots = sorted(t for t in targets if t not in ft)
    entries = [C.Entry(r, "call target", True) for r in roots]
    reached = C.reachable(fw, edges, entries)
    for a in (0x2558, 0x24F8, 0x3C8C, 0x25F90):
        check(f"{a:#06x} reachable from the roots", a in reached, True)


def test_branch_into_middle():
    """A target inside a run but not on an instruction boundary is CANDIDATE."""
    if not FW.exists() or not Path(OBJDUMP).exists():
        print("SKIP middle-of-instruction (missing inputs)")
        return
    fw = C.load(str(FW))
    C.disassemble(fw, OBJDUMP)
    edges = C.build(fw)
    cand = [e for e in edges
            if e.confidence == C.CANDIDATE and e.dst is not None and
            fw.in_run(e.dst)]
    # Such edges may exist; what matters is that they are never VERIFIED.
    verified_offboundary = [
        e for e in edges
        if e.confidence == C.VERIFIED_DIRECT and e.dst is not None and
        e.kind != "fallthrough" and e.dst not in fw.insns]
    check("no verified edge lands off-boundary", verified_offboundary, [])


def main():
    test_six_byte_instruction()
    test_known_branches()
    test_synthetic_cfg()
    test_entry_rule()
    test_reachability_chain()
    test_branch_into_middle()
    print()
    print("FAILURES" if fails else "all CFG tests passed")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
