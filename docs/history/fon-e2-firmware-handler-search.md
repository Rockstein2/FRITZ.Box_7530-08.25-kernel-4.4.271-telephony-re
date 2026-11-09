# FON-E2 — firmware slot-5 handler search

> **Status: bounded negative result.**  No slot-5 consumer was proven.
> Report: `tools/reports/cr16-fon-handler-candidates.json`.

## 1. Search coverage added in E2

E2 does not repeat the E1 MMIO-only xref scan.  It adds:

- the continuation after every direct call;
- 432/403 function summaries;
- 146/116 E2 direct-call argument records, of which 25/10 were initially proven; E3 re-audited them (21/8 retained, 4/2 downgraded) and reports 173/134 records, 91/42 PROVEN;
- consumer-side analysis of 382/396 indirect sites;
- complete 31-vector IRQ callgraphs for both images;
- indexed accesses in the IRQ path;
- a dedicated writer/reader classification of `0x01000000`.

## 2. Result

The 34 PCM-adjacent candidate accesses per image are unchanged.  No new
slot-5 buffer or peripheral consumer was proven.  The closest IRQ structure
is `dip_int`, which reads `0xF6006` and writes `0xF5402 = 0x400`; that is a
control/status neighborhood, not a proven slot-5 control-word handler.

No instruction sequence was found with the complete shape:

```text
source of the incoming TDM/PCM word
  -> dataflow into control/state processing
  -> output status or state update
```

The absence of that complete chain is the reason the result stays
`CANDIDATE`/`NOT_FOUND`.

## 3. Concrete remaining paths

### Indirect candidates

Normal examples (site, nearest table-like base):

```text
0x000380  base 0x00011dde
0x00039c  base 0x00011dea
0x0003b8  base 0x00011df6
0x0003d4  base 0x00011e02
0x0003f0  base 0x00011e0e
0x000400  base 0x0001082c
```

p2test examples:

```text
0x000294  base 0x00000004
0x0002ae  base 0x00000010
0x0002c8  base 0x0000001c
0x0002dc  base 0x00010810
0x000308  base 0x00001b7e
0x00033a  base 0x00010814
```

These are `CANDIDATE` only.  The report has 6 normal / 17 p2test candidates after E3 def-use
correction, and 376 normal / 379 p2test unresolved sites.  None has a proven table base,
bounded index and valid indirect target together.

### Unresolved indirect sites

Representative sites: `0x000014`, `0x000018`, `0x000370`, `0x00038c`,
`0x0003a8`, `0x0003c4` (normal), with shifted equivalents in p2test.  They are
register-indirect `jal` forms with no recovered value.

### Indexed accesses

| Image | READ/INDEXED | WRITE/INDEXED | RMW/INDEXED |
|---|---:|---:|---:|
| normal | 249 | 280 | 20 |
| p2test | 195 | 186 | 15 |

Most remain symbolic.  The priority is the indexed work inside `dsp_int`
(`0x028a94` normal, `0x027914` p2test) and its callees.  A single address must
not be picked from a 16-address range without proving the loop bounds.

### IRQ paths

`dip_int` and `dsp_int` are the only handlers with resolved peripheral or
symbolic memory work.  `tim1_int` only touches its counter and `0xF5402`.
No handler has a proven 8 kHz cadence or an indirect callback.

### Loader/init region

`0x01000000 + 2*index` has 511 writer accesses and no resolved reader.  It
remains `LOADER_OR_RAM_INIT_CANDIDATE`; see
`fon-e2-loader-vs-pcm-buffer.md`.

## 4. What would close Q75

A proven handler needs at least:

1. a resolved input source for the slot-5 word (FIFO, indexed buffer or
   table);
2. dataflow from that source into a control/state decision;
3. a proven output status or state update;
4. normal/p2test structural agreement, or a documented test-build reason for
   the difference.

A match on `0x4000`, `0x8000` or a nearby peripheral address is not enough.

## 5. Normal / p2test

Both images retain the same 31-vector structure, the same three memory-bearing
IRQ handlers, and the same `0xF6006`/`0xF5402` neighborhood.  Addresses shift;
no p2test-only slot-5 handler was found.  That does not prove the p2test and
normal functions are identical at source level.
