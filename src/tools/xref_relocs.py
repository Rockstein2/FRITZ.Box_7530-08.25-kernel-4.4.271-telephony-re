#!/usr/bin/env python3
"""List relocations to selected symbols and their containing functions."""
import sys
from elftools.elf.elffile import ELFFile

path=sys.argv[1]; wanted=set(sys.argv[2:])
with open(path,'rb') as f:
 e=ELFFile(f); secs=list(e.iter_sections()); symtab=e.get_section_by_name('.symtab')
 funcs=[]
 for s in symtab.iter_symbols():
  if s['st_info']['type']=='STT_FUNC' and s['st_size'] and s['st_value']:
   funcs.append((s['st_value'],s['st_value']+s['st_size'],s.name))
 def fn(off):
  for a,b,n in funcs:
   if a <= off < b: return n,off-a
  return '?',off
 for sec in secs:
  if sec['sh_type'] not in ('SHT_REL','SHT_RELA'): continue
  for r in sec.iter_relocations():
   sym=symtab.get_symbol(r['r_info_sym'])
   if sym.name in wanted:
    n,o=fn(r['r_offset'])
    print(f'{n}+0x{o:x} @0x{r["r_offset"]:x} -> {sym.name}')
