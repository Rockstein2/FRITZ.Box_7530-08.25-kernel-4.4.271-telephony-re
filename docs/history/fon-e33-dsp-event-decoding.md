# E3.3 bounded `dsp_int` paths

Normal `0x28A94…0x28B08`; p2test `0x27914…0x27988`. Static firmware
value at `0xD6` is `0x01027F80` in both. `loadd 0xD6` transfers that value
into a register pair, `addd $0x58` forms `0x01027FD8`, and the handler
loads and writes back a word at that pair-derived address. The low-byte
`& 0x0E` gate at `0x28AD0` / `0x27950` skips both helpers when nonzero.
On the zero path `orw $0x0C,r10` sets bits 2 and 3 **before** testing them;
bit-3 invokes `0x3B28` / `0x27744` and bit-2 invokes `0x3B38` / `0x27754`.
These tests must not be read as direct incoming-vector bit meanings. The
final acknowledgement writes `0x2000` to effective
`0x00FF5402`. This is 32-bit pair arithmetic, not an abs20 access.

The bit-3 helper loads a structure pointer, copies a word from offset +6
to +10 and stores zero at +12. The bit-2 helper has further branches and
indirect state accesses; its downstream semantics are not closed. The
counter bases `0x2C4` / `0x224` and +14/+16 fields are visible, but their
operational role is not proven. No resolved *direct* writes overlapping
`0xD6…0xD9` were found in the bounded address-use report; that does not
exclude indirect stores, copies or loader relocation. SC14480 p. 177 names
`DSP_INT_REG` and describes W1C, but this remains related-device evidence,
not an SC14448 hardware proof. No 8 kHz claim follows from these paths.
