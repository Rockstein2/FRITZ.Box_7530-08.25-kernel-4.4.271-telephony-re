# E3.3 `0x1001` and DIP instruction uncertainty

The firmware immediate is `movw $0x1001:m,r2` at `0x25F9A` / `0x26750`.
The direct helper path stores `r2`; all-path delivery is not proven.

SC14480 Rev. 1.0 Table 10 (printed pp. 35–38) names opcode `0x01` BR
and `0x10` BR_B0; p. 172 says execution begins at `DIP_RAM+1`. The PDF
refers to AN-D-140 for detailed instruction encoding, which is not in the
offline reference set. Neither `sc1442x_firmware.asm` nor `dip_opcodes.h`
was present locally; no network retrieval was performed. Therefore the
byte order, parameter/branch target, bank transition, first-word role and
out-of-range behavior are **UNRESOLVED**. Uniform branch-like words might
be a placeholder but cannot be declared a valid program or idle loop.
