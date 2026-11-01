#!/usr/bin/env python3
"""Scan ARM PIE ELF for PLT calls and rodata string-literal xrefs."""
import re, struct, sys
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN

path = sys.argv[1]
only = set(sys.argv[2:])
with open(path, 'rb') as f:
    elf = ELFFile(f)
    dyn = elf.get_section_by_name('.dynsym')
    text = elf.get_section_by_name('.text')
    plt = elf.get_section_by_name('.plt')
    relplt = elf.get_section_by_name('.rel.plt')
    sections = list(elf.iter_sections())
    rodata = elf.get_section_by_name('.rodata')
    def cstr(off):
        d=rodata.data(); end=d.find(b'\0',off)
        return d[off:end].decode('latin1') if 0 <= off < len(d) else ''
    def sec_of(addr):
        for s in sections:
            if s['sh_flags'] & 2 and s['sh_addr'] <= addr < s['sh_addr']+s['sh_size']:
                return s
        return None
    funcs={}
    for s in dyn.iter_symbols():
        if s['st_info']['type']=='STT_FUNC' and s['st_size'] and s['st_value']:
            funcs[(s['st_value'],s['st_size'])]=s.name
    ordered=sorted(funcs)
    pltnames=[]
    if relplt:
        for r in relplt.iter_relocations():
            pltnames.append(dyn.get_symbol(r['r_info_sym']).name)
    plt0=plt['sh_addr']; pltsz=plt['sh_size']
    def plt_at(addr):
        if not (plt0 <= addr < plt0+pltsz): return None
        n=(addr-plt0-20)//12
        return pltnames[n] if 0<=n<len(pltnames) else 'PLT0'
    def fn_at(addr):
        for (st,sz),n in funcs.items():
            if st <= addr < st+sz: return n, addr-st
        return None,0
    md=Cs(CS_ARCH_ARM,CS_MODE_ARM|CS_MODE_LITTLE_ENDIAN)
    for st,sz in ordered:
        name=funcs[(st,sz)]
        data=text.data()[st-text['sh_addr']:st-text['sh_addr']+sz]
        for ins in md.disasm(data,st):
            m=re.search(r'\[pc, #(0x[0-9a-f]+|\d+)\]',ins.op_str)
            if m:
                lit=ins.address+8+int(m.group(1),0)
                s=sec_of(lit)
                if s and s['sh_type']!='SHT_NOBITS' and lit+4<=s['sh_addr']+s['sh_size']:
                    word=struct.unpack_from('<I',s.data(),lit-s['sh_addr'])[0]
                    ts=sec_of(word)
                    if ts and ts.name=='.rodata':
                        txt=cstr(word-ts['sh_addr'])
                        if '/dev/dect_io' in txt or (only and any(o in txt for o in only)):
                            print(f'{name}+0x{ins.address-st:x} @0x{ins.address:x}: lit {txt!r}')
            for mt in re.finditer(r'#(0x[0-9a-f]+)',ins.op_str):
                if ins.mnemonic.startswith(('b','bl','blx')):
                    tgt=int(mt.group(1),16); pn=plt_at(tgt)
                    if pn and pn in only:
                        print(f'{name}+0x{ins.address-st:x} @0x{ins.address:x}: CALL {pn}')
