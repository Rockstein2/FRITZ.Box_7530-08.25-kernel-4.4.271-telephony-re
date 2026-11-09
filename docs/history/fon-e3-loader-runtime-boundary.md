# FON-E3 — `0x01000000` loader/runtime boundary

> **Status: offline classification, still UNRESOLVED as a whole.**
> Report: `tools/reports/cr16-e3-handler-candidates.json`.

## 1. The 511 writes are iterations, not instructions

E2 called them "511 writes".  E3 confirms that the count is a runtime loop
count, not 511 distinct static stores:

```text
normal:
  0x25F90  sets index at 0x937C to 1
  0x25BA   fill helper
  0x25D0   single storw  (one static instruction)
  0x25F90  loops while index <= 0x200
p2test:
  0x26750 / 0x1E76 / 0x1E8C
```

The effective store is:

```text
address = 0x01000000 + 2 * index
```

with `index = 1 … 511`, producing `0x01000002 … 0x010003FE`.  The base itself
is not written by that loop.

## 2. Address-space caveat

`0x01000000` is **outside** the 24-bit range (`0xFFFFFF` maximum).  E3 does not
assume that it is a normal 24-bit absolute address.  The bank/relocation
mechanism is `UNRESOLVED`; the value could be banked RAM, a loader address or a
different address transform.  No alias with the IPQ4019 TLMM base of the same
number is claimed.

## 3. Separate `dsp_int` pointer range

`dsp_int` reads a pointer from `0xD6`:

```text
image u32le at 0xD6 = 0x01027F80
pointer + 0x58      = 0x01027FD8
```

The handler reads and writes the 16-bit word at `0x01027FD8`.  No resolved
instruction writes `0xD6`; the runtime loader/relocation is unknown.

The pointer target `0x01027FD8` is far outside the fill range
`0x01000002…0x010003FE`.  The region therefore has at least two distinct
subranges:

| Range | Evidence | Classification |
|---|---|---|
| `0x01000002…0x010003FE` | indexed fill loop; SC14480 DIP RAM analogy | `DIP_RAM_FILL_CANDIDATE` |
| `0x01027FD8` | `dsp_int` pointer + 0x58 | `STATIC_POINTER_CANDIDATE` |
| region as a whole | no reader/lifetime proof | `UNRESOLVED` |

## 4. What is not proven

- that `0x01000000` is RAM rather than a bank/relocated space;
- that the fill loop runs only at boot;
- that the fill payload is code, a table or PCM data;
- that the `0xD6` pointer survives loader handoff unchanged;
- that either range is consumed by a TDM/PCM path.

The region is **not** named a PCM buffer.  The concrete blocker is a resolved
reader/lifetime proof for the fill range plus a proved relation to the slot-5
control word; neither exists in the current offline image.

## 4a. SC14480 DIP-RAM cross-check

SC14480 printed p131–132 maps:

```text
0x01000000–0x010003FF  DIP Sequencer RAM, 512 × 16 bit
0x01000002             first instruction after URST=0
```

The E3 fill writes `0x01000002…0x010003FE`, exactly 511 words starting at the
second word.  This makes **DIP-RAM fill** the leading hypothesis.

The payload is constant `0x1001`; it is not decoded.  In the SC14480 DIP
opcode table (printed p36–37), `0x01` is `BR`; if the low byte is the opcode,
`0x1001` could be `BR` with parameter `0x10`.  The byte order, parameter
format and validity of 511 repeated words are unproven.  Do not call this a
valid DIP program yet.

`0x01027FD8` in the same map is `DSP_INT_REG`; `dsp_int` reads it through
`[0xD6]+0x58`, so the two 0x0100xxxx ranges are distinct.

## 5. Classification

`UNRESOLVED` for `0x01000000` as a whole.  Subranges are separately marked
`DIP_RAM_FILL_CANDIDATE` (`0x01000002…0x010003FE`) and
`STATIC_POINTER_CANDIDATE` (`0x01027FD8`/`DSP_INT_REG`).  The task's
`BOOT_COPY_PROVEN`, `RAM_INIT_PROVEN` and `RUNTIME_BUFFER_PROVEN` labels are
deliberately **not** assigned.
