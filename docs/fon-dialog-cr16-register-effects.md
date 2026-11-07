# CR16 register-effects table

Status: **offline analysis.**  This file records, for every instruction form
that appears in `dectfw_secondlevel_441.hex` (`normal`) or
`dectfw_secondlevel_441p2test.hex` (`p2test`), *which registers it writes*, so
that the peripheral scanner cannot keep a stale address constant.

Evidence levels follow the project convention: **L1** machine bytes, **L2**
decode, **L3** control flow, **L4** semantics under the stated ISA
assumptions, **L5** hardware.  Everything here is L2 at most.

Sources used, in order of authority:

1. **CR16A Programmer's Reference Manual** (`/tmp/opencode/cr16a.txt`) — the
   instruction descriptions;
2. **binutils 2.44** `opcodes/cr16-opc.c` — the operand table that the
   assembler enforces;
3. **the assembler itself** (`as-new`) — which operand forms it accepts;
4. **machine bytes** in the two firmware images.

The CR16C manual was not available offline; where CR16A and the image
disagree, the image and the assembler win and the point is marked.

---

## 1. The rule the scanner uses

`written_registers(insn)` returns the set of registers an instruction may
modify.  The scanner invalidates every state entry touching that set before
applying the instruction, and the instruction may then establish a new
constant.

```text
written_registers(insn) -> {rN, ...}
```

A register pair `(rH,rL)` becomes UNKNOWN whenever either half is in the set.

## 2. Widening and multiply forms  — **corrected in PERIPH-2.2**

The previous version treated the widening forms as if the *first* operand
were the destination.  That was wrong.

| Form | Operands | Source | Destination | Writes |
|---|---|---|---|---|
| `movzw` | `r3,(r7,r6)` | `r3` | pair `(r7,r6)` | `r7`, `r6` |
| `movzw` | `r3,r4` | `r3` | `r4` | `r4` |
| `movxw` | `r5,(r1,r0)` | `r5` | pair | `r1`, `r0` |
| `movzb` | `r8,r0` | `r8` | `r0` | `r0` |
| `movxb` | `r8,r0` | `r8` | `r0` | `r0` |
| `mulsw` | `r3,(r7,r6)` | `r3` | pair | `r7`, `r6` |
| `muluw` | `r3,(r7,r6)` | `r3` | pair | `r7`, `r6` |
| `mulsb` | `r3,r4` | `r3` | `r4` | `r4` |

**Evidence.**  CR16A, `MOVZB src, dest`: *"converts the unsigned integer src
operand to the unsigned word dest operand"*, with the example
`movzb r8, r0` reading `r8` and writing `r0`.  `MOVXB` is described the same
way.  `MULi src, dest`: *"multiply the src operand by the dest operand and
places the result in the dest operand"*.  The assembler accepts only the
`src, dest` order (`movzw r3,r4` is accepted; the reverse is rejected with
`Illegal type of operand`).  The table in `cr16-opc.c`
(`ARITH_BYTE_INST2`, `{{regr,20},{regp,16}}`) fixes only the *printing*
order, not the semantics.

**Consequence for the scanner.**  `movzw r3,(r7,r6)` now invalidates
`(r7,r6)`.  The counterexample

```text
movd  $0xFF6006:l,(r7,r6)
movzw r3,(r7,r6)
storw r2,0x0:s(r7,r6)
```

is `UNKNOWN` after the fix (it was `RESOLVED 0x00FF6006` before).  The source
`r3` is not invalidated by this instruction.

Occurrences of *all* pair-destination widening/multiply forms: `normal`
222 `movzw` + 47 `movxw` + 14 `mulsw` + 3 `muluw` = **286**; `p2test`
163 + 43 + 57 + 4 = **267**.

A narrower count appears in `fon-dialog-peripheral-xrefs.md`: 269 / 206
covers only the widening moves (`movzw`, `movxw`), because the multiply
forms are never used as an address base.  Both numbers are correct for their
own definition and must not be read as one statistic.

## 3. Other instructions that write registers

| Form | Semantics | Writes | Evidence |
|---|---|---|---|
| `movd $imm:l,(rp)` | load a 32-bit constant | both halves | CR16A `MOVEi`; bytes |
| `movd $imm:m,(rp)` | load into one half only — **not** a 32-bit constant | both halves (the pair stops being a constant) | assembler emits this for `movd $imm:l` |
| `movd (rp1),(rp2)` | copy a pair | destination pair | bytes |
| `addd src,dst` | `dst := dst + src` | destination pair only | CR16A: *"Rdest := Rdest − Rsrc"* for SUB, ADD is the mirror |
| `subd`, `andd`, `ord`, `xord` | binary ALU into destination | destination pair | same |
| `ashud`, `lshd` | shift destination by immediate/register | destination pair | CR16A `ASHUi/LSHi` |
| `loadd ...,(rp)` | memory → pair | destination pair | `LD_REG_INST`, `{OP_D,20}` |
| `movw $imm,rn`, etc. | 16-bit ALU/move | destination register | CR16A §2 summary |
| `loadb/loadw ...,rn` | memory → register | that register | `LD_REG_INST` |
| `push`/`pop`/`popret` | stack, register list | the listed registers (`pop*`) and SP | `REGLIST_INST` |
| `spr`/`sprd` | register → processor register | none of the general registers | CR16A |
| `lpr`/`lprd` | processor register → general register | destination | CR16A |
| `tbit*`, `cmp*` | read-only | none | CR16A (flags only) |

### Known limitation: `push`/`pop` and SP

`push $n,rK` decrements SP; `pop $n,rK`/`popret` restores it and **writes the
listed registers**.  Measured on the images: the scanner currently reports
no written registers for `pop`/`popret` at all (`written_registers` returns
an empty set), so a register that a `pop` overwrites keeps its previous
constant if it survived to that point.

This does not create a false address in the two images: `pop` appears only
as an epilogue, and the block rule already drops every value at a block
boundary, so nothing is read after the `pop`.  It is nevertheless a real gap
for any future block that pops an address base (Q60).

## 4. Memory-access inventory

| Mnemonic | Operand form | Access | Supported |
|---|---|---|---|
| `loadb`/`loadw`/`loadd` | `addr,reg` or `addr,(rp)` | READ | yes |
| `storb`/`storw`/`stord` | `reg,addr` or `(rp),addr` | WRITE | yes |
| `sbitb`/`sbitw` | `$bit,addr` | **READ_MODIFY_WRITE** | yes (PERIPH-2.2) |
| `cbitb`/`cbitw` | `$bit,addr` | **READ_MODIFY_WRITE** | yes (PERIPH-2.2) |
| `tbitb`/`tbitw` | `$bit,addr` | READ (one bit) | yes (PERIPH-2.2) |
| `loadm` | `$n,rp` | READ, register list | **no — MEMORY_UNSUPPORTED** |
| `loadmp` | `$n,rp` | READ, list + post-increment | **no — MEMORY_UNSUPPORTED** |
| `storm` | `$n,rp` | WRITE, register list | **no — MEMORY_UNSUPPORTED** (absent from both images) |
| `stormp` | `$n,rp` | WRITE, list + post-increment | **no — MEMORY_UNSUPPORTED** (absent) |
| `push`/`pop` | stack | memory through SP | counted as `STACK` only for the explicit `(sp)` forms; the implicit stack traffic of `push`/`pop` is **not** counted |

`loadm`/`loadmp`/`storm`/`stormp` are declared with `REGLIST_INST` in
`cr16-opc.c` and are not described in the CR16A manual; they are absent from
CR16A entirely.  Their operand form (a register list plus a base) is not
decoded here, so they are listed per instruction in the report under
`memory_unsupported` rather than dropped.

Occurrences: `normal` 16 (`loadm` 13, `loadmp` 3); `p2test` 2 (`loadm`).

### What `sbit`/`cbit` changed

`sbitw`/`cbitw`/`sbitb`/`cbitb` are 299 memory operations in `normal` and
253 in `p2test` that the previous version did **not** count at all.  They
touch peripheral blocks directly:

| Address | Writes | Sites (normal) |
|---|---|---|
| `0x00FF5800`, `0x00FF5802`, `0x00FF5804`, `0x00FF5806`, `0x00FF580C` | bit set/clear | `0x1258`…`0x1992` |
| `0x00FF4808`, `0x00FF4812`, `0x00FF481E`, `0x00FF4860`, `0x00FF4868` | bit set/clear | `0x1200`…`0x14D4` |
| `0x00FF4010`, `0x00FF401C` | bit set/clear | `0x1896`, `0x14A8` |
| `0x000F4000`, `0x000F401A`, `0x000F4858`, `0x000F4970`, `0x000F5804`, `0x000F5806` | bit set/clear | `0x141E`…`0x14E4` |

These are **single-bit** modifications, not writes of a whole 16-bit word.
`0x00FF5406`, `0x00FF6006` and the other registers of the `0x25F90` sequence
are not touched by them.

## 5. Statistics (as produced by the tool)

| Counter | normal | p2test |
|---|---|---|
| decoded instructions | 19 570 | 18 058 |
| memory instructions, supported | 5 167 | 4 703 |
| memory instructions, unsupported | 16 | 2 |
| classified memory operations | 5 167 | 4 703 |
| READ | 2 596 | 2 374 |
| WRITE | 2 272 | 2 076 |
| READ_MODIFY_WRITE | 299 | 253 |
| address RESOLVED | 951 | 964 |
| address SYMBOLIC | 8 | 10 |
| address UNKNOWN | 2 812 | 2 631 |
| address STACK | 826 | 697 |
| address INDEXED | 529 | 380 |
| address PC_RELATIVE | 41 | 21 |
| ADDRESS_LOAD (not memory) | 568 | 480 |

Invariants checked by the tests:
`READ + WRITE + RMW == classified operations`, and
`sum(address kinds) == classified operations`; `ADDRESS_LOAD` is excluded
from both.
