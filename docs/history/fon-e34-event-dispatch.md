# E3.4 targeted DSP/DIP dispatch verification

`cr16-e34-event-dispatch.json` verifies, independently for normal and
p2test, the DSP gate's nonzero edge to skip, the OR of `0x0C` on the zero
path, the bit-3 false edge to bit-2 test, the bit-2 false edge to skip, and
the direct targets of both helper calls. It also checks the DIP zero gate
in both images and the `0x0E`, `0x0F` and other direct branches in p2test.
Normal's indexed-state path is not fully resolved. Bit-test/branch ISA
semantics and downstream indirect calls remain outside this CFG-edge proof.

Neither event family has a proven FON/PCM slot-5 input → consumer chain.
No global negative claim about other firmware paths is made.
