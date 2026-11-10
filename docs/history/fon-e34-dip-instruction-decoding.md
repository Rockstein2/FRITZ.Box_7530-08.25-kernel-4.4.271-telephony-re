# E3.4 DIP instruction decoding boundary

CR16 writes `0x1001` for the local fill and later `0x12AA` at index 2 on
one checked caller path. SC14480 Rev. 1.0 Table 10 (printed pp. 35–38)
lists `0x01 BR`, `0x10 BR_B0`, `0xAA M_CON`, `0x12 JMPF`. These make two
competing byte-order readings, not a proven format: opcode location,
parameter, displacement and branch target remain unknown. AN-D-140 was not
found in the public search. The public OsmocomDECT SC14421 assembly and
`dip_opcodes.h` are retained outside Git at `../work/cr16/references/`;
they establish family-level opcode overlap, **not** SC14448 compatibility.

No valid 512-word pseudodisassembly or executable program is claimed.
`cr16-e34-dip-instructions.json` keeps the two words as candidates and
runtime-dependent words as expressions.
