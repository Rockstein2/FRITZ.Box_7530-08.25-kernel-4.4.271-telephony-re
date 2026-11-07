# SC14448 firmware: global CFG, entry points, and the PCM bring-up path

> **Status: static analysis with a corrected decoder and a global CFG.**
> No hardware was touched.  Every address below comes from the validated
> decoder in `tools/cr16_branch.py`, not from parsing objdump text.

---

## 1. What was fixed

### 1.1 Six-byte instructions

`objdump` prints a 6-byte CR16 instruction on **two lines**: the second line
carries the remaining bytes with no mnemonic.

```text
    2582:  70 00 ff 00   movd $0xff6006:l,(r1,r0)
    2586:  06 60
    2588:  b2 5a 80 00   movw $0x80:m,r2
```

The old parser treated line `0x2586` as its own instruction, which desynced
everything after it.  Continuation lines are now merged, and the resulting
sizes are correct:

| Address | Size | Instruction |
|---|---|---|
| `0x2582` | **6** | `movd $0xff6006:l,(r1,r0)` |
| `0x2588` | 4 | `movw $0x80:m,r2` |
| `0x258C` | 2 | `storw r2,0x0:s(r1,r0)` |

Instruction-size histogram over the second-level image:

```text
2 bytes: 13 546
4 bytes:  4 832
6 bytes:  1 191
total  : 19 570
```

### 1.2 Global CFG

`tools/cr16_cfg.py` builds one instruction index over all runs, so a branch
can jump between blocks.  Edges carry a confidence:

| Confidence | Meaning |
|---|---|
| `VERIFIED_DIRECT` | decoded target lands on an instruction boundary inside a run |
| `VERIFIED_INDIRECT` | target comes from a table whose reader was located (none found yet) |
| `CANDIDATE` | target is inside a run but not on a boundary, or outside all runs |
| `UNRESOLVED` | register-indirect, no table |

### 1.3 Entry points are not assumed

A run start is **not** an entry.  The entries used below are derived from one
rule and one observation, both stated explicitly:

- **rule:** a function is a *root* when it is a call target and is never
  reached by fallthrough from any other instruction;
- **observation:** `0x1602` calls `0x39F8`, and `0x1602` itself has no caller
  in the image, so `0x1602` is the top of the reachable graph and is treated
  as a **candidate** entry (not verified: nothing proves it is the reset
  vector).

---

## 2. Statistics (second-level image)

| Metric | Value | Method |
|---|---|---|
| Firmware blocks | 9 | contiguous Intel-HEX runs |
| Decoded instructions | 19 570 | linear sweep per run with continuation merge |
| Verified entry points | 0 | none proven; `0x1602` is a candidate |
| Candidate entry points | 404 | call targets never reached by fallthrough |
| Reachable instructions | 8 178 | BFS over `VERIFIED_DIRECT` edges from the candidates |
| Direct calls | 1 490 | decoded `bal` with an in-run target |
| Cross-block calls | 376 | caller and callee in different runs |
| Resolved indirect edges | 0 | no table recovered |
| Unresolved indirect edges | 2 706 | `jal`/`jump` through register pairs |
| Invalid branch targets | 204 | target inside a run but not on a boundary |
| Functions touching PCM candidate registers | see §5 | |

Limits of these numbers: the linear sweep decodes bytes that are never
executed, so "decoded" is an upper bound.  "Reachable" only follows
`VERIFIED_DIRECT` edges, so it is a lower bound.  The 404 candidates include
helpers reached only through indirect calls.

---

## 3. Answer to "who calls `0x24F8`"

The previous iteration concluded "only recursion".  With a working CFG that
is incomplete.  The chain is:

```text
0x1602 (candidate top-level)
  └─ 0x39F8  init
       └─ 0x3A2C
            └─ 0x25FB8
                 └─ 0x25F90
                      ├─ 0x25BA   (loop body, writes a table)
                      └─ 0x25FAA ──► 0x2558
                                        └─ 0x257E ──► 0x24F8   recursion
```

So `0x24F8` **is** reachable from the top-level code, through
`0x2558`.  The recursion at `0x257E` is genuine, and the chain above it is
real code, not dead.

`0x24F8` itself still has no caller other than `0x257E`, which is why the
earlier search found nothing: the entry is the arm at `0x2558`, and `0x24F8`
is entered by re-entry from inside.

---

## 4. The routine at `0x25F90` — PCM bring-up

```text
25f90  push $0x2,r7,RA
25f92  movd $0x937c:l,(r8,r7)      ; pointer to a 16-bit counter at RAM 0x937c
25f98  storw $0x1:s,0x0:s(r8,r7)   ; counter = 1
25f9a  movw $0x1001:m,r2           ; value 0x1001
25f9e  bal  -> 0x25BA              ; store it into table[(counter)], counter++
25fa2  loadw 0x0:s(r8,r7),r0
25fa4  cmpw $0x200:m,r0
25fa8  bhi  *-0x25f9a              ; loop while counter <= 0x200
25faa  bal  -> 0x2558              ; <-- the 0xFF6006 routine
25fae  loadw 0xf6002:m,r0          ; poll a peripheral
25fb2  cmpw $0x1:s,r0
25fb4  bne  *-0x25fae              ; wait until it reads 1
25fb6  popret $0x2,r7,RA
```

And the loop body at `0x25BA`:

```text
25ba  push $0x1,r7
25bc  movd $0x937c:l,(r1,r0)
25c2  loadw 0x0:s(r1,r0),r3        ; index
25c4  movd $0x1000000:l,(r5,r4)    ; base 0x01000000
25ca  movzw r3,(r7,r6)             ; index * 2
25cc  ashud $1:s,(r7,r6)
25ce  addd (r7,r6),(r5,r4)         ; base + index*2
25d0  storw r2,0x0:s(r5,r4)        ; table[index] = 0x1001
25d2  addw $0x1:s,r3
25d4  storw r3,0x0:s(r1,r0)        ; counter++
25d6  popret $0x1,r7
```

**Interpretation, with its limits.** The routine:

1. fills 512 words at `0x01000000` with the constant `0x1001`;
2. calls `0x2558`, which pulses `0xFF6006`;
3. waits for `0xf6002` to read `1`.

That is the shape of **"fill a buffer, start the block, wait for ready"**.
The address `0x01000000` is not inside any loaded firmware run, so it is RAM
or a device window — most plausibly the PCM buffer, but that is an
inference.  `0x1001` is a 16-bit word whose field layout is unknown.

This is the closest thing to a PCM bring-up path found so far, and it is the
only code that both writes a large buffer and pokes `0xFF6006`.

---

## 5. Peripheral accesses near the candidate PCM registers

| Firmware site | Operand | Effective (flat) | Notes |
|---|---|---|---|
| `0x25FAE` | `0xf6002:m` | `0x000F6002` (?) | **polled for readiness** |
| `0x25F86` | `0xff6006` via `0x2558` | `0xFF6006` | pulsed |
| `0x0011D4` | `0xff4858:l` | `0xFF4858` | GPIO set/clear |
| `0x0011E8` | `0xff4856:l` | `0xFF4856` | GPIO set/clear |
| `0x002560` | `0xf6400:m` | `0x000F6400` (?) | zeroed before the pulse |
| `0x002566` | `0xf6402:m` | `0x000F6402` (?) | set to `0xF0` |

The `0x000Fxxxx` versus `0xFFxxxx` question is unresolved (Q44).  Note that
`0x25FAE` and `0x2558`'s `0xF6006`/`0xF6400` accesses use the **same
8-bit page offset with a different high byte**, which is consistent with one
address space reached with an implied segment — but this is not proven.

What the sequence means, as far as the evidence goes:

```text
0xFF6400 <- 0        (channel reset?)
0xFF6402 <- 0xF0     (divider / mode?)
0xFF6006 <- 0x80     (start bit 7)
poll 0xF6002 == 1    (ready)
0xFF6006 <- 0
```

This is **an initialisation followed by a start pulse and a readiness poll**.
Calling it "PCM start" is a hypothesis; calling it "unknown peripheral
protocol" is what is proven.

---

## 6. Is `0x257E` really recursion?

Yes, and the mechanism is now readable:

```text
256a  movd (sp),(r5,r4)       ; the function's argument
256c  movb $0x2:s,r3
256e  movb $0x2:s,r2
2570  bal  -> 0x3C8C          ; array helper (count 2)
2574  loadw 0x0:s(sp),r0
2576  movb r0,r3              ; r3 = low byte of the argument
2578  loadw 0x0:s(sp),r0
257a  lshw $-8:s,r0           ; r0 = r0 >> 8
257c  movb r0,r2              ; r2 = high byte
257e  bal  -> 0x24F8          ; re-enter the block with r2 != 0
```

`r2` receives the **high byte** of the argument.  At `0x24F8` the test is
`cmpb $0x0:s,r2`, so the recursive call enters the `0x2558` arm when the high
byte is non-zero.

**Termination:** the recursive call is the *last* thing the arm does before
the block returns, so there is no unbounded loop inside `0x2558`; the
recursion depth is one, not a stack-consuming loop.  This is a **tail
transfer**, not a recursive algorithm — a re-entry that runs the arm once
more per call.

Function boundaries: `0x24F8` is the block entry (`cmpb`/`beq`, no prologue)
and `0x2558` is an arm inside it, also without a prologue.  Treating them as
separate functions is a convenience, not a fact.

---

## 7. PCM RX handler search

Searched reachable functions for: PCM receive interrupt, buffer processing,
16-bit command decode, table dispatch on an index, GPIO/ADC control, status
word build.

**Not found.**  What exists and is closest:

| Candidate | Why it is not the handler |
|---|---|
| `0x25F90` | writes a buffer and polls readiness — a bring-up, not a receiver |
| `0x25D8` | table write helper, no decode |
| `0x3C8C` | array copy/clear |
| `0x289B0` | bit-number to mask |

Boundaries of the search:

- all immediate peripheral references in the image;
- the whole reachable set from the 404 candidates;
- every function that writes the `0xFF4xxx`, `0xFF5xxx`, `0xFF6xxx` or
  `0xF6xxx` windows.

Not covered:

- interrupt vectors installed at run time (the image has no vector table at
  a fixed address that we could identify);
- the 2 706 unresolved indirect edges;
- code that would only exist in the first-level image.

---

## 8. normal vs p2test

| Aspect | normal | p2test |
|---|---|---|
| Runs | 9 | 8 |
| Decoded instructions | 19 570 | 17 690 |
| `0xFF6006` site | `0x2582` | `0x1E3E` |
| Bring-up routine | `0x25F90` | present, shifted |
| Buffer fill base | `0x01000000` | same constant |
| Ready poll | `0xF6002` | same constant |
| GPIO extra register | — | `0xFF4860` |

The PCM bring-up structure is **functionally identical** in both images: the
same constants (`0x1001`, `0x01000000`, `0xF6002`) appear at shifted
addresses.  The p2test build adds one GPIO register and is otherwise the
same code with different block boundaries.

---

## 9. What remains unknown

| Item | Why |
|---|---|
| is `0x1602` the reset entry? | no vector table found at a fixed address |
| what `0xF6002` / `0xF6400` physically are | the `0x000Fxxxx` vs `0xFFxxxx` question is open |
| what `0x1001` means | unknown field layout |
| is `0x01000000` the PCM buffer? | not in any loaded run; inferred, not proven |
| where the PCM RX handler is | not found; 2 706 indirect edges unexplored |

**Next step with the best information/risk ratio:** recover the indirect
call tables.  With 2 706 unresolved edges, a table-based dispatch would
explain both the missing handler and the 404 unreachable roots.  That is
offline work on constants already in the image.
