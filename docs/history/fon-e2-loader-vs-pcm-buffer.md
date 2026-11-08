# FON-E2 — loader/copy versus PCM buffer at `0x01000000`

> **Status: classification improved, runtime role still UNKNOWN.**
> No hardware and no firmware execution.

## 1. Known writer

The normal image contains 511 sequential indexed 16-bit writes:

```text
0x01000000 + 2 * index     index = 1 ... 511
```

The base itself (`0x01000000`) is not written by that loop.  The recovered
fill loop has its index store at `0x25D0` and its 511 writes reported around
`0x25F90`; its exact function boundary and caller remain layout-sensitive in
the CR16 map.

## 2. What E2 checked

- whether a constant reader of `0x01000000` exists;
- whether an indexed reader uses the same base;
- whether a direct call passes the base into a callee;
- whether the write path is part of the boot/loader chain or a runtime
  function;
- whether p2test contains the same path;
- whether the written values resemble code, a data table, a RAM queue or a
  peripheral FIFO.

## 3. Result

| Question | Result |
|---|---|
| Writer proven | yes, 511 indexed writes |
| Constant reader | none resolved |
| Indexed reader with same base | none proven |
| Base passed through a proven direct call | none |
| Runtime lifetime proven | no |
| Contents proven code | no |
| Contents proven data table | no |
| PCM relationship proven | no |

Classification: **`LOADER_OR_RAM_INIT_CANDIDATE`**.

That means the region is consistent with a loader/copy or RAM-init buffer, but
E2 cannot distinguish those from a runtime buffer that is only reached through
an unresolved indexed/indirect path.  It is not a named PCM buffer.

## 4. Why the ambiguity remains

- The base is symbolic (`0x01000000 + 2*r3/r4`), not a resolved constant in a
  reader.
- The writer is in an initialisation-shaped path; E2 has not proved whether
  that path runs at boot only or also at runtime.
- The outstanding indirect sites and indexed accesses could hide a reader.
- `0x01000000` is also the IPQ4019 TLMM base in a different address space;
  no cross-space alias is claimed.

## 5. What would decide it

One of the following is needed:

1. a resolved reader of the same SC14448 address, with provenance;
2. a proven call/argument path carrying the base into a periodic handler;
3. a table/copy routine that establishes the region's lifetime and contents;
4. a future hardware trace showing the region is consumed with TDM data.

Until then Q46/Q55 remain open and the region must not be called a PCM buffer.
