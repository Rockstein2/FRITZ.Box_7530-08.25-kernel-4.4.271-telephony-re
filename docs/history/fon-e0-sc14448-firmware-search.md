# FON-E0 — SC14448 firmware search for a slot-5 handler

> **Status: bounded negative result.**
> Offline analysis of the two second-level firmware images.  No firmware was
> executed, no hardware was accessed, and no AVM binary is added to Git.

Images:

| Image | SHA256 | Decoded instructions |
|---|---|---:|
| `dectfw_secondlevel_441.hex` | `7cac33c72b2222468f34033a15c35487aa35062265ab0013bb480068ebab7b31` | 19 570 |
| `dectfw_secondlevel_441p2test.hex` | `6361384d0e3b717e33ca65111cef82df8952da28e24b9d3b94d055b20dbc4860` | 18 058 |

Tools used: the existing `tools/cr16_cfg.py`,
`tools/cr16_peripheral_xrefs.py`, `tools/cr16_branch.py` and the
machine-readable `tools/reports/peripheral-xrefs.json`.  The CR16 binutils
oracle was **not available** in this session (`/tmp` is not persistent); the
committed xref report and its tests were used instead of rebuilding it.

---

## 1. PCM/peripheral accesses

Resolved 16-bit accesses around the candidate PCM windows:

| Site | Image | Instruction | Address | Value/use |
|---:|---|---|---|---|
| `0x1348` | normal | `storw` | `0x000F6006` | `0x0080` |
| `0x145C` | normal | `storw` | `0x000F6006` | `0x0080` |
| `0x2602C` | normal | `loadw` | `0x000F6006` | value discarded |
| `0x28CDE` | normal | `loadw` | `0x000F6006` | value used before `0xF5402 <- 0x400` |
| `0x25FAE` | normal | `loadw` | `0x000F6002` | polled until 1 |
| `0x2582/258C` | normal | `movd`/`storw` | `0x00FF6006` | pulse `0x80` |
| `0x25AA` | normal | `loadw` | `0x00FF6006` | discarded |
| `0x25B4` | normal | `storw` | `0x00FF6006` | clear `0` |
| `0x255E/2566` | normal | `storw` | `0x000F6400/6402` | `0`, `0xF0` |
| `0x25B0` | normal | `storw` | `0x000F5402` | `0x400` |

The p2test image has the same functional pattern shifted:

```text
0x0DBE/0x0ED2  -> 0xF6006 = 0x80
0x1E3E/0x1E48  -> 0xFF6006 = 0x80
0x1E66/0x1E70  -> 0xFF6006 read / clear
0x26764        -> 0xF6002 polled
0x267E2        -> 0xF6006 read
0x27C96        -> 0xF6006 read (unreached mode A)
```

The `0x000F6002` read is a **single polled address** in both images.  The
`0x00FF6006` pulse is bracketed by an interrupt-controller write; its value
is discarded on read-back.  The two address families are not assumed to
alias.

## 2. What a slot-5 handler should look like

A firmware-side handler for the Linux control word would need at least one of:

- a periodic read/write of a 16-bit PCM/MBOX buffer;
- a mask/test of bits 14/15 or the low control fields;
- a path from an RX word to a GPIO/PWM/ADC operation;
- a path from a command word to a status word.

The resolved access map contains none of these with a proven address:

- no resolved access to a slot-5 buffer;
- no immediate `0x4000` in either image;
- no immediate `0x5555`;
- only one `0xfefe` immediate (`0x06AC` normal / `0x04F0` p2test), stored to
  an address in the `0x00108xx` data region, not to a PCM peripheral;
- `0x8000` immediates occur in the `0x00116xx` data region and one nearby
  code site, not in a PCM control mask.

This is a **negative result over resolved forms**, not a proof of absence.

## 3. Indirect/indexed space

The xref report has many 16-bit indexed/unknown operations:

| Image | `storw` UNKNOWN | `loadw` UNKNOWN | `storw` INDEXED | `loadw` INDEXED |
|---|---:|---:|---:|---:|
| normal | 302 | 233 | 92 | 33 |
| p2test | 355 | 195 | 57 | 24 |

These are the main remaining possibility for an undecoded PCM buffer or
control handler.  The current xref model deliberately starts every basic
block with UNKNOWN registers and does not merge state across blocks.  It can
therefore miss a handler whose buffer base is computed in a predecessor
block or loaded from a table.

## 4. Cross-block limitation

No new cross-block dataflow was implemented in E0.  The existing tool
(version 3) does not propagate a register pair across basic blocks, calls,
returns or indirect jumps.  The following therefore remain unproven:

- a buffer base loaded in one block and used in another;
- a function pointer or table entry selected at run time;
- an IRQ handler reached only through a vector table;
- a PCM handler whose address is assembled from data memory.

The known unresolved branch-target question (see
`fon-dialog-ff6006-callgraph.md`) also prevents a complete call graph.

## 5. Candidate buffers/regions

| Region | Evidence | Status |
|---|---|---|
| `0x01000000` + indexed writes | 511 sequential 16-bit writes in `0x25F90`; no resolved reader | **candidate PCM buffer**, not proven |
| `0x00108xx` | `0xFEFE` and `0x7FFF` writes; data region | **candidate data/table**, not PCM |
| `0x00116xx` | `0x8000` writes 9x normal / 8x p2test | **candidate data/table**, not PCM |
| peripheral `0x000F6002/6` | direct accesses, poll/pulse | **control/status candidate**, not slot-5 buffer |
| peripheral `0x00FF6006` | pulse/clear; address pair | **pulse candidate**, not assumed alias |

No candidate is named "PCM buffer" without qualification.

## 6. Interrupt candidates

`0x000F5402` is written from several sites with `0x2000`, `0x0400`, `0x0100`,
`0xFFFF`; it is the most likely control register among the observed block.
The vector-map documents 31 entries but no vector is proven to be PCM.  No
`PCM ready`, `DMA done` or `slot 5` interrupt name is assigned.

## 7. Conclusion

A slot-5 / FON command handler was **not found** in the resolved firmware
map.  The search boundary is:

- all resolved peripheral references in both images;
- the PCM/GPIO/UART/interrupt candidate windows;
- the previously reconstructed `0x24F8..0x3CFD` and `0x20000..0x28DCD`
  blocks;
- the committed CFG/xref reports.

It cannot exclude a handler reached only through an unresolved indirect
table, a cross-block address, or an IRQ vector, and it does not prove that
the SC14448 consumes slot 5 at all.  The next evidence would require a
reviewed cross-block dataflow tool or a future hardware trace.
