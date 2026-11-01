#!/usr/bin/env python3
"""List direct callers of named ARM functions."""
import re, sys
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN
path=sys.argv[1]; targets=set(sys.argv[2:])
with open(path,'rb') as f:
 e=ELFFile(f); dyn=e.get_section_by_name('.dynsym'); text=e.get_section_by_name('.text')
 funcs={}
 for s in dyn.iter_symbols():
  if s['st_info']['type']=='STT_FUNC' and s['st_size'] and s['st_value']:
   funcs[s.name]=(s['st_value'],s['st_size'])
 addr2name={v[0]:n for n,v in funcs.items()}
 md=Cs(CS_ARCH_ARM,CS_MODE_ARM|CS_MODE_LITTLE_ENDIAN)
 for name,(st,sz) in sorted(funcs.items()):
  if name in targets: continue
  data=text.data()[st-text['sh_addr']:st-text['sh_addr']+sz]
  for ins in md.disasm(data,st):
   if ins.mnemonic in ('bl','b','blx'):
    m=re.search(r'#(0x[0-9a-f]+)',ins.op_str)
    if m:
     t=int(m.group(1),16)
     if t in addr2name and addr2name[t] in targets:
      print(f'{name}+0x{ins.address-st:x} @0x{ins.address:x} -> {addr2name[t]}')
