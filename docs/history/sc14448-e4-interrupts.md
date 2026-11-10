# E4 raw-vector architecture

`cr16-e4-interrupt-architecture.json` lists all 31 vector entries in each
image and verifies their raw stored address (`byte target / 2`) against
the input firmware. The reference SC14441 numbering proposes names such as
tim1/dip/dsp but does **not** prove the SC14448 electrical trigger.

Selected handlers: normal `0x28996` timer candidate, `0x28CD0` DIP,
`0x28A94` DSP; p2test `0x2772A`, `0x27C88`, `0x27914`.
Earlier E3.3/E3.4 reports trace DIP/DSP bounded branches, interrupt clear
and helper calls, including the DSP OR `0x0C` before bit2/bit3 tests.
Both UART-named vectors are stubs here. A timer/event effect on the main
loop is a candidate until memory-write→read and scheduling paths close.
