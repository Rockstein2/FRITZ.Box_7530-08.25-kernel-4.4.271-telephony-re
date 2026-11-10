# E3.5 DIP versus FON

`cr16-e35-dip-caller-classification.json` enumerates all direct callers of
the indexed writer in each image (10 normal, 14 p2test). A direct call
alone does not establish DECT, DSP or PCM input. Their classification is
`UNKNOWN` pending entry and argument provenance. The normal `0x25FD4` /
p2test `0x2678A` known local caller supplies `0x12AA` at index 2 (E3.4),
but neither is linked to FON slot 5. Save/restore paths are not classified
as PCM. Q46/Q55 are unchanged. Further DIP opcode reverse engineering is
not prioritized absent a new PCM/FON connection.
