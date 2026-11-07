#!/usr/bin/env python3
"""Global CR16 control-flow graph for the SC14448 firmware images.

Replaces the per-run reachability of `cr16_fw_map.py` with a single CFG over
all loaded runs, with explicit edge confidence and explicit entry points.

Concepts kept separate, as required:

    instruction_address   where the instruction starts
    branch_displacement   the raw field, decoded by cr16_branch
    branch_target         the resolved address, or None when unknown

Edge confidence:

    VERIFIED_DIRECT    target computed from the encoding and lands on an
                       instruction boundary inside a loaded run
    VERIFIED_INDIRECT  target comes from a table whose reader and index
                       arithmetic were located
    CANDIDATE          plausible but not anchored (e.g. a computed target that
                       lands on data, or an indirect call with no table)
    UNRESOLVED         target unknown (register-indirect, no table found)

Entry points are never assigned automatically from a run start.  They are
declared by the caller or derived from an explicit, documented rule.

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
from cr16_branch import branch_target, is_in_runs  # noqa: E402

COND = {
    "beq", "bne", "blt", "ble", "bgt", "bge", "bhi", "bls", "blo", "bhs",
    "beq0b", "beq0w", "bne0b", "bne0w", "bcs", "bcc", "bvs", "bvc",
    "bfc", "bfs", "bswaplo", "bswaphi",
}
JUMPS = {"br", "jump", "jmp", "bral"}
CALLS = {"bal", "jal", "jalr"}
RETS = {"popret", "ret", "retx"}

VERIFIED_DIRECT = "VERIFIED_DIRECT"
VERIFIED_INDIRECT = "VERIFIED_INDIRECT"
CANDIDATE = "CANDIDATE"
UNRESOLVED = "UNRESOLVED"


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
    kind: str            # call / cond / jump / fallthrough
    confidence: str
    reason: str = ""


@dataclass
class Entry:
    addr: int
    origin: str
    verified: bool


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
    """Fill fw.insns with validated instruction records for every run."""
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


def _imm_disp(raw: bytes) -> int | None:
    """Displacement field of a 2- or 3-word CR16 branch, or None."""
    if len(raw) not in (4, 6):
        return None
    w = [raw[i] | (raw[i + 1] << 8) for i in range(0, len(raw), 2)]
    try:
        return branch_target(0, tuple(w))[0]
    except Exception:
        return None


def classify_insn(insn: Insn, fw: Firmware) -> list[Edge]:
    """Edges leaving one instruction, excluding fallthrough."""
    mn = insn.mnemonic
    edges: list[Edge] = []

    def direct_target() -> tuple[int | None, str]:
        if len(insn.raw) in (4, 6):
            w = [insn.raw[i] | (insn.raw[i + 1] << 8)
                 for i in range(0, len(insn.raw), 2)]
            t, _ = branch_target(insn.addr, tuple(w))
            return t, "decoded from the immediate field"
        return None, "no immediate field of a known length"

    if mn in CALLS or mn in JUMPS or mn in COND:
        t, why = direct_target()
        kind = "call" if mn in CALLS else ("cond" if mn in COND else "jump")
        if t is None:
            edges.append(Edge(insn.addr, None, kind, UNRESOLVED, why))
            return edges
        if not fw.in_run(t):
            edges.append(Edge(insn.addr, t, kind, CANDIDATE,
                              "target outside every loaded run"))
        elif t in fw.insns:
            edges.append(Edge(insn.addr, t, kind, VERIFIED_DIRECT, why))
        else:
            edges.append(Edge(insn.addr, t, kind, CANDIDATE,
                              "target lands inside a run but not on an "
                              "instruction boundary"))
        return edges

    if mn in RETS:
        return edges                      # return: no fallthrough
    return edges


def has_fallthrough(insn: Insn) -> bool:
    return not (insn.mnemonic in JUMPS or insn.mnemonic in RETS)


def build(fw: Firmware) -> list[Edge]:
    edges: list[Edge] = []
    for addr in sorted(fw.insns):
        insn = fw.insns[addr]
        edges.extend(classify_insn(insn, fw))
        if has_fallthrough(insn):
            nxt = insn.end
            if nxt in fw.insns:
                edges.append(Edge(addr, nxt, "fallthrough",
                                  VERIFIED_DIRECT, "next address"))
            elif fw.in_run(nxt):
                edges.append(Edge(addr, nxt, "fallthrough", CANDIDATE,
                                  "next address is not an instruction start"))
            else:
                edges.append(Edge(addr, None, "fallthrough", UNRESOLVED,
                                  "next address leaves the run"))
    return edges


def reachable(fw: Firmware, edges: list[Edge],
              entries: list[Entry]) -> dict[int, int]:
    """BFS from the verified entries; returns address -> depth."""
    succ: dict[int, list[int]] = {}
    for e in edges:
        if e.dst is None:
            continue
        if e.confidence not in (VERIFIED_DIRECT, VERIFIED_INDIRECT):
            continue
        succ.setdefault(e.src, []).append(e.dst)

    seen: dict[int, int] = {}
    frontier = [e.addr for e in entries if e.verified and e.addr in fw.insns]
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


def find_indirect_tables(fw: Firmware, targets: set[int]) -> list[dict]:
    """Look for aligned 16-bit words whose value is a known instruction."""
    hits = []
    for lo, data in fw.runs:
        for i in range(0, len(data) - 1, 2):
            v = data[i] | (data[i + 1] << 8)
            if v in targets:
                # reject matches that sit inside a decoded instruction
                a = lo + i
                inside = False
                for start in range(a - 5, a + 1):
                    ins = fw.insns.get(start)
                    if ins and ins.addr <= a < ins.end:
                        inside = True
                        break
                hits.append({"addr": a, "value": v, "in_insn": inside})
    return hits


def stats(fw: Firmware, edges: list[Edge], reached: dict[int, int]) -> dict:
    runs = fw.run_bounds()
    direct_calls = [e for e in edges
                    if e.kind == "call" and e.dst is not None]
    cross = [e for e in direct_calls
             if fw.run_of(e.src) and fw.run_of(e.dst) and
             fw.run_of(e.src)[0] != fw.run_of(e.dst)[0]]
    return {
        "blocks": len(runs),
        "decoded": len(fw.insns),
        "reachable": len(reached),
        "direct_calls": len(direct_calls),
        "cross_block_calls": len(cross),
        "indirect_unresolved": len([e for e in edges
                                    if e.confidence == UNRESOLVED]),
        "invalid_targets": len([e for e in edges
                                if e.confidence == CANDIDATE and
                                e.dst is not None]),
    }
