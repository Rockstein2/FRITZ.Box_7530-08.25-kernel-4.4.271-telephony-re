#!/usr/bin/env python3
"""Unit tests for tools/cr16_branch.py.

Run: python3 tools/tests/test_cr16_branch.py

Cases are real instructions taken from
dectfw_secondlevel_441.hex whose decode was confirmed against
cr16-elf-objdump, plus synthetic encodings for the sign rules.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cr16_branch import branch_target, disp24, is_in_runs  # noqa: E402

RUNS = [
    (0x000000, 0x0000D4), (0x0000D6, 0x0002B2), (0x0002B4, 0x001AAD),
    (0x0024F8, 0x003CFD), (0x009000, 0x00936A), (0x009C5E, 0x009FFF),
    (0x017300, 0x017E79), (0x017FE0, 0x017FF7), (0x020000, 0x028DCD),
]

fails = 0


def check(name, got, want):
    global fails
    if got == want:
        print(f"PASS {name}")
    else:
        print(f"FAIL {name}: got {got:#x} want {want:#x}")
        fails += 1


def check_eq(name, got, want):
    global fails
    if got == want:
        print(f"PASS {name}")
    else:
        print(f"FAIL {name}: got {got} want {want}")
        fails += 1


# ---- forward branch inside a run -----------------------------------------
# 0x2570: 00 c0 1c 17   -> objdump printed +0x3c8c
w = ((0x00 | (0xC0 << 8)), (0x1C | (0x17 << 8)))
t, sign = branch_target(0x2570, w)
check("forward branch 0x2570", t, 0x3C8C)
check_eq("forward branch 0x2570 sign flag", sign, False)
check_eq("forward target inside runs", is_in_runs(t, RUNS), True)

# 0x25e2: 02 c0 c8 66 -> objdump printed +0x28caa
w = ((0x02 | (0xC0 << 8)), (0xC8 | (0x66 << 8)))
t, sign = branch_target(0x25E2, w)
check("forward branch 0x25e2", t, 0x28CAA)
check_eq("0x25e2 inside runs", is_in_runs(t, RUNS), True)

# 0x2c6: 02 c0 76 8a -> objdump printed +0x28d3c
w = ((0x02 | (0xC0 << 8)), (0x76 | (0x8A << 8)))
t, sign = branch_target(0x2C6, w)
check("forward branch 0x2c6", t, 0x28D3C)

# 0x36c: 00 c0 20 01 -> objdump printed +0x48c
w = ((0x00 | (0xC0 << 8)), (0x20 | (0x01 << 8)))
t, sign = branch_target(0x36C, w)
check("forward branch 0x36c", t, 0x48C)

# ---- negative (sign-flagged) branch --------------------------------------
# 0x257e: ff c0 7b ff -> objdump printed *-0x24f8, target is 0x24f8
w = ((0xFF | (0xC0 << 8)), (0x7B | (0xFF << 8)))
t, sign = branch_target(0x257E, w)
check_eq("0x257e sign flag set", sign, True)
check("0x257e target", t, 0x24F8)
check_eq("0x257e inside runs", is_in_runs(t, RUNS), True)

# 0x0AF0: ff c0 a7 f9 -> objdump *-0x496, target 0x496 (has a push prologue)
w = ((0xFF | (0xC0 << 8)), (0xA7 | (0xF9 << 8)))
t, sign = branch_target(0x0AF0, w)
check_eq("0xaf0 sign flag set", sign, True)
check("0xaf0 target", t, 0x496)

# 0x131e: ff c0 b1 fe -> objdump *-0x11ce, target 0x131e-0x11ce
w = ((0xFF | (0xC0 << 8)), (0xB1 | (0xFE << 8)))
t, sign = branch_target(0x131E, w)
# 0x11ce begins with "push $0x1,r7" -> a real function prologue, so the
# decoder's 0x11ce is the correct entry, not a coincidence.
check("0x131e target", t, 0x11CE)

# ---- synthetic sign rules ------------------------------------------------
# synthetic: raw field with bit0 set -> sign flag.
# p = 0x8b, c = (~p+1)&0xffffff = 0xffff75, (-c)&0xfffffe = 0x8a,
# target = 0x1000 + 0x8a.  Confirms the arithmetic without a firmware anchor.
t, sign = branch_target(0x1000, (0, 0x8B))
check_eq("synthetic odd disp sets sign", sign, True)
check("synthetic backward target", t, 0x108A)

# raw p even and positive => plain forward
t, sign = branch_target(0x1000, (0, 0x0100))
check_eq("synthetic even disp no sign", sign, False)
check("synthetic even disp target", t, 0x1100)

# ---- three-word form -----------------------------------------------------
# 3-word bal: p = (((p>>16)&0xf)<<20)|(((p>>24)&0xf)<<16)|(p&0xffff)
words = (0x0000, 0x0000, 0x0000)
check("3-word zero displacement decodes to addr", branch_target(0x500, words)[0], 0x500)

print()
print("FAILURES" if fails else "all branch decoder tests passed")
sys.exit(1 if fails else 0)
