#!/usr/bin/env python3
"""Disassemble selected ELF32 ARM sections with symbols and relocations."""
import sys
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN

path = sys.argv[1]
want = sys.argv[2:] or ['.text', '.init.text', '.exit.text', '.text.unlikely']

with open(path, 'rb') as f:
    elf = ELFFile(f)
    symtab = elf.get_section_by_name('.symtab')
    syms = []
    for s in symtab.iter_symbols():
        if s['st_info']['type'] in ('STT_FUNC', 'STT_OBJECT', 'STT_NOTYPE') and s['st_size']:
            syms.append(s)
    relocs = {}
    for sec in elf.iter_sections():
        if sec['sh_type'] not in ('SHT_REL', 'SHT_RELA'):
            continue
        target = sec['sh_info']
        for r in sec.iter_relocations():
            sym = symtab.get_symbol(r['r_info_sym']) if symtab else None
            name = sym.name if sym else ''
            relocs.setdefault(target, {})[r['r_offset']] = (name, r['r_info_type'])
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
    md.detail = False
    sec_index = {sec.name: i for i, sec in enumerate(elf.iter_sections())}
    for name in want:
        sec = elf.get_section_by_name(name)
        if sec is None:
            continue
        sidx = sec_index[name]
        data = sec.data()
        base = sec['sh_addr']
        print(f'\n===== {name} offset=0x{sec["sh_offset"]:x} size=0x{len(data):x} =====')
        defs = [s for s in syms if s['st_shndx'] == sidx]
        for s in sorted(defs, key=lambda x: x['st_value']):
            if s['st_info']['type'] != 'STT_FUNC':
                continue
            start, size = s['st_value'], s['st_size']
            end = min(start + size, len(data))
            print(f'\n--- {s.name} 0x{start:x}..0x{end:x} ({size} bytes) ---')
            chunk = data[start:end]
            for ins in md.disasm(chunk, start):
                rel = relocs.get(sidx, {}).get(ins.address)
                note = ''
                if rel and rel[0]:
                    note = f'    ; reloc {rel[0]} (type {rel[1]})'
                print(f'0x{ins.address:04x}: {ins.bytes.hex():<10} {ins.mnemonic:<8} {ins.op_str}{note}')
