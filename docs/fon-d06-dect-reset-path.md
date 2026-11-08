# D0.6-A — the AVM DECT RESET path (GPIO40)

> **Status: offline disassembly of OEM modules.**  No router access, no GPIO
> write, no reset.  All addresses are module-relative `.text` offsets of
> `Piglet_noemif.ko` unless stated otherwise.

Binary used: `lib/modules/4.4.271/piglet_noemif/Piglet_noemif.ko` from the
FRITZ!OS 08.25 squashfs.  The module is not committed; only its analysis is.

---

## 0. Bottom line

The reset path is recovered end to end **on the software side**:

```
GPIO40 (board table gpio_avm_dect_reset)
   |
   v  get_profile() looks the name up in the board config
profile + 0x28  = GPIO number
   |
   v  dect_loader(), state PREPARE
dakota_gpio_ctrl(gpio, 0, 1)      -> request as output
dakota_gpio_out_bit(gpio, 0)      -> drive LOW      (assert)
   ... 11 x ~1 unit of delay ...
dakota_gpio_out_bit(gpio, 1)      -> drive HIGH     (release)
   |
   v
msm_dectuart_init(...)            -> UART ready for the firmware upload
```

Key results:

| Question | Answer | Status |
|---|---|---|
| Owner of GPIO40 in FRITZ!OS | `Piglet_noemif.ko`, `dect_loader()` | **CONFIRMED** |
| Which profile slot | `profile+0x28`, resolved from the string `gpio_avm_dect_reset` | **CONFIRMED** |
| Direction / initial level | `dakota_gpio_ctrl(gpio, 0, 1)`, then `out_bit(gpio, 0)` | **CONFIRMED** |
| Logical assert / deassert | **assert = 0**, **deassert = 1** at the API | **CONFIRMED** |
| Reset occurs before or after the upload | **before** `msm_dectuart_init()` | **CONFIRMED** |
| Hardware inversion between IO and SC14448 | **UNKNOWN** | — |

## 1. How the GPIO number is obtained

`get_profile()` (`.text` `0x2b08`) walks a linked list of 0x20-byte records
from `avm_get_hw_config_table()` and `strcmp`s each record's name.  The reset
entry is at `0x3844..0x385c`:

```
3844: ldr   r3, [r7, #0x4]        ; record->value  == GPIO number
384c: ldr   r2, [pc, #0xe4]       ; literal 0x3938 -> "gpio_avm_dect_reset"
3854: str   r3, [r5, #0x28]       ; profile->[0x28] = gpio
```

and the adjacent `dect_rd` entry at `0x38c0..0x38c8` writes `profile+0x2c`,
which confirms the two neighbouring slots:

| Profile offset | Name | Meaning |
|---|---|---|
| `+0x28` | `gpio_avm_dect_reset` | reset line |
| `+0x2c` | `gpio_avm_dect_rd` | receive/status line |
| `+0x30` | `gpio_avm_dect_tx` | transmit line |

So the reset GPIO number is **data**, not an immediate, and it comes from the
same board table that says GPIO40.  If the string is missing, the lookup
fails and the value stays 0; the loader treats `cmn r0, #1` (–1) as "no
GPIO", so a missing entry is handled.

## 2. The reset sequence in `dect_loader()`

`dect_loader()` is at `.text` `0x9a8`.  The relevant block, in the
dump of `0xb20..0xbc4`:

```
b28: ldr   r3, [r7]                ; pProfile
b30: ldr   r0, [r3, #0x28]         ; gpio = profile->dect_reset
b34: cmn   r0, #1                  ; gpio == -1 ?
b38: beq   0xb58                   ;   yes: skip the reset entirely
b3c: mov   r1, #0                  ; dir  = 0
b40: mov   r2, #1                  ; flag = 1
b44: bl    dakota_gpio_ctrl        ; dakota_gpio_ctrl(gpio, 0, 1)
b4c: mov   r1, #0                  ; value = 0
b50: ldr   r0, [r3, #0x28]
b54: bl    dakota_gpio_out_bit     ; dakota_gpio_out_bit(gpio, 0)  <-- ASSERT
b58: mov   r6, #11
b60: subs  r6, r6, #1
b64: bne   0xc14                   ; delay loop (11 iterations)
...
b84: ldr   r3, [pc, #0xd28]        ; pProfile
b8c: ldr   r0, [r3, #0x28]
b90: cmn   r0, #1
b94: beq   0xba0
b98: mov   r1, #1                  ; value = 1
b9c: bl    dakota_gpio_out_bit     ; dakota_gpio_out_bit(gpio, 1)  <-- DEASSERT
ba0: mov   r11, #16
ba8: subs  r11, r11, #1
bac: bne   0xc24                   ; post-release settle loop
```

### 2.1 What the API arguments mean

`XBIT_WritePort_XBIT_CLK` (`0x0`–`0x18`) is the clearest caller:

```
0:  ldr  r3, [pc, #0x24]   ; pProfile
c:  ldr  r3, [r3]
10: ldr  r0, [r3, #0xc]    ; gpio
14: bl   dakota_gpio_out_bit   ; with r1 = caller's value
```

It forwards the caller's value unchanged, and the only values it is ever
called with are 0 and 1.  So `dakota_gpio_out_bit(gpio, v)` sets the pad to
**logical v**.  Whether the pad is active-high at the pin is a TLMM property
we do not have; the AVM layer adds no inversion here.

`dakota_gpio_ctrl(gpio, 0, 1)` is the same call shape used elsewhere with
`dir = 0`, and `Check_TDMInterface` uses `dakota_gpio_ctrl(gpio, 0, 0)` for
pure input reads (see `fon-d06-pcm-pinmux.md`).  So `(gpio, 0, 1)` = request
as output, `(gpio, 0, 0)` = request as input.

### 2.2 Delay length

The loop counters are 11 before release and 16 after.  Their unit depends on
the loop body at `0xc14` / `0xc24`, which is a call to `_cond_resched`-style
helpers; no fixed microsecond value is proven.  **The duration is
UNKNOWN**; only "non-zero, fixed count" is CONFIRMED.

## 3. Logical vs electrical polarity

| Layer | Assert | Deassert | Evidence |
|---|---|---|---|
| AVM board table param | `GPIO_OUT_ACTIVE_HIGH` | — | DTSI text |
| `dakota_gpio_out_bit` argument | **0** | **1** | `b4c`/`b98` |
| Pad electrical level | LOW | HIGH | **UNKNOWN** — TLMM + any external inverter |
| SC14448 reset pin | **UNKNOWN** | **UNKNOWN** | no datasheet pin, no trace |

Two things must not be merged:

1. `AVM_DEF_HW_PARAM_GPIO_OUT_ACTIVE_HIGH` describes how the AVM **software**
   wraps the call.  Its expansion is not in the GPL drop, and the value is
   not visible in any recovered code path.
2. The sequence drives logical **0 to assert**.  If the label
   "ACTIVE_HIGH" applied to this signal, that would be contradictory, so
   either the label does not apply to reset, or "ACTIVE_HIGH" means something
   other than "assert = 1".  **This contradiction is not resolvable from the
   available artifacts** and is recorded as UNKNOWN.

A 74LVC1G04 near the chip could invert between the pad and the pin, which
would reconcile the two readings — but that is a hypothesis, see
`fon-d06-inverter-hypotheses.md`.

## 4. When reset happens relative to the upload

```
b3c..b54   assert (level 0)
b58..b64   delay 11
b84..b9c   deassert (level 1)
ba0..bac   settle 16
b74        log_piglet(...)
b80        msm_dectuart_init(...)      <-- UART configured after reset
```

So the order is **reset pulse first, UART afterwards**, and only then the
first-level/second-level `dectfw` transfer.  This matches the OEM boot log
(`11.9 s` piglet start, `17.77 s` second-level loaded).

**Consequence for our driver:** a firmware upload cannot succeed on a chip
that was never released from reset, and nothing in this path uses the UART to
perform the reset.

## 5. Is GPIO40 also touched anywhere else?

All `dakota_gpio_*` call sites in `dect_loader` are `0xb44`, `0xb54`,
`0xb9c`, `0xbfc`; `0xb44`/`0xb54`/`0xb9c` are the reset block above.  The
`XBIT_*` helpers operate on different profile slots (`+0xc`, `+0xd`, …), i.e.
the no-EMIF FPGA bit-bang pins, not reset.

`0xbfc` (`dakota_gpio_ctrl`) sits after the block and belongs to the
following stage; it is not part of the reset pulse.

## 6. Stage table

| Stage | Function / module | GPIO operation | Level | Evidence |
|---|---|---|---|---|
| Boot | — | none | — | no pin touching before piglet |
| Loader init | `get_profile()` `0x3844` | reads `gpio_avm_dect_reset` into `profile+0x28` | n/a | **CONFIRMED** |
| Reset assert | `dect_loader()` `0xb44`,`0xb54` | `ctrl(gpio,0,1)`, `out_bit(gpio,0)` | **0** | **CONFIRMED** |
| Reset release | `dect_loader()` `0xb9c` | `out_bit(gpio,1)` | **1** | **CONFIRMED** |
| Firmware upload | `msm_dectuart_init` `0xb80` then `dectfw_*` | UART, not GPIO40 | — | **CONFIRMED** (order) |
| Normal run | `pcmlink.ko` | does not touch reset | — | **INFERRED** from absence of the name in `pcmlink` |
| Error recovery | `dect_loader` re-entry (`piglet_loader_thread`) | repeats the same block | 0 → 1 | **INFERRED** |

Recovery is INFERRED: `dect_loader` is re-entrant from the loader thread and
the block has no "already released" guard, but no retry counter around it was
recovered.

## 7. Under OpenWrt the line reads 0 as an input

Stage A measured GPIO40 as an **unclaimed input reading 0**.  With the
sequence above, logical 0 is the **assert** state, so a chip whose reset line
is still low has never been released.  That is consistent with the SC14448
not running under OpenWrt — but consistency is not proof; the pad could also
be pulled low externally.  **INFERRED**, not CONFIRMED.

## 8. Residual unknowns

| Question | Why it is open | How to close it |
|---|---|---|
| Electrical level at the SC14448 pin for logical 0/1 | no datasheet pin, no trace, possible inverter | scope the pad and the chip side together |
| Reset pulse duration | loop unit not resolved | measure, or read the loop body |
| Is GPIO40 also an input at some point? | no read of `+0x28` besides the two writes | full-module callgraph |
| Does the pad default to output before `ctrl()`? | depends on TLMM reset value | TLMM register dump (read-only plan) |
