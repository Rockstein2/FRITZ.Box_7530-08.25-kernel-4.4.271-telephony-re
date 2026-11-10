# E3.5 candidate ingress register inventory

`cr16-e35-pcm-register-candidates.json` enumerates resolved read/write sites
in the effective `0x00FFxxxx` and `0x01027Fxx` windows, preserving raw bytes,
access width, architectural address and known address provenance. Candidate
reference names belong to SC14480 or SC14CVMDECT, **not** SC14448.
Window membership alone does not identify an address as a peripheral.

`cr16-e35-pcm-ingress.json` shortlists the observed `0x00FF4858` pinmux,
`0x00FF4868` pinmux and `0x00FF6006` DIP-control candidates; the latter is
not treated as PCM merely because the address appears near interrupts.
The SC14480 PCM input register range `0x01027FAE…0x01027FB4` has **zero
resolved reads in both images** under this analysis. Many indexed/unknown
addresses remain; no global negative follows. A physical 8-slot AVM wire
mapping to the four-channel related-device interface is unproven.

The earliest missing link is from the Linux *logical* slot-5 control word to
a specific SC14448 hardware-provided source. EOR-2 swaps words in DMA RAM;
it does not establish the electrical wire order or SC14448 register width.
