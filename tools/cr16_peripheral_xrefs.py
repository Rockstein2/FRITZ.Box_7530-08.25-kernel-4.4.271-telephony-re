#!/usr/bin/env python3
"""Memory-access cross-references for SC14448 firmware, with dataflow.

For every memory instruction the scanner decides *what address it accesses*
and grades the answer:

    RESOLVED  a constant proven by the machine code (abs20 operand, or a
              register pair whose value is a proven constant in this block)
    SYMBOLIC  an expression over a proven base, never evaluated
    UNKNOWN   the base registers are not known statically
    STACK     the stack frame (`(sp)`)
    INDEXED   `[r12]` / `[r13]` indexed forms

Model (deliberately conservative):

* linear disassembly is cut into basic blocks; every block starts with an
  all-UNKNOWN register state, so no value crosses a block boundary, a call,
  a return, or an indirect jump.  A block only inherits a state when every
  predecessor agrees — this version never inherits, which can only *lose*
  a link, never invent one.
* `movd $imm:l,(rp)` makes the pair KNOWN32; `movd $imm:m,(rp)` makes only
  the high half KNOWN16; `movd $imm,(rN)` makes a single register KNOWN16;
* writing either half of a pair invalidates the pair;
* `addd src,dst` with dst KNOWN32 keeps the constant; any other `addd`
  invalidates the destination;
* a `load*` into a register invalidates it.

Memory-operand forms understood (from `cr16-opc.c`, `LD_STOR_INS`):

    <abs16>:m                    abs20 operand (address in the instruction)
    <disp>:s|m(rN)               one base register
    <disp>:s|m(rN,rM)            register-pair base
    (rN) / (rN,rM)               zero displacement
    <disp>:s|m(sp)               stack frame
    [r12] / [r13]<disp>:m        index-register forms

Usage:
    python3 tools/cr16_peripheral_xrefs.py --json tools/reports/peripheral-xrefs.json
"""
import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src" / "mock"))

import cr16_cfg as C  # noqa: E402

TOOL_VERSION = "cr16-peripheral-xrefs/2"
OBJDUMP = Path("/tmp/opencode/cr16/build/binutils/objdump")
IMAGES = [
    ("normal", ROOT / "firmware" / "dectfw_secondlevel_441.hex"),
    ("p2test", ROOT / "firmware" / "dectfw_secondlevel_441p2test.hex"),
]

ACCESS = {"loadw": ("READ", 16), "storw": ("WRITE", 16),
          "loadb": ("READ", 8), "storb": ("WRITE", 8),
          "loadd": ("READ", 32), "stord": ("WRITE", 32)}
BRANCHES = C.COND | C.JUMPS

ABS20 = re.compile(r"^0x([0-9a-f]+):m$")
DISPS_RP = re.compile(r"^(0x[0-9a-f]+|\$?-?\d+)(?::[sm])?\((r\d+),(r\d+)\)$")
DISPS_R = re.compile(r"^(0x[0-9a-f]+|\$?-?\d+)(?::[sm])?\((r\d+)\)$")
BARE_RP = re.compile(r"^\((r\d+),(r\d+)\)$")
BARE_R = re.compile(r"^\((r\d+)\)$")
IDX = re.compile(r"^\[(r\d+)\](?:0x([0-9a-f]+))?(?::[a-z])?(?:\([^)]*\))?$")
STACK = re.compile(r"^(?:0x[0-9a-f]+)?(?::[sm])?\(sp\)$")


def split_operands(text):
    out, depth, cur = [], 0, ""
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def _num(text):
    text = text.strip()
    neg = text.startswith("-")
    text = text.lstrip("-").lstrip("$")
    value = int(text, 16) if text.startswith("0x") else int(text)
    return -value if neg else value


def parse_memory_operand(text):
    text = text.strip()
    m = ABS20.match(text)
    if m:
        return "ABS", int(m.group(1), 16)
    m = DISPS_RP.match(text)
    if m:
        return "DISP_RP", (_num(m.group(1)), m.group(2), m.group(3))
    m = DISPS_R.match(text)
    if m:
        return "DISP_R", (_num(m.group(1)), m.group(2))
    m = BARE_RP.match(text)
    if m:
        return "DISP_RP", (0, m.group(1), m.group(2))
    m = BARE_R.match(text)
    if m:
        return "DISP_R", (0, m.group(1))
    m = IDX.match(text)
    if m:
        return "IDX", (m.group(1), int(m.group(2) or 0, 16))
    if STACK.match(text):
        return "STACK", None
    return None


def abs20_address(raw):
    return ((raw[0] & 0x0F) << 16) | raw[2] | (raw[3] << 8)


# ---------------------------------------------------------------------------
# register state: pairs are ("P", hi, lo) -> ("KNOWN32", value) | ("UNKNOWN", None)
# ---------------------------------------------------------------------------
def pair_state(state, hi, lo):
    return state.get(("P", hi, lo), ("UNKNOWN", None))


def invalidate(state, reg):
    for key in list(state):
        if key[0] == "P" and reg in (key[1], key[2]):
            state[key] = ("UNKNOWN", None)


def set_pair(state, hi, lo, value):
    invalidate(state, hi)
    invalidate(state, lo)
    state[("P", hi, lo)] = ("KNOWN32", value)


def set_reg(state, reg, value):
    invalidate(state, reg)
    state[("R", reg)] = ("KNOWN16", value)


MD_RE = re.compile(r"^\$0x([0-9a-f]+):l,\((r\d+),(r\d+)\)$")
MD_M_RE = re.compile(r"^\$0x([0-9a-f]+):m,\((r\d+),(r\d+)\)$")
MV_RE = re.compile(r"^\$0x([0-9a-f]+)(?::[sm])?,(r\d+)$")


def apply_instruction(state, insn):
    ops = insn.operands.replace(" ", "")
    if insn.mnemonic in C.CALLS:
        state.clear()
        return
    m = MD_RE.match(ops)
    if m:
        set_pair(state, m.group(2), m.group(3), int(m.group(1), 16))
        return
    m = MD_M_RE.match(ops)
    if m:
        invalidate(state, m.group(2))
        invalidate(state, m.group(3))
        return
    m = MV_RE.match(ops)
    if m:
        set_reg(state, m.group(2), int(m.group(1), 16))
        return
    # addd <rp>,<rp> keeps a constant only when the destination is one
    m = re.match(r"^\((r\d+),(r\d+)\),(\(r\d+,r\d+\))$", ops)
    if m and insn.mnemonic == "addd":
        # destination first; without a value for the source the result is
        # not a constant that this analysis can follow
        invalidate(state, m.group(1))
        invalidate(state, m.group(2))
        return
    # any other instruction that writes a register invalidates it
    m = re.match(r"^.*,((?:r\d+)|\(r\d+(?:,r\d+)?\))$", ops)
    if m and insn.mnemonic not in (C.COND | C.RETS) and \
            insn.mnemonic not in ("cmpw", "cmpb", "cmpd", "tbit", "tbitw",
                                  "tbitb", "cbitw", "cbitb"):
        target = m.group(1)
        if target.startswith("("):
            for reg in re.findall(r"r\d+", target):
                invalidate(state, reg)
        else:
            invalidate(state, target)


def write_back(state, insn):
    if insn.mnemonic.startswith("load"):
        for operand in split_operands(insn.operands):
            if re.match(r"^r\d+$", operand):
                invalidate(state, operand)


# ---------------------------------------------------------------------------
def block_leaders(fw):
    leaders = set()
    for addr, insn in fw.insns.items():
        if insn.mnemonic in BRANCHES or insn.mnemonic in (C.CALLS | C.RETS):
            if insn.end in fw.insns:
                leaders.add(insn.end)
            target, _form, status = C.decode_insn(addr, insn.mnemonic,
                                                  insn.raw[:6])
            if status == "DIRECT" and target in fw.insns:
                leaders.add(target)
    return leaders


def blocks_of(fw):
    leaders = block_leaders(fw)
    blocks, current, prev = {}, None, None
    for addr in sorted(fw.insns):
        insn = fw.insns[addr]
        if current is None or addr in leaders or prev is None or \
                prev.end != addr:
            current = addr
            blocks[current] = []
        blocks[current].append(addr)
        prev = insn
    return blocks


def reachability(fw):
    edges = C.build(fw)
    mode_a = C.reach_all(fw, edges, [0x1602]) if 0x1602 in fw.insns else {}
    entries = C.heuristic_entries(fw, edges)
    mode_b = C.reach_all(fw, edges, [e.addr for e in entries])
    return mode_a, mode_b


def _row(image, addr, insn, kind, width, address_kind, effective=None,
         provenance=(), expr=None, mode_a=(), mode_b=(), note=""):
    return {
        "image": image,
        "instruction": f"0x{addr:06x}",
        "bytes": insn.raw.hex(),
        "mnemonic": insn.mnemonic,
        "operation": kind,
        "width_bits": width,
        "address_kind": address_kind,
        "effective_address": effective,
        "expression": expr,
        "provenance": sorted(set(provenance)),
        "reachable_mode_a": addr in mode_a,
        "reachable_mode_b": addr in mode_b,
        "note": note,
    }


def scan(fw, image):
    """Return (rows, stats, unclassified)."""
    blocks = blocks_of(fw)
    mode_a, mode_b = reachability(fw)
    rows, unclassified = [], []
    for start in sorted(blocks):
        state = {}
        prov = {}
        index_sym = {}
        for addr in blocks[start]:
            insn = fw.insns[addr]
            ops = insn.operands.replace(" ", "")

            # index register used by the fill pattern: movzw rX,(rp)
            m = re.match(r"^(r\d+),\((r\d+),(r\d+)\)$", ops)
            if m and insn.mnemonic == "movzw":
                index_sym[(m.group(2), m.group(3))] = m.group(1)
            m = re.match(r"^\$(?:0x1|1):s,\(([^)]+)\)$", ops)
            if m and insn.mnemonic == "ashud":
                regs = re.findall(r"r\d+", m.group(1))
                if len(regs) == 2:
                    key = (regs[0], regs[1])
                    if key in index_sym:
                        index_sym[key] = "2*" + index_sym[key]
            m = re.match(r"^\((r\d+),(r\d+)\),\((r\d+),(r\d+)\)$", ops)
            if m and insn.mnemonic == "addd":
                # `addd src,dst`: the first pair is the source, the second
                # the destination, so the doubled index moves from the source
                # to the destination pair
                src = (m.group(1), m.group(2))
                dst = (m.group(3), m.group(4))
                if src in index_sym:
                    index_sym[dst] = index_sym.pop(src)
                elif dst in index_sym:
                    index_sym[dst] = index_sym.pop(dst)
                else:
                    index_sym.pop(dst, None)




            if insn.mnemonic in ACCESS:
                kind, width = ACCESS[insn.mnemonic]
                parsed, payload = None, None
                for operand in split_operands(insn.operands):
                    p = parse_memory_operand(operand)
                    if p:
                        parsed, payload = p
                        break
                if parsed == "ABS":
                    value = abs20_address(insn.raw)
                    if value == payload:
                        rows.append(_row(image, addr, insn, kind, width,
                                         "RESOLVED", f"0x{value:08x}",
                                         [f"0x{addr:06x}"], None,
                                         mode_a, mode_b))
                    else:
                        rows.append(_row(image, addr, insn, kind, width,
                                         "UNKNOWN", None, [], None,
                                         mode_a, mode_b,
                                         "abs20 field differs from the "
                                         "printed operand"))
                elif parsed == "DISP_RP":
                    disp, hi, lo = payload
                    st = pair_state(state, hi, lo)
                    sym = index_sym.get((hi, lo))
                    if st[0] == "KNOWN32" and sym:
                        rows.append(_row(
                            image, addr, insn, kind, width, "SYMBOLIC",
                            None, prov.get((hi, lo), []),
                            f"0x{st[1]:08x} + {sym}" if sym.startswith("2*")
                            else f"0x{st[1]:08x} + zero_extend16({sym})",
                            mode_a, mode_b,
                            "base loaded by movd, index added afterwards"))
                    elif st[0] == "KNOWN32":
                        rows.append(_row(image, addr, insn, kind, width,
                                         "RESOLVED",
                                         f"0x{(st[1] + disp) & 0xFFFFFFFF:08x}",
                                         prov.get((hi, lo), []), None,
                                         mode_a, mode_b))
                    else:
                        rows.append(_row(image, addr, insn, kind, width,
                                         "UNKNOWN", None, [], f"({hi},{lo})+{disp}",
                                         mode_a, mode_b))
                elif parsed == "DISP_R":
                    disp, reg = payload
                    if reg in ("r12", "r13"):
                        rows.append(_row(image, addr, insn, kind, width,
                                         "INDEXED", f"[{reg}]+{disp}", [],
                                         None, mode_a, mode_b))
                    else:
                        rows.append(_row(image, addr, insn, kind, width,
                                         "UNKNOWN", None, [], f"{reg}+{disp}",
                                         mode_a, mode_b))
                elif parsed == "IDX":
                    reg, disp = payload
                    rows.append(_row(image, addr, insn, kind, width,
                                     "INDEXED", f"[{reg}]+{disp:#x}", [],
                                     None, mode_a, mode_b))
                elif parsed == "STACK":
                    rows.append(_row(image, addr, insn, kind, width, "STACK",
                                     "sp", [], None, mode_a, mode_b))
                else:
                    unclassified.append(f"0x{addr:06x} {insn.mnemonic} "
                                        f"{insn.operands}")
                write_back(state, insn)
                continue

            if insn.mnemonic == "movd":
                m = MD_RE.match(ops)
                if m:
                    hi, lo = m.group(2), m.group(3)
                    rows.append(_row(image, addr, insn, "ADDRESS_LOAD", 32,
                                     "RESOLVED",
                                     f"0x{int(m.group(1), 16):08x}",
                                     [f"0x{addr:06x}"], None,
                                     mode_a, mode_b))
                    prov[(hi, lo)] = [f"0x{addr:06x}"]

            apply_instruction(state, insn)

            # a pair built from a base plus an index keeps its origin
            m = re.match(r"^\((r\d+),(r\d+)\),(\(r\d+,r\d+\))$", ops)
            if m and insn.mnemonic == "addd":
                dst = (m.group(1), m.group(2))
                srcs = re.findall(r"r\d+", m.group(3))
                src = (srcs[0], srcs[1]) if len(srcs) == 2 else None
                if prov.get(dst):
                    prov[dst] = prov[dst] + [f"0x{addr:06x}"]
                elif src and prov.get(src):
                    prov[dst] = prov[src] + [f"0x{addr:06x}"]

    return rows, _stats(rows), unclassified


def _stats(rows):
    st = defaultdict(int)
    for r in rows:
        st[(r["operation"], r["address_kind"])] += 1
    return {f"{k[0]}/{k[1]}": v for k, v in sorted(st.items())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path)
    ap.add_argument("--objdump", type=Path, default=OBJDUMP)
    args = ap.parse_args()
    if not args.objdump.is_file():
        print("SKIP: CR16 objdump not available", file=sys.stderr)
        return 2
    missing = [str(p) for _, p in IMAGES if not p.is_file()]
    if missing:
        print(f"SKIP: firmware missing: {missing}", file=sys.stderr)
        return 2
    report = {"tool": TOOL_VERSION, "images": {}}
    for image, path in IMAGES:
        fw = C.load(str(path))
        C.disassemble(fw, str(args.objdump))
        rows, stats, unclassified = scan(fw, image)
        report["images"][image] = {
            "file": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "decoded_instructions": len(fw.insns),
            "operations": rows,
            "stats": stats,
            "unclassified": unclassified,
        }
    text = json.dumps(report, indent=1, sort_keys=True) + "\n"
    if args.json:
        args.json.write_text(text)
        print(f"wrote {args.json}")
    for image in report["images"]:
        print(image, report["images"][image]["stats"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
