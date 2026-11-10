# E3.5 FON control candidate boundary

`cr16-e35-fon-control-consumers.json` lists literal `0x4000`/`0x8000`
occurrences as **search seeds only**. A mask occurrence does not imply
control-word provenance. There is no proved consumer of Linux normal or
special control and no valid FON_SLOT5_CONSUMER_PROVEN status.

Both images also contain a bounded RAM-bit to GPIO-RMW chain (normal
`0x2801E`; p2test `0x3CD8`). Its conditional branch targets and output
operations are checked against firmware instructions. Source is local RAM,
not identified PCM data; output at effective `0x00FF4860` has only a
SC14CVMDECT **related-device** GPIO name. Thus local input/output effects
are real, but hook/ring/line/FON interpretation is **UNRESOLVED**.

Normal control: marker bit14 plus field bits 0…9 from virtual reg48/reg2c.
Special: `special | 0x8000` from virtual reg30 (`TDMPriv+0x7F4`);
the payload is not masked, so the two markers need not be exclusive.
Linux ring toggles reg48 bits5/6, but this alone assigns no SC14448 pin
meaning. Consult `fon-sc14448-pcmlink-protocol.md` for exact shifts.
