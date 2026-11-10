# E3.4 bounded bring-up CFG check

The E3.4 analyzer verifies the direct edge from fill exit (`0x25FAA` /
`0x26760`) into the selected routine (`0x2558` / `0x1E0C`). It checks
every sequential instruction from the first BMC candidate write through
the `0x00FF6006 ← 0` store, rejecting missing fallthrough or conditional
jumps in that region. It separately checks the `0`, `0xF0`, `0x80`, and
`0` value definitions/operands at their selected stores. This replaces
the constant boolean in E3.3.

The routine includes calls; a successful return and lack of asynchronous
interleaving are **assumptions**, and the pre-fill DIP control state is
unknown. `0x80` and `0` mean stop/start *only on SC14480*; no SC14448
register semantics or stopped-DIP state during fill is established.
