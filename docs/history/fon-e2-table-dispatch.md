# FON-E2 — table-aware indirect dispatch

> **Status: offline candidate analysis.**  Report:
> `tools/reports/cr16-table-dispatch.json`.

## 1. Why E1's table-hit count was insufficient

E1 found 5 639/5 668 aligned 16-bit words whose values equal decoded
instruction addresses.  That is only a correlation: code bytes and data
literals can produce the same values.  E2 therefore starts from an indirect
site and looks for the consumer chain, not from address-like words.

## 2. Required chain

A `PROVEN` indirect target needs all of:

```text
table base
  -> index or offset
  -> load of one table entry
  -> address transformation
  -> indirect call or jump
  -> target on a valid instruction boundary
```

The report records the width classes checked (16/20/24/32-bit), both
endian interpretations and absolute/relative address forms.  It records:

- indirect site;
- target expression;
- candidate table base;
- entry width;
- index bounds;
- consumer instruction;
- possible targets;
- provenance;
- confidence.

## 3. Results

| Image | Indirect sites | `CANDIDATE` | `UNRESOLVED` | `PROVEN` |
|---|---:|---:|---:|---:|
| normal | 382 | 0 | 382 | 0 |
| p2test | 396 | 11 | 385 | 0 |

Most candidates only have a nearby load whose effective address is data-like.
They do not establish a table base, a stride, a bounded index or a valid code
target.  The remaining sites have no preceding table-like consumer at all.

E3 corrected this from the earlier 87/78 count: a candidate now requires a
def-use link to the register consumed by the indirect instruction and no
nearer clobber.  The 0/11 linked candidates are still **CANDIDATE**, not
function-pointer proof.
No candidate was promoted by a normal/p2test address coincidence.

## 4. RAM-initialised tables

An indirect target built in RAM would require:

- a loader/copy path into the table;
- a relocation or address-generation rule;
- a proven index range;
- an indirect consumer.

E2 did not reconstruct such a table.  The `0x01000000 + 2*index` writer is
still a candidate loader/RAM-initialisation path, not a dispatch table
(see `fon-e2-loader-vs-pcm-buffer.md`).

## 5. IRQ vectors

The vector table at `INTBASE = 0x24` is documented separately in
`cr16-irq-paths.json`.  It is a real dispatch structure, but its entries are
not part of the 5 639/5 668 “table hits”; the two must not be conflated.

## 6. Conclusion

No slot-5, PCM or DMA dispatcher is proven.  The next table step needs a real
consumer chain, not another count of address-like words.
