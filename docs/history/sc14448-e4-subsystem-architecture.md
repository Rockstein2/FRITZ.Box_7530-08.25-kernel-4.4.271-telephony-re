# E4 evidenced architecture graph and blockers

The reproducible `cr16-e4-subsystem-graph.json` contains four checked
edges: main→item dispatcher, dispatcher→parser, main→TX pump, TX pump→
effective `0x00FF4902`. Each has a call or peripheral instruction and bytes.
No placeholder UART-RX, DIP, DSP, PCM, GPIO or FON edge is emitted for visual
completeness. Individual vector handler evidence lives in the interrupt
report; queue/state evidence lives in shared-memory report.

The first missing transport edge is host/receiver→producer of the RAM item
consumed in the parser. The second is decoded item→documented subsystem
state changes. The third is physical PCM/analog-FON source and sink.
Indirect entries, interrupted updates and branch/code overlap restrict
global coverage. Q75 is not closed; Q46/Q55 have no new proven data.
