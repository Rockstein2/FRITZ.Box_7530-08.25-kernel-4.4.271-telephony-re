# FON-E3 — `dip_int` and the `0xF600x` path

> **Status: offline focused trace, CANDIDATE only.**  No hardware was touched.
> Report: `tools/reports/cr16-e3-dip-paths.json`.

## 1. Entries

| Image | Entry | End |
|---|---|---|
| normal | `0x028CD0` | `0x028CF4` |
| p2test | `0x027C88` | `0x027CAC` |

## 2. Instruction flow

Normal:

```text
0x028CD2  movd $0x93C9,(r1,r0)
0x028CD8  loadb 0x0:(r1,r0),r2
0x028CDA  addb  $1,r2
0x028CDC  storb r2,0x0:(r1,r0)
0x028CDE  loadw 0xF6006,r0
0x028CE2  movb  r0,r2
0x028CE4  movw  $0x400,r0
0x028CE8  storw r0,0xF5402
0x028CEC  bal   0x028732
0x028CF0  pop
0x028CF2  retx
```

p2test has the same shape at `0x027C96`/`0x027CA0`, with counter `0x9510`,
`0xF6006` read, `0xF5402 = 0x0400`, and callee `0x025D74`.

## 3. What the `0xF6006` value does

Only the low byte is passed onward:

```text
loadw 0xF6006,r0
movb  r0,r2       ; r2 = low byte
movw  $0x400,r0   ; r0 no longer contains the read value
storw r0,0xF5402
bal   callee      ; r2 is the callee input
```

The callee normal `0x028732` uses `r2` as an event code/index into a table near
`0x93D0` and tests bits at offset `+5`; p2test `0x025D74` is much larger and
also consumes `r2`.  The two callees are not proven to be the same body.

The `0xF5402 = 0x0400` write is an acknowledgement candidate.  The read value
is not used in a branch in the handler itself.

## 4. Address spaces

These are kept separate:

| Address | Evidence |
|---|---|
| `0x000F6006` | `loadw` in `dip_int`, value passed as low byte to callee |
| `0x00FF6006` | pulse `0x80`/clear `0` in the separate `0x2558` path |
| `0x000F6002` | polled loop at `0x25FAE` normal / `0x26764` p2test |
| `0x000F5402` | acknowledgement candidate, value `0x0400` |

No alias between `0x000F6006` and `0x00FF6006` is claimed.  The QCA firmware
maps `0x000Fxxxx` and `0x00FFxxxx` in separate address spaces; E3 preserves
that distinction.

The proposed chain:

```text
0x00FF6006 pulse -> unknown hardware effect
0x000F6002 poll  -> ready
0x000F6006 read  -> low-byte event code
0x000F5402 write -> acknowledgement
```

is a **hypothesis**, not a proven execution sequence.  The `0x25FAE` poll loop
does not branch on `0xF6006`, and the pulse path is a different function.

## 4a. SC14480 interrupt-pending cross-check

SC14480 printed p196–197 defines `RESET_INT_PENDING_REG` at `0x00FF5402`:
bit 10 `DIP_INT_PEND`, bit 13 `DSP_INT_PEND`, write-one-to-clear.

The firmware writes `0x0400` in `dip_int` and `0x2000` in `dsp_int`, which is
semantically consistent.  But E3 sees those writes at `0x000F5402`, while
SC14480 places the register at `0x00FF5402` and maps `0x000Fxxxx` to program
FLASH/ROM.  The register meaning is a strong hypothesis; the actual SC14448
address decode is unresolved and is now a Q57 priority.

Likewise, SC14480 `0x00FF6006` is `DIP_CTRL_REG` with bit 7 `URST`
(1 = stop, 0 = start at DIP RAM+1), matching the observed `0x00FF6006`
`0x80 → 0` sequence.  The low-space `0x000F6006` accesses are a different
address and cannot be merged without proof.

## 5. Classification

**`EVENT_STATUS_ACK_CANDIDATE`**; under the SC14480 cross-check the low-byte
event path and `0x0400` write are **`DIP_INTERRUPT_ACK_HYPOTHESIS`**, with the
low/high address conflict unresolved.

Missing evidence:

- bit-level meaning of `0xF6006`;
- read-to-clear or latch semantics;
- callee event-code table semantics;
- relation to the polled `0xF6002` path;
- any slot-5/PCM source or sink.

No 8 kHz period is claimed.  The handler does not check `0x4000`, `0x8000` or
a slot-5 control word.
