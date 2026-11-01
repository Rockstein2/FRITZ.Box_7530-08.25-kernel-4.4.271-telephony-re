#!/usr/bin/env python3
"""Disassemble named ARM ELF functions with literal/PLT annotations."""
import re, struct, sys
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN

path = sys.argv[1]
names = set(sys.argv[2:])
with open(path, 'rb') as f:
    elf = ELFFile(f)
    dyn = elf.get_section_by_name('.dynsym')
    text = elf.get_section_by_name('.text')
    rodata = elf.get_section_by_name('.rodata')
    plt = elf.get_section_by_name('.plt')
    sections = list(elf.iter_sections())
    def read_cstr(sec, off):
        d = sec.data(); end = d.find(b'\0', off)
        if end < 0: end = len(d)
        try: return d[off:end].decode()
        except Exception: return d[off:end].decode('latin1')
    def sec_of_addr(addr):
        for s in sections:
            if s['sh_flags'] & 2 and s['sh_addr'] <= addr < s['sh_addr'] + s['sh_size']:
                return s
        return None
    funcs = {}
    for s in dyn.iter_symbols():
        if s['st_info']['type'] == 'STT_FUNC' and s['st_size'] and s['st_value']:
            funcs[s.name] = (s['st_value'], s['st_size'])
    # PLT entries: first 20 bytes, then 12 bytes each; relocation order maps entries.
    relplt = elf.get_section_by_name('.rel.plt')
    pltnames = []
    if relplt:
        for r in relplt.iter_relocations():
            sym = dyn.get_symbol(r['r_info_sym'])
            pltnames.append(sym.name)
    plt_base = plt['sh_addr'] if plt else 0
    def plt_at(addr):
        if not plt or not (plt_base <= addr < plt_base + plt['sh_size']):
            return None
        n = (addr - plt_base - 20) // 12
        if 0 <= n < len(pltnames):
            return pltnames[n]
        return 'PLT0'
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
    for name in names:
        if name not in funcs:
            print(f'!! missing {name}')
            continue
        start, size = funcs[name]
        print(f'\n=== {name} 0x{start:x}..0x{start+size:x} ({size} bytes) ===')
        for ins in md.disasm(text.data()[start-text['sh_addr']:start-text['sh_addr']+size], start):
            notes = []
            m = re.search(r'\[pc, #(0x[0-9a-f]+|\d+)\]', ins.op_str)
            if m:
                lit = ins.address + 8 + int(m.group(1), 0)
                s = sec_of_addr(lit)
                if s and s['sh_addr'] <= lit < s['sh_addr'] + s['sh_size']:
                    off = lit - s['sh_addr']
                    if s['sh_type'] != 'SHT_NOBITS' and off+4 <= s['sh_size']:
                        word = struct.unpack_from('<I', s.data(), off)[0]
                    else:
                        word = None
                    notes.append(f'lit@0x{lit:x}={s.name}+0x{off:x}' + (f' -> 0x{word:x}' if word is not None else ''))
                    if word is not None:
                        ts = sec_of_addr(word)
                        if ts and ts.name == '.rodata':
                            notes.append(f'CSTR "{read_cstr(ts, word-ts["sh_addr"])}"')
                        elif ts:
                            notes.append(f'{ts.name}+0x{word-ts["sh_addr"]:x}')
            for mt in re.finditer(r'#(0x[0-9a-f]+)', ins.op_str):
                tgt = int(mt.group(1), 16)
                if ins.mnemonic.startswith(('b', 'bl', 'blx')):
                    pn = plt_at(tgt)
                    if pn: notes.append(f'CALL {pn}')
                    else:
                        candidates = [(n, v) for n, v in funcs.items() if v[0] <= tgt < v[0]+v[1]]
                        if candidates:
                            n, v = max(candidates, key=lambda x: x[1][0])
                            notes.append(f'-> {n}+0x{tgt-v[0]:x}')
            if notes:
                print(f'0x{ins.address:06x}: {ins.mnemonic:<8} {ins.op_str:<32} ; ' + ' | '.join(notes))
            else:
                print(f'0x{ins.address:06x}: {ins.mnemonic:<8} {ins.op_str}')
