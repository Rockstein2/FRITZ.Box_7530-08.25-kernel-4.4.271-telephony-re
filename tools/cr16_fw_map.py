#!/usr/bin/env python3
"""Build an address map and a reachability-checked disassembly of SC14448 firmware.

Offline tool.  It parses the Intel HEX images, keeps every contiguous run
separate (never filling 0xFF between blocks), disassembles each run with the
correct VMA using an external cr16-elf objdump, and distinguishes
reachable code from linear-sweep noise.

Usage:
    python3 tools/cr16_fw_map.py FIRMWARE.hex [--objdump PATH]
                                    [--json OUT] [--asm OUT] [--entry ADDR]

The objdump must support CR16 (`objdump -i | grep cr16`).  Build one with:

    ./configure --target=cr16-elf && make all-binutils
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "mock"))
from piglet_image import parse_hex  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cr16_branch import branch_target, is_in_runs  # noqa: E402

DEFAULT_OBJDUMP = "/tmp/opencode/cr16/build/binutils/objdump"

# Peripheral windows the firmware may address.  These names are working
# hypotheses from the AVM/Dialog documentation, not established facts.
PERIPHERAL_WINDOWS = [
    (0xFF4800, 0xFF48FF, "GPIO (candidate)"),
    (0xFF4900, 0xFF49FF, "UART (candidate)"),
    (0xFF5400, 0xFF54FF, "interrupt controller (candidate)"),
    (0xFF5800, 0xFF58FF, "timer/platform (candidate)"),
    (0xFF6000, 0xFF60FF, "PCM/DMA (candidate)"),
    (0xFF7000, 0xFF70FF, "RF/analog (candidate)"),
]


@dataclass
class Run:
    start: int
    data: bytes

    @property
    def end(self) -> int:
        return self.start + len(self.data) - 1


@dataclass
class Insn:
    addr: int
    size: int
    text: str
    mnemonic: str
    operands: str


@dataclass
class Branch:
    addr: int
    kind: str          # call / jump / cond / ret
    target: int | None  # None for indirect
    indirect: bool


@dataclass
class RunMap:
    run: Run
    insns: list[Insn] = field(default_factory=list)
    branches: list[Branch] = field(default_factory=list)
    reachable: set[int] = field(default_factory=set)
    unreachable: list[int] = field(default_factory=list)


def load_runs(path: str) -> list[Run]:
    mem = parse_hex(path)
    if not mem:
        return []
    addrs = sorted(mem)
    runs: list[Run] = []
    start = addrs[0]
    buf = bytearray([mem[start]])
    prev = start
    for a in addrs[1:]:
        if a == prev + 1:
            buf.append(mem[a])
        else:
            runs.append(Run(start, bytes(buf)))
            start = a
            buf = bytearray([mem[a]])
        prev = a
    runs.append(Run(start, bytes(buf)))
    return runs


MD_RE = re.compile(r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2,}\s)+)\s*\t?(.*)$")


def disassemble(run: Run, objdump: str) -> RunMap:
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        f.write(run.data)
        tmp = f.name
    try:
        out = subprocess.run(
            [objdump, "-D", "-b", "binary", "-m", "cr16",
             f"--adjust-vma={run.start:#x}", tmp],
            capture_output=True, text=True, check=False).stdout
    finally:
        Path(tmp).unlink(missing_ok=True)

    rm = RunMap(run)
    pending: dict | None = None

    def flush(rec):
        if rec is None:
            return
        addr = rec["addr"]
        raw = rec["raw"]
        text = rec["text"]
        mnemonic = text.split()[0] if text else ""
        operands = text[len(mnemonic):].strip()
        rm.insns.append(Insn(addr, len(raw), text, mnemonic, operands))
        braw = bytes(raw)
        rm.branches.append(classify(addr, mnemonic, operands, braw))

    for line in out.splitlines():
        m = MD_RE.match(line)
        if not m:
            continue
        addr = int(m.group(1), 16)
        if addr < run.start or addr > run.end:
            continue
        raw = [int(x, 16) for x in m.group(2).split()]
        text = m.group(3).strip()

        if not text:
            # Continuation line: these bytes belong to the previous
            # instruction (CR16 has 2-, 4- and 6-byte forms, and objdump
            # prints the extra word on its own line with no mnemonic).
            if pending is not None and \
               addr == pending["addr"] + len(pending["raw"]):
                pending["raw"] += raw
                continue
            # A continuation with no owner cannot be trusted.
            flush(pending)
            pending = {"addr": addr, "raw": raw, "text": ""}
            continue

        flush(pending)
        pending = {"addr": addr, "raw": raw, "text": text}

    flush(pending)
    return rm


COND = {
    "beq", "bne", "blt", "ble", "bgt", "bge", "bhi", "bls",
    "beq0b", "beq0w", "bne0b", "bne0w", "bcs", "bcc", "bvs", "bvc",
}
JUMPS = {"br", "jump", "jmp", "bral"}
CALLS = {"bal", "jal", "jalr"}
RETS = {"popret", "ret", "retx"}


def target_from_operands(operands: str, addr: int = 0,
                         raw: bytes = b"") -> int | None:
    """Resolve a branch target.

    objdump prints the absolute target, with a sign prefix that only reflects
    the CR16 sign flag (see docs/history/fon-dialog-cr16-branches.md). The printed
    magnitude is therefore taken as the target, and where raw bytes are
    available the validated decoder is used instead.
    """
    if len(raw) >= 4 and raw[0] in (0x00, 0x02, 0xFF) and raw[1] == 0xC0:
        w0 = raw[0] | (raw[1] << 8)
        w1 = raw[2] | (raw[3] << 8)
        return branch_target(addr, (w0, w1))[0]
    m = re.search(r"\*([+-]0x[0-9a-f]+|[+-]\d+):[sbwm]", operands)
    if m:
        return abs(int(m.group(1), 0))
    m = re.search(r",\s*(0x[0-9a-f]+):[sbwm]", operands)
    if m:
        return int(m.group(1), 16)
    m = re.search(r"^\s*(0x[0-9a-f]+):", operands)
    if m:
        return int(m.group(1), 16)
    return None


def classify(addr: int, mnemonic: str, operands: str,
             raw: bytes = b"") -> Branch:
    indirect = bool(re.search(r"\((?:r|sp|ra)", operands)) and \
        not operands.strip().startswith("*")
    if mnemonic in CALLS:
        t = target_from_operands(operands, addr, raw)
        return Branch(addr, "call", t, t is None)
    if mnemonic in COND:
        t = target_from_operands(operands, addr, raw)
        return Branch(addr, "cond", t, t is None)
    if mnemonic in JUMPS:
        t = target_from_operands(operands, addr, raw)
        return Branch(addr, "jump", t, t is None or indirect)
    if mnemonic in RETS:
        return Branch(addr, "ret", None, True)
    return Branch(addr, "", None, indirect)


def reachable_set(rm: RunMap, entries: list[int]) -> set[int]:
    """Walk from the entries through direct and conditional branches."""
    by_addr = {i.addr: i for i in rm.insns}
    branches = {b.addr: b for b in rm.branches}
    seen: set[int] = set()
    stack = [e for e in entries if e in by_addr]
    while stack:
        a = stack.pop()
        while a in by_addr and a not in seen:
            seen.add(a)
            insn = by_addr[a]
            nxt = a + insn.size
            br = branches.get(a)
            if br and br.kind in ("call", "jump", "cond") and br.target:
                t = br.target if br.target > 0 else None
                if t and t in by_addr:
                    stack.append(t)
            if br and br.kind in ("jump", "ret") and not br.target:
                break
            if br and br.kind == "jump" and br.target:
                break
            a = nxt
    return seen


def peripheral_hits(runs: list[Run]) -> list[dict]:
    hits = []
    for run in runs:
        for i in range(len(run.data) - 5):
            # movd $imm32:l,(r1,r0) is 0x70 0x00 plus a word-swapped imm
            if run.data[i] != 0x70 or run.data[i + 1] != 0x00:
                continue
            b = run.data[i + 2:i + 6]
            val = (b[1] << 24) | (b[0] << 16) | (b[3] << 8) | b[2]
            for lo, hi, name in PERIPHERAL_WINDOWS:
                if lo <= val <= hi:
                    hits.append({"addr": run.start + i,
                                 "peripheral": val,
                                 "window": name})
    return hits


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("hexfile")
    ap.add_argument("--objdump", default=DEFAULT_OBJDUMP)
    ap.add_argument("--json")
    ap.add_argument("--asm")
    ap.add_argument("--entry", action="append", default=[],
                    help="entry address (may be repeated); default = run start")
    args = ap.parse_args(argv[1:])

    if not Path(args.objdump).exists():
        print(f"objdump not found: {args.objdump}", file=sys.stderr)
        return 2

    runs = load_runs(args.hexfile)
    maps = [disassemble(r, args.objdump) for r in runs]
    entries = [int(e, 0) for e in args.entry]

    summary = []
    asm_lines = []
    for rm in maps:
        ents = [e for e in entries] or [rm.run.start]
        rm.reachable = reachable_set(rm, ents)
        rm.unreachable = [i.addr for i in rm.insns
                          if i.addr not in rm.reachable]
        calls = [b for b in rm.branches if b.kind == "call"]
        conds = [b for b in rm.branches if b.kind == "cond"]
        indirect = [b for b in rm.branches if b.indirect and b.kind]
        summary.append({
            "start": rm.run.start,
            "end": rm.run.end,
            "bytes": len(rm.run.data),
            "insns": len(rm.insns),
            "reachable": len(rm.reachable),
            "calls": len(calls),
            "cond": len(conds),
            "indirect": len(indirect),
        })
        asm_lines.append(f"\n; === run {rm.run.start:#08x}-{rm.run.end:#08x}"
                         f" ({len(rm.run.data)} bytes) ===")
        for i in rm.insns:
            mark = "" if i.addr in rm.reachable else "  ; UNREACHED"
            asm_lines.append(f"{i.addr:08x}: {i.text}{mark}")

    print(f"=== {args.hexfile} ===")
    print(f"runs: {len(maps)}")
    for s in summary:
        print(f"  {s['start']:#08x}-{s['end']:#08x}  "
              f"{s['bytes']:6d} B  insns {s['insns']:5d}  "
              f"reach {s['reachable']:5d}  calls {s['calls']:3d}  "
              f"cond {s['cond']:3d}  indirect {s['indirect']:3d}")

    hits = peripheral_hits(runs)
    print(f"peripheral immediates: {len(hits)}")
    for h in hits:
        print(f"  {h['addr']:#08x} -> {h['peripheral']:#010x}  {h['window']}")

    if args.json:
        Path(args.json).write_text(json.dumps({
            "firmware": args.hexfile,
            "runs": summary,
            "peripherals": hits,
        }, indent=2))
    if args.asm:
        Path(args.asm).write_text("\n".join(asm_lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
