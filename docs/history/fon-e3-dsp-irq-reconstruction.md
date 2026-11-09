# FON-E3 — `dsp_int` IRQ reconstruction

> **Status: offline focused trace, CANDIDATE only.**  No IRQ was asserted.
> Report: `tools/reports/cr16-e3-dsp-paths.json`.

## 1. Entry points

| Image | Entry | End |
|---|---|---|
| normal | `0x028A94` | `0x028B0A` |
| p2test | `0x027914` | `0x02798A` |

Both are vector handlers.  Their instruction sequence is structurally similar
but not byte-identical.

## 2. Data source

The first real data source is a pointer cell:

```text
loadd 0xD6 -> pointer
```

The image value at `0xD6` is the same in both images:

```text
bytes: 80 7f 02 01
u32le: 0x01027F80
```

The handler then executes:

```text
addd 0x58 -> 0x01027FD8
loadw 0x0:(r1,r0),r10
storw r10,0x0:(r1,r0)
```

No resolved instruction writes `0xD6`; its writers are assigned to the
loader/startup unknown.  The pointer is therefore a
`STATIC_POINTER_CANDIDATE`, not a proven runtime relocation.

## 3. Fields — correcting E2

E2 said the handler used `+0`, `+14` and `+16`.  Those offsets do not share one
base:

| Expression | Actual address | Role observed |
|---|---|---|
| pointer + 0x58 + 0x0 | `0x01027FD8` | event word read/write |
| `0x2C4 + 0x0e` | normal `0x2D2`, p2test `0x232` | counter read/increment/write |
| `0x2C4 + 0x10` | normal `0x2D4`, p2test `0x234` | counter read/increment/write |

The second pair comes from `movd $0x2C4` normal / `movd $0x224` p2test, not
from the `0xD6` pointer.

## 4. Event processing

The event word is loaded once and tested:

```text
r10 = word at pointer+0x58
andb $0xe,r2
bne0b  -> skip one counter path
orw $0xc,r10
tbit $0xf,r10 -> set bit 6 of 0x93C8 (normal) / 0x950E (p2test)
tbit $0x3,r10 -> call helper
tbit $0x2,r10 -> call helper
storw 0x2000,0xF5402
```

The `0x93CB` normal / `0x9512` p2test byte is read, replaced with `0x28`, and
restored at the end.  It is a re-entrancy/state flag candidate, not a PCM
sample.

The event word itself is not yet tied to a TDM, DMA or slot-5 source.

## 5. Helpers

Normal:

- `0x3B28`: loads `0x936C`, copies `+6` to `+0xA`, clears `+0xC`; small
  queue/state helper.
- `0x3B38`: larger queue/list helper, 36 blocks, calls `0x3C00` and `0x3C1A`.

p2test:

- `0x27744`: addresses `0x94A4`; same small-helper shape.
- `0x27754`: larger helper, calls `0x2781C` and `0x27836`.

The two families are structurally similar but not proven identical.  No helper
is named PCM.

## 6. Classification

**`DSP_EVENT_OR_SOFTWARE_QUEUE_CANDIDATE`**

Evidence for a DSP/event path:

- vector entry;
- pointer-based event word;
- event bit tests and conditional helpers;
- counter fields;
- `0xF5402` acknowledgement candidate.

Missing evidence:

- source of the event word;
- `0xD6` runtime writer/relocation;
- bit meanings;
- helper semantics and queue destination;
- any relation to the Linux slot-5 control word.

`pcm_evidence` and `slot5_evidence` are therefore **false**, not "unknown
because the function is named dsp".
