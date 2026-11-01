#!/usr/bin/env python3
"""Annotated ELF disassembly helper for the AVM pcmlink analysis.

This script is intentionally analysis-only.  It never loads or executes the
module.  It reads an ARM ELF, prints symbols/relocations, and disassembles a
function with PC-relative literals and relocation targets annotated.

Requirements:
    python3 -m venv .venv-analysis
    .venv-analysis/bin/pip install -r tools/requirements.txt

Examples:
    .venv-analysis/bin/python tools/pcmlink_regs.py \
        --module modules/ubik2/pcmlink.ko --list 'pcmlink_ul'
    .venv-analysis/bin/python tools/pcmlink_regs.py \
        --module modules/ubik2/pcmlink.ko --disasm pcmlink_ul_writeregister
    .venv-analysis/bin/python tools/pcmlink_regs.py \
        --module modules/ubik2/pcmlink.ko --disasm 0x9710 --length 0x400
    .venv-analysis/bin/python tools/pcmlink_regs.py \
        --module modules/ubik2/pcmlink.ko --metadata
    .venv-analysis/bin/python tools/pcmlink_regs.py \
        --module modules/ubik2/pcmlink.ko --xrefs FPGALink_SharedMemory
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
from pathlib import Path

try:
    from elftools.elf.elffile import ELFFile
except ImportError as exc:  # pragma: no cover
    sys.exit("missing pyelftools; install tools/requirements.txt in a venv")
try:
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN
except ImportError as exc:  # pragma: no cover
    sys.exit("missing capstone; install tools/requirements.txt in a venv")


def open_elf(path: Path):
    fh = path.open("rb")
    elf = ELFFile(fh)
    return fh, elf


def text_section(elf):
    return elf.get_section_by_name(".text")


def symbol_by_name(elf, name: str):
    for sec in elf.iter_sections():
        if sec["sh_type"] not in ("SHT_SYMTAB", "SHT_DYNSYM"):
            continue
        for sym in sec.iter_symbols():
            if sym.name == name:
                return sym
    return None


def symbols(elf, pattern: str | None):
    rows = []
    for sec in elf.iter_sections():
        if sec["sh_type"] not in ("SHT_SYMTAB", "SHT_DYNSYM"):
            continue
        for sym in sec.iter_symbols():
            if not sym.name:
                continue
            if pattern and not re.search(pattern, sym.name, re.I):
                continue
            if sym["st_value"] == 0 and sym["st_size"] == 0:
                continue
            rows.append((sym["st_value"], sym["st_size"], sym["st_info"]["type"], sym.name))
    for value, size, typ, name in sorted(rows):
        print(f"{value:#08x} {size:#06x} {typ:7s} {name}")


def reloc_map(elf):
    """Return address -> list of (reloc-type, symbol-name, addend).

    For ARM REL relocations the addend is the word at the relocated address.
    The module is REL, not RELA, so read the in-place addend where possible.
    """
    result = {}
    for sec in elf.iter_sections():
        if not sec.name.startswith(".rel"):
            continue
        symtab = elf.get_section(sec["sh_link"])
        for rel in sec.iter_relocations():
            sym = symtab.get_symbol(rel["r_info_sym"])
            off = rel["r_offset"]
            result.setdefault(off, []).append((rel["r_info_type"], sym.name))
    return result


def section_for_addr(elf, addr: int):
    for sec in elf.iter_sections():
        start = sec["sh_addr"]
        end = start + sec["sh_size"]
        if sec["sh_flags"] & 0x2 and start <= addr < end:
            return sec
    return None


def read_u32(elf, addr: int):
    sec = section_for_addr(elf, addr)
    if sec is None or sec["sh_type"] == "SHT_NOBITS":
        return None
    off = addr - sec["sh_addr"]
    if off + 4 > len(sec.data()):
        return None
    return struct.unpack_from("<I", sec.data(), off)[0]


def resolve_pc_literal(insn):
    """Resolve the common ARM `ldr rX, [pc, #imm]` literal address."""
    m = re.search(r"\[pc, #(0x[0-9a-f]+|\d+)\]", insn.op_str)
    if not m:
        return None
    # ARM PC reads as instruction address + 8.
    return insn.address + 8 + int(m.group(1), 0)


def disasm(elf, relocs, addr: int, length: int):
    text = text_section(elf)
    if text is None:
        sys.exit("no .text section")
    if not (text["sh_addr"] <= addr < text["sh_addr"] + text["sh_size"]):
        sys.exit(f"address {addr:#x} is outside .text")
    offset = addr - text["sh_addr"]
    data = text.data()[offset:offset + length]
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
    md.detail = True
    for insn in md.disasm(data, addr):
        notes = []
        for typ, sym in relocs.get(insn.address, []):
            if sym:
                notes.append(f"reloc {sym}")
        lit = resolve_pc_literal(insn)
        if lit is not None:
            word = read_u32(elf, lit)
            if word is not None:
                notes.append(f"lit@{lit:#x}=0x{word:08x}")
            for typ, sym in relocs.get(lit, []):
                if sym:
                    notes.append(f"lit-reloc {sym}")
        note = ("  ; " + ", ".join(notes)) if notes else ""
        print(f"{insn.address:08x}: {insn.bytes.hex():8s} {insn.mnemonic:8s} {insn.op_str}{note}")


def find_function(elf, name_or_addr: str):
    if name_or_addr.lower().startswith("0x"):
        return int(name_or_addr, 16), None
    sym = symbol_by_name(elf, name_or_addr)
    if sym is None:
        sys.exit(f"symbol not found: {name_or_addr}")
    return sym["st_value"], sym["st_size"] or 0x100


def xrefs(elf, relocs, name: str):
    found = False
    for addr, entries in sorted(relocs.items()):
        for typ, sym in entries:
            if sym == name:
                print(f"{addr:#08x} type={typ} -> {sym}")
                found = True
    if not found:
        print(f"no relocation references {name}")


def metadata(elf):
    """Print the 26 x 0x14 register metadata records at .rodata+0x58c."""
    ro = elf.get_section_by_name(".rodata")
    if ro is None:
        sys.exit("no .rodata")
    base = 0x58C
    data = ro.data()
    print("pcmlink virtual-register metadata (26 records, 0x14 bytes each)")
    print("idx reg  word0(read_mask) word1 word2 word3 word4")
    for i in range(26):
        off = base + i * 0x14
        words = struct.unpack_from("<5I", data, off)
        print(f"{i:02d}  {i*4:#04x}  " + " ".join(f"{w:08x}" for w in words))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--module", default="modules/ubik2/pcmlink.ko")
    ap.add_argument("--list", metavar="REGEX", nargs="?", const=".", help="list matching symbols")
    ap.add_argument("--disasm", metavar="SYMBOL_OR_ADDR")
    ap.add_argument("--length", type=lambda x: int(x, 0), default=0x100)
    ap.add_argument("--xrefs", metavar="SYMBOL")
    ap.add_argument("--metadata", action="store_true")
    args = ap.parse_args()

    path = Path(args.module)
    if not path.exists():
        sys.exit(f"module not found: {path}")
    fh, elf = open_elf(path)
    try:
        relocs = reloc_map(elf)
        if args.list is not None:
            symbols(elf, args.list if args.list != "." else None)
        if args.disasm:
            addr, size = find_function(elf, args.disasm)
            length = args.length
            if args.length == 0x100 and size:
                length = size
            disasm(elf, relocs, addr, length)
        if args.xrefs:
            xrefs(elf, relocs, args.xrefs)
        if args.metadata:
            metadata(elf)
    finally:
        fh.close()


if __name__ == "__main__":
    main()
