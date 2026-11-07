#!/usr/bin/env python3
"""Memory-access cross-references for SC14448 firmware, with dataflow.

For every memory instruction the scanner decides *what address it accesses*
and grades the answer:

    RESOLVED  a constant proven by the machine code (abs20 operand, or a
              register pair whose value is a proven constant in this block)
    SYMBOLIC  an expression over a proven base, never evaluated
    UNKNOWN   the base registers are not known statically
    STACK     the stack frame (`(sp)`)
    PC_RELATIVE  relative to the return address (`(ra)`), i.e. a code or
              literal-pool reference, never a peripheral address
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

    <abs16>:m                    abs20 operand (4-byte form)
    <abs16>:l                    abs24 operand (6-byte `opc20` form)
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

TOOL_VERSION = "cr16-peripheral-xrefs/3"
OBJDUMP = Path("/tmp/opencode/cr16/build/binutils/objdump")
IMAGES = [
    ("normal", ROOT / "firmware" / "dectfw_secondlevel_441.hex"),
    ("p2test", ROOT / "firmware" / "dectfw_secondlevel_441p2test.hex"),
]

ACCESS = {"loadw": ("READ", 16), "storw": ("WRITE", 16),
          "loadb": ("READ", 8), "storb": ("WRITE", 8),
          "loadd": ("READ", 32), "stord": ("WRITE", 32)}
BRANCHES = C.COND | C.JUMPS

ABS = re.compile(r"^0x([0-9a-f]+):[ml]$")
DISPS_RP = re.compile(r"^(0x[0-9a-f]+|\$?-?\d+)(?::[sm])?\((r\d+),(r\d+)\)$")
DISPS_R = re.compile(r"^(0x[0-9a-f]+|\$?-?\d+)(?::[sm])?\(((?:r\d+)|ra)\)$")
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
    m = ABS.match(text)
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
    """Address of the 4-byte `<abs>:m` form: low nibble of byte 0 is bit 20."""
    return ((raw[0] & 0x0F) << 16) | raw[2] | (raw[3] << 8)


def abs24_address(raw):
    """Address of the 6-byte `<abs>:l` form (`opc20`, `cr16-opc.c:354`).

    cr16-dis.c builds a 48-bit big-endian word from the three little-endian
    halfwords and then takes bits 31..16 (high byte split over two nibbles)
    plus bits 15..0.  The formula is verified against every 6-byte load/store
    in both images (161 and 170 instructions, 0 mismatches).
    """
    words = [raw[0] | (raw[1] << 8), raw[2] | (raw[3] << 8),
             raw[4] | (raw[5] << 8)]
    packed = (words[0] << 32) | (words[1] << 16) | words[2]
    return ((((packed >> 16) & 0xF) << 20) | (((packed >> 24) & 0xF) << 16)
            | (packed & 0xFFFF))


def abs_address(insn):
    """Decoded address of an absolute memory operand, or None."""
    if len(insn.raw) == 6:
        return abs24_address(insn.raw)
    if len(insn.raw) == 4:
        return abs20_address(insn.raw)
    return None


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


# Registers that an instruction writes.
#
# The list is derived from the ISA, not from a whitelist of mnemonics found in
# this firmware:  any instruction whose *last* operand is a register or a
# register pair and whose semantics is not "compare" or "test" modifies it.
# Callers (bal/jal/jalr) clobber the whole state and are handled before this.
NOT_WRITING = C.COND | C.RETS | {"cmpw", "cmpb", "cmpd", "tbit", "tbitw",
                                "tbitb", "cbitw", "cbitb", "sbitw", "sbitb"}
PAIR_OPS = {"movd", "addd", "subd", "andd", "ord", "xord", "ashud", "lshd",
            "muld", "loadd", "stord", "loadm", "loadmp", "storm"}
# These print the destination as the first operand.
WIDEN_FIRST_DEST = {"movzw", "movxw", "movzb", "movxb", "mulsw", "muluw",
                    "mulsb"}

TAIL_REG = re.compile(r"(?:,|^)(r\d+)$")
TAIL_PAIR = re.compile(r"(?:,|^)\((r\d+),(r\d+)\)$")


def written_registers(insn):
    """Return the set of registers the instruction may modify.

    Both halves of a written pair are returned, so any state keyed on either
    half is invalidated by the caller.  A memory instruction whose operand is
    a *destination* pair (`loadd ...,(rp)`, `loadm`) writes that pair; a memory
    instruction whose pair is the *source* (`storw r2,0x0:s(rp)`) writes
    nothing but the register it loads into.
    """
    mn = insn.mnemonic
    ops = insn.operands.replace(" ", "")
    if mn in C.CALLS or mn in NOT_WRITING:
        return set()
    # memory instructions: only the register operand is written.
    # (`ashud $1:s,(rp)` is not a memory access: the `:s` belongs to the
    # immediate, not to an address operand.)
    if mn in ACCESS:
        if mn.startswith("load"):
            for operand in split_operands(insn.operands):
                operand = operand.strip()
                m = re.fullmatch(r"(r\d+)", operand)
                if m:
                    return {m.group(1)}
                m = re.fullmatch(r"\((r\d+),(r\d+)\)", operand)
                if m:
                    return {m.group(1), m.group(2)}
        return set()
    # widening moves print their destination first: `movzw r3,(r7,r6)`
    # stores the zero-extended pair into r3.
    if mn in WIDEN_FIRST_DEST:
        m = re.match(r"^(r\d+),", ops)
        if m:
            return {m.group(1)}
        m = re.match(r"^\((r\d+),(r\d+)\),", ops)
        if m:
            return {m.group(1), m.group(2)}
        return set()
    m = TAIL_PAIR.search(ops)
    if m and mn in PAIR_OPS:
        return {m.group(1), m.group(2)}
    m = TAIL_REG.search(ops)
    if m:
        return {m.group(1)}
    return set()


def apply_instruction(state, insn):
    """Update the register state for one instruction (in place).

    Only two value forms are tracked: a 32-bit constant in a register pair and
    a 16-bit constant in a single register.  Every other write is UNKNOWN.
    """
    mn = insn.mnemonic
    ops = insn.operands.replace(" ", "")
    if mn in C.CALLS:
        state.clear()
        return

    # `movd $imm:l,(rp)` is the only way this analysis learns a 32-bit value
    m = MD_RE.match(ops)
    if m:
        hi, lo = m.group(2), m.group(3)
        for reg in written_registers(insn):
            if reg not in (hi, lo):
                invalidate(state, reg)
        set_pair(state, hi, lo, int(m.group(1), 16))
        return

    # `addd src,dst` computes dst := dst + src.  A numeric value survives
    # only when both sides are proven constants; otherwise the destination
    # stops being known.  The source is never modified.
    m = re.match(r"^\((r\d+),(r\d+)\),\((r\d+),(r\d+)\)$", ops)
    if m and mn == "addd":
        shi, slo, dhi, dlo = m.groups()
        src = pair_state(state, shi, slo)
        dst = pair_state(state, dhi, dlo)
        if src[0] == "KNOWN32" and dst[0] == "KNOWN32":
            set_pair(state, dhi, dlo, (dst[1] + src[1]) & 0xFFFFFFFF)
        else:
            invalidate(state, dhi)
            invalidate(state, dlo)
        return

    # any other write of a 16-bit constant: `movw $imm,rn`
    m = MV_RE.match(ops)
    if m:
        for reg in written_registers(insn):
            if reg != m.group(2):
                invalidate(state, reg)
        set_reg(state, m.group(2), int(m.group(1), 16))
        return

    for reg in written_registers(insn):
        invalidate(state, reg)


def write_back(state, insn):
    """Registers written by a memory access stop being known."""
    for reg in written_registers(insn):
        invalidate(state, reg)


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


def double(symbol):
    """Halve-safe doubling of a symbolic index: `2 * (2 * r1)` -> `4 * r1`."""
    m = re.match(r"^(\d+)\*(.+)$", symbol)
    if m:
        return f"{2 * int(m.group(1))}*{m.group(2)}"
    return f"2*{symbol}"


def _resolved_note(value):
    """Flag RESOLVED addresses that look unlike a real internal address."""
    if 0x01000000 <= value < 0x01000000 + 0x100000:
        return ""
    if 0x0F0000 <= value < 0x100000 or 0x00FF0000 <= value < 0x01000000:
        return ""
    if 0x000000 <= value < 0x00100000:
        return ""
    return ("address outside the known internal ranges; may be data decoded "
            "as code (see docs, 'unreliable RESOLVED')")


def scan(fw, image):
    """Return (rows, stats, unclassified)."""
    blocks = blocks_of(fw)
    mode_a, mode_b = reachability(fw)
    rows, unclassified = [], []
    for start in sorted(blocks):
        state = {}
        prov = {}
        sym = {}
        sym_base = {}
        for addr in blocks[start]:
            insn = fw.insns[addr]
            ops = insn.operands.replace(" ", "")
            written = written_registers(insn)

            # Symbolic index state, keyed by register pair.
            #
            # `sym` maps a pair to (expression, assumptions): the pair holds
            # `base + expression`, where the assumptions list the *index*
            # registers whose live value the expression depends on.  Any
            # write to a pair or to a live index register drops the entry, so
            # an expression can never outlive the value it names.
            # A pair whose expression is *re-derived* by the current
            # instruction (`movzw`/`movxw`/`ashud`/`addd` on that same pair)
            # is exempt from the clobber check below; every other write to
            # the pair or to a live index register drops the expression.
            rederived = set()
            m = re.match(r"^(r\d+),\((r\d+),(r\d+)\)$", ops)
            if m and insn.mnemonic in ("movzw", "movxw"):
                rederived.add((m.group(2), m.group(3)))
            m = re.match(r"^\$(?:0x1|1):s,\(([^)]+)\)$", ops)
            if m and insn.mnemonic == "ashud":
                regs = re.findall(r"r\d+", m.group(1))
                if len(regs) == 2:
                    rederived.add((regs[0], regs[1]))
            m = re.match(r"^\((r\d+),(r\d+)\),\((r\d+),(r\d+)\)$", ops)
            if m and insn.mnemonic == "addd":
                # the source pair keeps its expression (addd does not modify
                # it); the destination is re-derived only when it has one
                rederived.add((m.group(1), m.group(2)))
                if (m.group(1), m.group(2)) in sym:
                    rederived.add((m.group(3), m.group(4)))
            for pair in list(sym):
                expr, deps = sym[pair]
                if pair in rederived:
                    continue
                if written & (set(pair) | set(deps)):
                    del sym[pair]
                    sym_base.pop(pair, None)

            m = re.match(r"^(r\d+),\((r\d+),(r\d+)\)$", ops)
            if m and insn.mnemonic in ("movzw", "movxw"):
                # the pair now holds zero_extend16(rN); rN itself is an
                # assumption, not part of the pair being described
                sym[(m.group(2), m.group(3))] = (m.group(1), {m.group(1)})

            m = re.match(r"^\$(?:0x1|1):s,\(([^)]+)\)$", ops)
            if m and insn.mnemonic == "ashud":
                regs = re.findall(r"r\d+", m.group(1))
                if len(regs) == 2:
                    key = (regs[0], regs[1])
                    if key in sym:
                        expr, deps = sym[key]
                        sym[key] = (double(expr), set(deps) | set(key))

            m = re.match(r"^\((r\d+),(r\d+)\),\((r\d+),(r\d+)\)$", ops)
            if m and insn.mnemonic == "addd":
                # `addd src,dst`: dst := dst + src.  A symbolic index moves
                # from the source to the destination pair; a destination
                # without a symbolic source loses its expression.
                src = (m.group(1), m.group(2))
                dst = (m.group(3), m.group(4))
                if src in sym:
                    expr, deps = sym.pop(src)
                    # keep the destination's own base value for later; a
                    # symbolic store needs base + index, not the sum
                    base = pair_state(state, *dst)
                    sym[dst] = (expr, set(deps) | set(dst))
                    if base[0] == "KNOWN32":
                        sym_base[dst] = base[1]
                else:
                    sym.pop(dst, None)
                    sym_base.pop(dst, None)

            if insn.mnemonic in ACCESS:
                kind, width = ACCESS[insn.mnemonic]
                # A register pair is also a *value* (`stord (r1,r0),addr`
                # stores the pair), so the address operand is chosen by
                # direction: the first memory operand of a load is the
                # address, the last one of a store is.
                parsed, payload = None, None
                operands_list = split_operands(insn.operands)
                candidates = (operands_list if kind == "READ"
                              else list(reversed(operands_list)))
                for operand in candidates:
                    p = parse_memory_operand(operand)
                    if p and not (kind == "WRITE" and p[0] == "DISP_RP"
                                  and operand in operands_list[:1]
                                  and insn.mnemonic in ("stord", "storw", "storb")
                                  and parse_memory_operand(operands_list[-1])):
                        parsed, payload = p
                        break
                if parsed == "ABS":
                    value = abs_address(insn)
                    if value == payload:
                        rows.append(_row(image, addr, insn, kind, width,
                                         "RESOLVED", f"0x{value:08x}",
                                         [f"0x{addr:06x}"], None,
                                         mode_a, mode_b))
                    else:
                        rows.append(_row(image, addr, insn, kind, width,
                                         "UNKNOWN", None, [], None,
                                         mode_a, mode_b,
                                         "absolute field differs from "
                                         "the printed operand"))
                elif parsed == "DISP_RP":
                    disp, hi, lo = payload
                    st = pair_state(state, hi, lo)
                    entry = sym.get((hi, lo))
                    base = sym_base.get((hi, lo))
                    if entry and disp == 0 and base is not None:
                        expr = entry[0]
                        text = (f"0x{base:08x} + {expr}"
                                if expr.startswith(("2*", "4*", "8*"))
                                else f"0x{base:08x} + zero_extend16({expr})")
                        rows.append(_row(
                            image, addr, insn, kind, width, "SYMBOLIC",
                            None, prov.get((hi, lo), []), text,
                            mode_a, mode_b,
                            "base loaded by movd, index added by addd; "
                            "depends on " + ", ".join(sorted(entry[1]))))
                    elif st[0] == "KNOWN32":
                        value = (st[1] + disp) & 0xFFFFFFFF
                        rows.append(_row(image, addr, insn, kind, width,
                                         "RESOLVED", f"0x{value:08x}",
                                         prov.get((hi, lo), []), None,
                                         mode_a, mode_b,
                                         _resolved_note(value)))
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
                    elif reg == "ra":
                        # relative to the return address: address depends on
                        # the caller, never a peripheral address by itself
                        rows.append(_row(image, addr, insn, kind, width,
                                         "PC_RELATIVE", f"ra+{disp}", [],
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
