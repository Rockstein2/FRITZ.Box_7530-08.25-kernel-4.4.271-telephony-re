# E4.3 conditional state graph, not a runtime trace

Selected conditional edges: case 7 → new queue record/state byte; case 9
→ case-10 helper (first indirect JAL under CR16B model); case 10 → lookup
→ helper indexed RAM store candidate; case 13 → word store through a
symbolic pointer. Each starts behind parser's unproved tag-`0x23` input.

The case-10 store's indexed address/value and case-13 pointer target are
not closed by interprocedural aliases; neither reaches a proved peripheral
register. No producer-backed command→event or command→TX edge follows from
these selected instructions. `cr16-e43-state-transitions.json` separates
conditional edges from the empty set of established producer-backed edges.
