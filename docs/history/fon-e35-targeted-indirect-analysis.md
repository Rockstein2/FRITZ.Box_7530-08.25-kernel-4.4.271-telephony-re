# E3.5 indirect triage: no target resolution

`cr16-e35-targeted-indirect-paths.json` lists indirect transfer sites
within 32 bytes of *resolved peripheral reads* under the selected scan;
returns via `jump (ra)` are excluded. This is an inventory for follow-up,
**not** a dataflow path. The scan does not prove target-address producer,
stack/register propagation, table width, endianness, callee identity or
effects. No indirect site is promoted to a FON consumer.

The proximity filter intentionally misses indirect routes via DMA or a
previously unknown address. A consumer proof still requires a verified
physical/logical PCM source and instruction-level path through control
decoding to side effects; a nearby call is not such evidence.
