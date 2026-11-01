#!/usr/bin/env python3
"""Annotate ARM PC-relative literal loads with ELF symbols/strings."""
import re, struct, sys
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN

path = sys.argv[1]
with open(path, 'rb') as f:
    elf = ELFFile(f)
    symtab = elf.get_section_by_name('.symtab')
    sections = list(elf.iter_sections())
    sec_by_name = {s.name: s for s in sections}
    sec_index = {s.name: i for i, s in enumerate(sections)}
    def sec_data(name):
        s = sec_by_name.get(name)
        return s.data() if s else b''
    def read_cstr(name, off):
        d = sec_data(name)
        if off < 0 or off >= len(d): return None
        end = d.find(b'\0', off)
        if end < 0: end = len(d)
        raw = d[off:end]
        try: return raw.decode('utf-8')
        except Exception: return raw.decode('latin1')
    symbols = []
    for s in symtab.iter_symbols():
        if s['st_value'] or s.name:
            symbols.append(s)
    def sym_at(name, off):
        cands = [s for s in symbols if s['st_shndx'] == sec_index.get(name) and s['st_value'] <= off < s['st_value'] + max(s['st_size'], 1)]
        if not cands: return None
        s = max(cands, key=lambda x: x['st_value'])
        d = off - s['st_value']
        return f'{s.name}+0x{d:x}' if d else s.name
    def resolve_value(word, secname, off):
        rel = relocs.get(sec_index.get(secname), {}).get(off)
        target = rel[0] if rel else None
        if target:
            if target.startswith('.rodata'):
                st = read_cstr(target, word)
                return f'{target}+0x{word:x}' + (f' "{st}"' if st else '')
            if target.startswith('.data') or target.startswith('.bss'):
                return f'{target}+0x{word:x}'
            return target + (f'+0x{word:x}' if word else '')
        for sn in ('.rodata.str1.1', '.rodata', '.data'):
            d = sec_data(sn)
            if 0 <= word < len(d):
                st = read_cstr(sn, word) if sn.startswith('.rodata') else None
                return f'{sn}+0x{word:x}' + (f' "{st}"' if st else '')
        return None
    relocs = {}
    for sec in sections:
        if sec['sh_type'] not in ('SHT_REL', 'SHT_RELA'):
            continue
        for r in sec.iter_relocations():
            sym = symtab.get_symbol(r['r_info_sym']) if symtab else None
            sname = sym.name if sym else ''
            if sym and not sname and sym['st_shndx'] != 'SHN_UNDEF':
                try:
                    sname = elf.get_section(sym['st_shndx']).name
                except Exception:
                    sname = ''
            relocs.setdefault(sec['sh_info'], {})[r['r_offset']] = (sname, r['r_info_type'])
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
    sec = sec_by_name['.text']
    data = sec.data()
    funcs = [s for s in symbols if s['st_shndx'] == sec_index['.text'] and s['st_info']['type'] == 'STT_FUNC' and s['st_size']]
    for fn in sorted(funcs, key=lambda x: x['st_value']):
        start, size = fn['st_value'], fn['st_size']
        print(f'\n--- {fn.name} 0x{start:x}..0x{start+size:x} ---')
        for ins in md.disasm(data[start:start+size], start):
            notes = []
            m = re.search(r'\[pc, #(0x[0-9a-f]+|\d+)\]', ins.op_str)
            if m:
                imm = int(m.group(1), 0)
                lit = ins.address + 8 + imm
                if 0 <= lit <= len(data) - 4:
                    word = struct.unpack_from('<I', data, lit)[0]
                    rv = resolve_value(word, '.text', lit)
                    if rv:
                        notes.append(f'lit@0x{lit:x} -> {rv}')
                    else:
                        notes.append(f'lit@0x{lit:x} = 0x{word:x}')
            for mt in re.finditer(r'#(0x[0-9a-f]+)', ins.op_str):
                tgt = int(mt.group(1), 16)
                if ins.mnemonic.startswith(('b', 'bl', 'blx')):
                    sn = sym_at('.text', tgt)
                    if sn:
                        notes.append(f'-> {sn}')
            rel = relocs.get(sec_index['.text'], {}).get(ins.address)
            if rel and rel[0]:
                notes.append(f'reloc {rel[0]}')
            if notes:
                print(f'0x{ins.address:04x}: {ins.mnemonic:<8} {ins.op_str:<30} ; ' + ' | '.join(notes))
            else:
                print(f'0x{ins.address:04x}: {ins.mnemonic:<8} {ins.op_str}')
