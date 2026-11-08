# FON-E0 — analog FON state machine from `isdn_fbox_fon5.ko`

> **Status: offline static reconstruction.**
> Source: `isdn_fbox_fon5.ko` SHA256
> `47e0e29bbdc4e76738f2d893c4c587ec7dd7aa99f543a035140561ed90dbd2c9`.
> No hardware, GPIO, UART, PCM, reset or analog line was accessed.

This document recovers the Linux-side writes and readback logic around the
analog FON.  It does **not** prove what the SC14448 does with the resulting
TX slot-5 control word.

---

## 1. `slics_reset` bring-up sequence

Function `0x40994`.

The function calls `pcmlink_ul_status(0,0,0)` first.  If it returns `>0`, it
only stores the returned status and returns; the long bring-up below runs on
the non-positive branch.

Observed writes on the bring-up branch:

```text
write(0x48, 0x01100000, 0x01100000)
write(0x40, 0x01107770, 0x0110fff0)
slic_set_ring(0, 1, 1)       -> 0x48 bits 5/6, mask 0x0060
slic_set_ring(1, 1, 1)       -> 0x48 bits 9/10, mask 0x0600
slic_set_ring(2, 1, 1)       -> 0x48 bits 13/14, mask 0x6000
msleep(200)
```

Then it clears the per-SLIC state bytes and polls the hook state for each
SLIC.  For the on-hook (`hook == 0`) branch it writes, for each SLIC:

```text
write(0x40, 0, 0x0070)       SLIC0
write(0x48, 0, 0x0070)
write(0x40, 0, 0x0700)       SLIC1
write(0x48, 0, 0x0700)
write(0x40, 0, 0x7000)       SLIC2
write(0x48, 0, 0x7000)
write(0x64, 0, 0x0001)
```

The off-hook branches set the corresponding bits and increment the per-SLIC
state; the exact branch values are visible in `slics_reset` at
`0x40c18..0x40c98`.  The sequence is a **bring-up/ring-pulse/hook probe**, not
a proven line-feed waveform.

## 2. `slic_set_ring`

Function `0x408d0`.

| SLIC | Register | Mask | Meaning in Linux code |
|---:|---|---:|---|
| 0 | `0x48` | `0x0060` | bits 5 and 6 |
| 1 | `0x48` | `0x0600` | bits 9 and 10 |
| 2 | `0x48` | `0x6000` | bits 13 and 14 |

The function writes `ring_on` into the first bit and `ring_state` into the
second.  It does not write a voltage or a frequency; the ring phase/cadence
is software-driven.

## 3. `Handle_Ints_FPGA`

Function `0x41058`.

It polls `slic_get_hook_state()` and reads/writes register `0x48` with the
per-SLIC masks.  For SLIC0 it toggles bits 5/6 on the observed idle/hook
path (`0x41174..0x41194`), using `pcmlink_ul_readregister(0x48)` and
`pcmlink_ul_writeregister(0x48, value, 0x60)`.  SLIC1/2 use masks `0x600`
and `0x6000` and bits 9/10 or 13/14.

This is a **software phase toggle**, not a single "ring enable" write.  The
hook value itself comes from register `0x44` bit 7, which is RX status bit 3.

## 4. `Get_POTS_LineState_FPGA`

Function `0x4179c`.

It reads:

```text
0x48  line/ring state
0x44  hook/status
0x50  line status
```

and returns a bitmask.  Values observed in the code include `0x100`, `0x1000`,
`0x11`, `0x02`, `0x01`; the mapping from those bits to the human-readable
strings (`ONHOOK`, `OFFHOOK`, `RING0..2`, `NO_LINE`, `POLREV`, ...) is not
recovered.  Do not attach names to numeric return bits without a caller
table.

## 5. `Set_POTS_Line_FPGA`

Function `0x419c4`.

The line-state argument `r9` is dispatched through a jump table for values
`0..8`.  The table is at `0x41b18`:

| State | Entry | Observed actions |
|---:|---:|---|
| 0 | `0x41b3c` | restore RX slot, `PCMRoute_RxOff`, DTMF/TGS setup; optional `0x3c` or `0x48` write |
| 1 | `0x41bd0` | CLIP/tuut init, `PCMRoute_SetTimeSlot(0x2e)`, optional `0x3c`/`0x48` write |
| 2 | `0x41c1c` | time-slot query/restore, optional `0x3c`/`0x48` write |
| 3 | `0x41c68` | tuut init, `PCMRoute_SetTimeSlot(0x2e)`, `PCMRoute_RxOff` |
| 4 | `0x41cfc` | `PCMRoute_SetTimeSlot(0x2e)`, `PCMRoute_TxOff` |
| 5 | `0x41c94` | `PCMRoute_TxOff` |
| 6 | `0x41ca4` | tuut filter init |
| 7 | `0x41cb4` | slot feature, restore RX, RX/TX off, noise canceller |
| 8 | `0x41cf0` | `PCMRoute_SetTimeSlot(0x2e)`, `PCMRoute_TxOff` |

The function also writes register `0x3c` or `0x48` depending on POTS ID and
the state; the exact `(value,mask)` pairs are visible in the table entries.
The numeric states are **not** labelled `DISABLED`, `LINE_IDLE`, `RINGING` or
`ACTIVE` here because no proven numeric-to-string table was found.

## 6. Minimal observed state relationships

```text
bring-up: 0x48/0x40 writes -> ring pulse -> 200 ms -> hook poll -> idle writes
ring:     slic_set_ring bits 5/6 -> timer toggles bits 5/6
hook:     RX status bit 3 -> reg 0x44 bit 7 -> slic_get_hook_state()
line:     Set_POTS_Line_FPGA state -> PCM routing + optional 0x3c/0x48 write
```

These are Linux-side state relationships, not a proven analog waveform or
SC14448 internal state machine.  In particular, the software does not expose
a single register that means "48 V line feed" or "90 V ring"; those effects
are downstream and unproven.

## 7. Unknown

- numeric line-state names and transitions in the higher-level POTS code;
- exact SC14448 GPIO/PWM/ADC mapping;
- whether `0x4000`/`0x8000` are idle/ring markers or data qualifiers;
- high-voltage ring/line-feed topology;
- whether the SC14448 firmware must run for the analog path.
