# FON-E3 — reference opportunities

> **Status: planning document.**  This does not start E3 and does not change
> any analyzer.

The new references can improve E3 in four ways: ABI auditing, IRQ/vector
cross-checking, instruction-level oracle tests and PCM/register hypothesis
generation.  None of them proves an SC14448 firmware behavior by itself.

## 1. Mapping

| E3 problem | Potential source | What it can contribute | Limit |
|---|---|---|---|
| CR16 call/return ABI | GCC CR16 backend; `linux-cr16` | call-clobbered set, return register, stack/argument conventions, `ra`/`sp` layout | GCC ABI is not proof of AVM's custom firmware convention |
| Register pairs / clobber | GCC; QEMU `LOADM`/`STORM`; `linux-cr16` pair layout | pair arithmetic, register-list save/restore, potential clobber checks | QEMU is incomplete for `jal`/`retx`; Linux target is SC14450/52 |
| Exception / IRQ semantics | `linux-cr16` `irq.c`, `irq.h`, `uapi/ptrace.h`; QEMU `EXCP` | 31-entry vector model, vector numbering, saved register frame, interrupt entry shape | no SC14448 vector table or hardware proof |
| DIP hardware | SC14480 datasheet; OsmocomDECT patch (`sc1442x.c`, `dip_opcodes.h`) | DIP RAM map, URST, DIP_PC/status/control, DIP banks and RF slot scheduling | SC14480/SC14421/24, not SC14448; DIP is not CR16C |
| `dip_int` / `dsp_int` | SC14480 map (`DSP_INT_REG`, reset-pending), OsmocomDECT, CVM, `linux-cr16` | DSP vector/clear-on-write semantics, DIP stop/start and interrupt acknowledgement candidates | no proven SC14448 address identity or source-to-sink chain |
| PCM pinmux | SC14CVMDECT PDF pp7, 32–33 | P2/P3 function encodings | different module; firmware `P2_MODE` write conflicts with a naive PCM reading |
| DSP PCM control | CVM PDF pp22–27; regrettableDectable `Api/AUDIO.py` | option names, FSC/BCLK ranges, clock edge/open-drain | Phoenix API is not the AVM PCMLINK path; BCLK values differ |
| UART API | regrettableDectable `MailProtocol.py`, `Api/HAL.py`; openD | mailbox framing, HAL area IDs, API vocabulary | not the ROM bootloader and not PCMLINK slot 5 |
| FON slot-5 protocol | own AVM RE (DISASM/E0–E3) | only source with direct slot-5 evidence | external references do not contain the AVM protocol |
| Asterisk integration | OsmocomDECT/Asterisk page | call-control/audio separation concepts | page NOT VERIFIED in this run; not FXS |

## 2. Prioritized follow-up plan

### P0 — SC14480 DIP/DSP cross-check (offline, highest value)

Use `sc14480-memory-map.md` first:

- test the DIP-RAM fill hypothesis for `0x01000002…0x010003FE`;
- decode the repeated `0x1001` payload, including opcode byte order;
- reinterpret `dsp_int` around `DSP_INT_REG=0x01027FD8` and its
  write-one-to-clear vector bits;
- compare `0x00FF6006` `0x80→0` with DIP `URST`;
- resolve the `0x000Fxxxx` vs `0x00FFxxxx` address-space conflict before
  assigning `0x400`/`0x2000` to the reset-pending register.

This does not close Q75; it changes the next questions.

### P1 — audit E3 PROVEN with the GCC ABI (offline)

Use `gcc/config/cr16/cr16.h`/`cr16.c` to check:

- expected argument registers `r2`–`r6`;
- return value `r0`;
- call-clobbered `r0`–`r6`, `ra`, `sp`;
- callee-saved `r7`–`r13`;
- stack direction and frame/argument pointer roles.

Do **not** rewrite E3 yet.  Compare each `cr16-e3-callsite-audit.json` record
against this ABI and classify any argument pair outside `r2`–`r6` as
`ABI_MISMATCH` or explain why the firmware may use a custom convention.

### P2 — cross-check IRQ entry/save frames

Use `linux-cr16` `irq.h`/`uapi/ptrace.h` and QEMU `EXCP` to compare:

- vector table size and indexing;
- saved-register order;
- `ra`/`sp` and pair save/restore;
- return path (`retx`/`popret` on CR16 vs Linux interrupt return).

The Linux port is for SC14450/SC14452, so any match with SC14448 is a
structural hypothesis, not a device identity.

### P3 — small QEMU instruction fixtures

QEMU currently implements `MOVD`, `ADDD`, `LOAD`, `STOR`, `LOADM`, `STORM`,
`EXCP`, `JCOND`, `BRCOND` and many arithmetic/bit forms.  It does **not**
show `JAL`, `JALR`, `RETX`, `LOADMP` or `STORMP` in the retrieved
`insn.decode`; interrupts are marked TODO.

Use QEMU only for small, already-decoded sequences where the instruction is
present, and compare against the binutils CR16 oracle.  Do not attempt to
run the full AVM firmware.

### P4 — use CVM registers as hypotheses for a focused firmware audit

The CVM register family gives useful addresses for `0x00FF48xx`:

- `PAD_CTRL_REG=0xFF481E`;
- `P2_DIR_REG=0xFF4856`;
- `P2_MODE_REG=0xFF4858`;
- `P3_DIR_REG=0xFF4866`;
- `P3_MODE_REG=0xFF4868`;
- `P3_DATA_REG=0xFF4860`.

The SC14448 firmware uses the same low addresses.  Investigate, but do not
declare, the following:

- whether `P2[2..5]` really are PCM_CLK/DI/DO/FSC on this board;
- whether `P3[7:5]` analog RING modes explain the observed `P3_MODE` writes;
- whether the `0x000F4858` RMW is an alias of `0x00FF4858`.

The observed `P2_MODE` write at normal `0x11D4` is not the naive CVM PCM
selection; this is a **conflict/uncertainty** that must be resolved, not a
reason to rename the pins.

### P5 — use regrettableDectable only as API vocabulary

`MailProtocol.py` and `Api/HAL.py` can help name Phoenix/UART concepts and
memory-area IDs.  They must not be used to claim:

- that AVM firmware exposes Phoenix;
- that the SC14448 ROM loader uses the same mailbox;
- that `AHA_DSP`/`AHA_FPGA` are the AVM PCMLINK/TDM path.

Do not run `main.py`.

### P6 — do not start Asterisk work

The Asterisk page is a call-control/audio integration reference, not a FON
driver.  It remains outside the E3 scope.

## 3. Concrete next E3 experiments (when authorized)

1. Re-audit `cr16-e3-callsite-audit.json` against GCC `r2`–`r6` argument and
   `r0` return conventions.
2. Compare `dsp_int`/`dip_int` prologues with Linux CR16 `pt_regs`/vector
   save order, but keep SC14448 as the target.
3. Use QEMU to validate only the implemented `LOADM`/`STORM`/`MOVD`/`ADDD`
   sequence shapes; refuse missing `JAL`/`RETX` forms.
4. Run a focused, source-anchored audit of `P2_MODE`/`P3_MODE` writes in
   normal/p2test to test the PCM/ring hypotheses.
5. Keep Q75 open until a firmware source-to-sink path is proved; external
   references cannot close it.

No hardware action is part of this plan.
