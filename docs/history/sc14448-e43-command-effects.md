# E4.3 selected case dataflow

Case 7 (`0x9ED0`/`0x274D2`) loads pointer and length from input payload+3
and +7, calls `0x9E10`/`0x27412`. Helper passes `r2=0x22` into allocator,
changes the **state** byte at `payload−2` to `0x23`, writes `0xFFF1` at
payload+0, subtype 8 at +2, pointer and length at +3/+7, then calls a
byte-copy helper with a stack-passed count. Allocation publishes before
payload completion; no interrupt/all-path ordering proof covers this
window. A next consumer is not identified by mere queue proximity.

Case 9 takes low 16 bits of payload+3 pointer as `r2` for helper, which
looks up indexed records and issues register-pair `jal` instructions.
Only its first indirect site has a locally preserved target pair.

Case 10 passes payload+3/+4 bytes to a helper, compares image-dependent
thresholds, calls a lookup and a further helper with an indexed RAM store.
No semantic function name is assigned to either input byte. Case 13 performs
the already verified load32/load16/store16 chain; the upstream payload
source and destination range remain unknown. No MMIO effect is inferred.
