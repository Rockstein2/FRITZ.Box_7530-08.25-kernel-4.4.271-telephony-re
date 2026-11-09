# E3.2 history — DSP/DIP IRQ comparison after address canonicalisation

> **Status: offline cross-check with a related device.**  No hardware.

## 1. Canonical addresses

The abs20 expansion rule (see `fon-e32-cr16-addressing.md`) changes the
effective addresses used in E3:

| E3 printed form | Encoded field | Effective address | SC14480 related-device meaning |
|---|---|---|---|
| `0x000F6006` | `0xF6006` | `0x00FF6006` | `DIP_CTRL_REG`, `URST` bit 7 |
| `0x000F5402` | `0xF5402` | `0x00FF5402` | `RESET_INT_PENDING_REG`, bits 10/13 |
| `0x000F6002` | `0xF6002` | `0x00FF6002` | `DIP_PC_REG` |
| `0x000F6400` | `0xF6400` | `0x00FF6400` | `BMC_CTRL_REG` |
| `0x000F6402` | `0xF6402` | `0x00FF6402` | `BMC_CTRL2_REG` |
| `0x000F4858` | `0xF4858` | `0x00FF4858` | P2 mode / pinmux family |

## 2. `dip_int`

Normal `0x28CD0` / p2test `0x27C88`:

```text
loadw encoded 0xF6006  -> effective 0x00FF6006
movb  r0,r2            -> low byte kept
movw  $0x400,r0
storw r0,encoded 0xF5402 -> effective 0x00FF5402
bal   callee
```

After canonicalisation, the read and acknowledgement are consistent with the
SC14480 DIP control/reset-pending semantics.  This is **semantic
consistency**, not proof of SC14448 register identity.  The SC14480
`DIP_CTRL_REG` stop/start sequence in the `0x2582` path uses the 24-bit
`0x00FF6006` form directly; the short abs20 form reaches the same effective
address.

## 3. `dsp_int`

Normal `0x28A94` / p2test `0x27914`:

```text
loadd 0xD6 -> 0x01027F80 (static image value)
addd  0x58 -> 0x01027FD8
load/test/write word at that pointer
...
storw r0,encoded 0xF5402 -> effective 0x00FF5402, value 0x2000
```

`0x01027FD8` is the SC14480 `DSP_INT_REG`; `0x00FF5402` bit 13 is
`DSP_INT_PEND`.  The shapes match, but the `0xD6` pointer is still a static
image value, its runtime writers are unknown, and the 32-bit pointer is above
the 24-bit address range.  The classification remains
`DSP_EVENT_OR_SOFTWARE_QUEUE_CANDIDATE`, with
`DSP_INTERRUPT_HANDLER_HYPOTHESIS`.

## 4. What is now settled

- the 0x400 / 0x2000 acknowledgements are not sent to a separate low-space
  register; their effective address is `0x00FF5402`;
- the `0x000F6006` read is the same effective address as the `0x00FF6006`
  pulse target;
- the DIP/DSP IRQ comparison no longer has an address-space conflict.

What remains:

- SC14448-specific register names and bit semantics;
- the 0xD6 runtime pointer/bank;
- a source-to-sink path for the slot-5 control word (Q75).
