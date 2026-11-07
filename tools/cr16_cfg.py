#!/usr/bin/env python3
"""Global CR16 control-flow graph for the SC14448 firmware images.

Replaces the per-run reachability of `cr16_fw_map.py` with one CFG over all
loaded runs.

Three quantities are kept strictly separate, as required:

    instruction_address   where the instruction starts
    branch_target         the resolved address, or None when unknown
    edge category         why the edge exists and how far it is proven

Edge categories
---------------

    DIRECT_RESOLVED          decoded from the instruction encoding and the
                             target lies on an instruction boundary inside a
                             loaded run
    DIRECT_UNSUPPORTED       the instruction is a known control-transfer form
                             whose encoding is not implemented; no target is
                             invented
    INDIRECT_REGISTER        call/jump through a register or a computed
                             address; target unknown
    INDIRECT_TABLE_RESOLVED  an indirect transfer whose target was recovered
                             from a located table
    INDIRECT_UNRESOLVED      indirect transfer with no recovered table
    FALLTHROUGH_UNRESOLVED   the next address is not a decoded instruction
                             start (e.g. data gap); the path is lost
    OUTSIDE_LOADED_IMAGE     a direct target outside every loaded run
    TARGET_NOT_INSTRUCTION   a direct target inside a run but not on an
                             instruction boundary

Fallthrough rules
-----------------

    call                 next address (return site)   DIRECT_RESOLVED
    conditional branch   next address (fallthrough)   DIRECT_RESOLVED
    unconditional jump   none
    return               none
    indirect jump/call   no fallthrough is invented for jumps; a register
                         call still returns to the next address

Reachability modes
------------------

    A. single candidate   one starting address, status `candidate`
    B. all candidates     every heuristically detected entry, research mode
    C. verified entries   only entries confirmed by loader or vector table

`verified=True` is never assigned heuristically.  Mode C is empty until an
independent confirmation exists.

This module performs static analysis only.  It does not touch hardware.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent / "src" / "mock"))

from piglet_image import parse_hex  # noqa: E402
from cr16_branch import (  # noqa: E402
    UnsupportedEncoding,
    decode_insn,
    is_in_runs,
)

COND = {
    "beq", "bne", "blt", "ble", "bgt", "bge", "bhi", "bls", "blo", "bhs",
    "beq0b", "beq0w", "bne0b", "bne0w", "bcs", "bcc", "bvs", "bvc",
    "bfc", "bfs",
}
# `br` is the unconditional relative branch: CR16A manual, "BR (Unconditional
# Branch)" — it loads the sign-extended displacement plus PC into PC and
# execution continues at the destination.  It carries no link register, so it
# is a jump, not a call, and it has no fall-through.  objdump prints it with
# the same `dispe9`/`disps17` field as the conditionals because `br` is the
# condition code 14 (0xE) of the same Bcond opcode family; the encoding is
# shared, the control-flow meaning is not.
JUMPS = {"br", "jump", "jmp", "bral"}
CALLS = {"bal", "jal", "jalr"}
RETS = {"popret", "ret", "retx"}
# Indirect forms: call or jump through a register operand.
INDIRECT_MN = {"jalr", "jump", "jmp", "bral", "ret", "retx"}

# Edge categories
DIRECT_RESOLVED = "DIRECT_RESOLVED"
DIRECT_UNSUPPORTED = "DIRECT_UNSUPPORTED"
INDIRECT_REGISTER = "INDIRECT_REGISTER"
INDIRECT_TABLE_RESOLVED = "INDIRECT_TABLE_RESOLVED"
INDIRECT_UNRESOLVED = "INDIRECT_UNRESOLVED"
FALLTHROUGH_UNRESOLVED = "FALLTHROUGH_UNRESOLVED"
OUTSIDE_LOADED_IMAGE = "OUTSIDE_LOADED_IMAGE"
TARGET_NOT_INSTRUCTION = "TARGET_NOT_INSTRUCTION"

CATEGORIES = (
    DIRECT_RESOLVED, DIRECT_UNSUPPORTED, INDIRECT_REGISTER,
    INDIRECT_TABLE_RESOLVED, INDIRECT_UNRESOLVED, FALLTHROUGH_UNRESOLVED,
    OUTSIDE_LOADED_IMAGE, TARGET_NOT_INSTRUCTION,
)

# Categories that are proven enough to move reachability along.
FOLLOWED = {DIRECT_RESOLVED}

# Historical aliases kept so older callers keep working.
VERIFIED_DIRECT = DIRECT_RESOLVED
VERIFIED_INDIRECT = INDIRECT_TABLE_RESOLVED
CANDIDATE = TARGET_NOT_INSTRUCTION
UNRESOLVED = INDIRECT_REGISTER


@dataclass
class Insn:
    addr: int
    size: int
    mnemonic: str
    operands: str
    raw: bytes

    @property
    def end(self) -> int:
        return self.addr + self.size


@dataclass
class Edge:
    src: int
    dst: int | None
    kind: str            # call / cond / jump / fallthrough / indirect
    category: str
    reason: str = ""

    # Old name, so existing code and tests keep reading.
    @property
    def confidence(self) -> str:
        return self.category


@dataclass
class Entry:
    addr: int
    origin: str
    verified: bool = False


@dataclass
class Firmware:
    runs: list[tuple[int, bytes]]
    insns: dict[int, Insn] = field(default_factory=dict)
    stale: dict[int, bytes] = field(default_factory=dict)

    def in_run(self, addr: int) -> bool:
        return any(lo <= addr < lo + len(d) for lo, d in self.runs)

    def run_of(self, addr: int):
        for lo, d in self.runs:
            if lo <= addr < lo + len(d):
                return lo, d
        return None

    def run_bounds(self) -> list[tuple[int, int]]:
        return [(lo, lo + len(d) - 1) for lo, d in self.runs]


def load(hexfile: str) -> Firmware:
    mem = parse_hex(hexfile)
    addrs = sorted(mem)
    runs: list[tuple[int, bytes]] = []
    if addrs:
        start = addrs[0]
        buf = bytearray([mem[start]])
        prev = start
        for a in addrs[1:]:
            if a == prev + 1:
                buf.append(mem[a])
            else:
                runs.append((start, bytes(buf)))
                start = a
                buf = bytearray([mem[a]])
            prev = a
        runs.append((start, bytes(buf)))
    return Firmware(runs)


MD_RE = __import__("re").compile(
    r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2,}\s)+)\s*\t?(.*)$")


def disassemble(fw: Firmware, objdump: str) -> None:
    """Fill fw.insns with validated instruction records for every run.

    objdump prints a 6-byte instruction on two lines; the second line has no
    mnemonic and is merged back into the first.  Continuation lines must not
    become separate instructions, otherwise they would appear as bogus
    fallthrough targets.
    """
    import subprocess
    import tempfile

    for lo, data in fw.runs:
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            f.write(data)
            tmp = f.name
        try:
            out = subprocess.run(
                [objdump, "-D", "-b", "binary", "-m", "cr16",
                 f"--adjust-vma={lo:#x}", tmp],
                capture_output=True, text=True, check=False).stdout
        finally:
            Path(tmp).unlink(missing_ok=True)

        pending = None

        def flush(rec):
            if rec is None:
                return
            raw = bytes(rec["raw"])
            text = rec["text"]
            mn = text.split()[0] if text else ""
            ops = text[len(mn):].strip()
            fw.insns[rec["addr"]] = Insn(rec["addr"], len(raw), mn, ops, raw)

        for line in out.splitlines():
            m = MD_RE.match(line)
            if not m:
                continue
            addr = int(m.group(1), 16)
            raw = [int(x, 16) for x in m.group(2).split()]
            text = m.group(3).strip()
            if not text:
                if pending is not None and \
                   addr == pending["addr"] + len(pending["raw"]):
                    pending["raw"] += raw
                    continue
                flush(pending)
                pending = {"addr": addr, "raw": raw, "text": ""}
                continue
            flush(pending)
            pending = {"addr": addr, "raw": raw, "text": text}
        flush(pending)


def _classify_target(fw: Firmware, t: int) -> tuple[str, str]:
    """Category and reason for a decoded direct target."""
    if not fw.in_run(t):
        return OUTSIDE_LOADED_IMAGE, "target outside every loaded run"
    if t in fw.insns:
        return DIRECT_RESOLVED, "target on an instruction boundary"
    return TARGET_NOT_INSTRUCTION, (
        "target inside a run but not on an instruction boundary")


def _is_register_operands(ops: str) -> bool:
    """True when every operand is a bare register or register pair.

    `jal (r7,r6)` has one operand `(r7,r6)`; `jal (ra),0x1234` has a memory
    operand and a displacement and is a direct call.
    """
    ops = ops.strip()
    if not ops:
        return False
    if "," in ops and not ops.endswith(")"):
        return False
    return ops.startswith("(") and ops.endswith(")") and "0x" not in ops


def classify_insn(insn: Insn, fw: Firmware) -> list[Edge]:
    """Non-fallthrough edges leaving one instruction."""
    mn = insn.mnemonic
    edges: list[Edge] = []

    if mn in COND or mn in CALLS or mn in JUMPS:
        kind = "call" if mn in CALLS else ("cond" if mn in COND else "jump")
        # A register-indirect form has no immediate field.
        if "(" in insn.operands and mn in INDIRECT_MN:
            return [Edge(insn.addr, None, "indirect", INDIRECT_REGISTER,
                         f"{mn} with a register operand")]
        if mn == "jal" and _is_register_operands(insn.operands):
            return [Edge(insn.addr, None, "indirect", INDIRECT_REGISTER,
                         "jal with a register operand")]
        try:
            t, form, status = decode_insn(insn.addr, insn.mnemonic,
                                          insn.raw[:min(6, insn.size)])
        except UnsupportedEncoding:
            t, form, status = None, "?", "UNSUPPORTED"
        if status != "DIRECT" or t is None:
            return [Edge(insn.addr, None, kind, DIRECT_UNSUPPORTED,
                         f"{mn} {insn.raw.hex(' ')}: encoding not implemented")]
        cat, why = _classify_target(fw, t)
        if cat == DIRECT_RESOLVED:
            why = f"{form}: {why}"
        return [Edge(insn.addr, t, kind, cat, why)]

    if mn in RETS:
        return []
    return []


def has_fallthrough(insn: Insn) -> bool:
    """Calls continue after return; conditional branches have both paths.

    `jump (rp)` and `jal (rp)` are register-indirect: their target is unknown,
    so no continuation is invented for the jump.
    """
    mn = insn.mnemonic
    if mn in RETS or mn == "illegal":
        return False
    if mn in JUMPS:
        return False
    if mn in COND:
        return True
    if mn in CALLS:
        return True
    return True


def build(fw: Firmware) -> list[Edge]:
    edges: list[Edge] = []
    for addr in sorted(fw.insns):
        insn = fw.insns[addr]
        edges.extend(classify_insn(insn, fw))
        if has_fallthrough(insn):
            nxt = insn.end
            if nxt in fw.insns:
                edges.append(Edge(addr, nxt, "fallthrough", DIRECT_RESOLVED,
                                  "next address"))
            elif fw.in_run(nxt):
                edges.append(Edge(addr, nxt, "fallthrough",
                                  FALLTHROUGH_UNRESOLVED,
                                  "next address is not an instruction start"))
            else:
                edges.append(Edge(addr, None, "fallthrough",
                                  FALLTHROUGH_UNRESOLVED,
                                  "next address leaves the loaded runs"))
    return edges


def successors(edges: list[Edge], followed: set[str] = FOLLOWED) -> dict[int, list[int]]:
    succ: dict[int, list[int]] = {}
    for e in edges:
        if e.dst is None or e.category not in followed:
            continue
        succ.setdefault(e.src, []).append(e.dst)
    return succ


def reachable(fw: Firmware, edges: list[Edge],
              entries: list[Entry],
              min_depth: int = 1) -> dict[int, int]:
    """BFS over followed edges from the given starting addresses.

    `min_depth` is the maximum path length to walk; the historical default of
    1 preserved the old partial result, so callers that want full
    reachability must pass a large value (see `reach_all`).
    """
    succ = successors(edges)
    seen: dict[int, int] = {}
    frontier = [e.addr for e in entries if e.addr in fw.insns]
    depth = 0
    while frontier and depth < min_depth:
        nxt = []
        for a in frontier:
            if a in seen:
                continue
            seen[a] = depth
            nxt.extend(succ.get(a, ()))
        frontier = nxt
        depth += 1
    return seen


def reach_all(fw: Firmware, edges: list[Edge],
              starts: list[int]) -> dict[int, int]:
    """Full BFS; returns address -> shortest hop count from any start."""
    succ = successors(edges)
    seen: dict[int, int] = {}
    frontier = [a for a in starts if a in fw.insns]
    depth = 0
    while frontier:
        nxt = []
        for a in frontier:
            if a in seen:
                continue
            seen[a] = depth
            nxt.extend(succ.get(a, ()))
        frontier = nxt
        depth += 1
    return seen


def heuristic_entries(fw: Firmware, edges: list[Edge]) -> list[Entry]:
    """Entry candidates: direct call targets that are not reached otherwise.

    A target is excluded when it is reached by a fallthrough edge or when it
    lies inside the body of another decoded instruction (a mid-instruction
    address cannot be an instruction start).

    These are `verified=False` by construction.  They are a research aid,
    not proof of execution, and `0x1602` is *not* among them: it is reached
    by fallthrough from `0x15fe` (`lpr r1,psr`), so it is an ordinary
    instruction, not a function root.
    """
    fall_into = {e.dst for e in edges if e.kind == "fallthrough"}
    interior: set[int] = set()
    for a, i in fw.insns.items():
        if i.size > 2:
            interior.update(range(a + 2, a + i.size, 2))
    targets = {e.dst for e in edges
               if e.kind == "call" and e.dst is not None
               and e.category == DIRECT_RESOLVED}
    cand = sorted(t for t in targets
                  if t not in fall_into and t not in interior
                  and t in fw.insns)
    return [Entry(t, "call target not reached otherwise", False)
            for t in cand]


def verified_entries() -> list[Entry]:
    """Entries confirmed by a loader, vector table or other independent proof.

    None is known at present: no loader has been read and no vector table has
    been located.  Mode C is therefore empty on purpose.
    """
    return []


@dataclass
class ModeResult:
    name: str
    entries: list[Entry]
    reached: dict[int, int]

    @property
    def count(self) -> int:
        return len(self.reached)


def run_modes(fw: Firmware, edges: list[Edge],
              single: int | None = 0x1602) -> dict[str, ModeResult]:
    """Run reachability modes A, B and C."""
    out: dict[str, ModeResult] = {}
    ents_a = ([Entry(single, "single candidate", False)]
              if single is not None else [])
    out["A"] = ModeResult("A", ents_a,
                          reach_all(fw, edges, [e.addr for e in ents_a]))
    ents_b = heuristic_entries(fw, edges)
    out["B"] = ModeResult("B", ents_b,
                          reach_all(fw, edges, [e.addr for e in ents_b]))
    ents_c = verified_entries()
    out["C"] = ModeResult("C", ents_c,
                          reach_all(fw, edges, [e.addr for e in ents_c]))
    return out


def find_indirect_tables(fw: Firmware, targets: set[int]) -> list[dict]:
    """Look for aligned 16-bit words whose value is a known instruction."""
    hits = []
    for lo, data in fw.runs:
        for i in range(0, len(data) - 1, 2):
            v = data[i] | (data[i + 1] << 8)
            if v in targets:
                a = lo + i
                inside = False
                for start in range(a - 5, a + 1):
                    ins = fw.insns.get(start)
                    if ins and ins.addr <= a < ins.end:
                        inside = True
                        break
                hits.append({"addr": a, "value": v, "in_insn": inside})
    return hits


def category_stats(edges: list[Edge]) -> dict[str, int]:
    """Count of edges in each category, plus totals."""
    st = {c: 0 for c in CATEGORIES}
    for e in edges:
        st[e.category] = st.get(e.category, 0) + 1
    st["TOTAL"] = len(edges)
    return st


def stats(fw: Firmware, edges: list[Edge], reached: dict[int, int]) -> dict:
    runs = fw.run_bounds()
    direct_calls = [e for e in edges
                    if e.kind == "call" and e.dst is not None
                    and e.category == DIRECT_RESOLVED]
    cross = [e for e in direct_calls
             if fw.run_of(e.src) and fw.run_of(e.dst) and
             fw.run_of(e.src)[0] != fw.run_of(e.dst)[0]]
    out = {
        "blocks": len(runs),
        "decoded": len(fw.insns),
        "reachable": len(reached),
        "direct_calls": len(direct_calls),
        "cross_block_calls": len(cross),
        "categories": category_stats(edges),
    }
    # Historical keys kept, now mapped to their true categories.
    out["indirect_unresolved"] = (out["categories"][INDIRECT_REGISTER] +
                                  out["categories"][INDIRECT_UNRESOLVED])
    out["invalid_targets"] = out["categories"][TARGET_NOT_INSTRUCTION]
    return out
