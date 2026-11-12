# E4.1 TX byte pump and response boundary

Normal TX pump `0x9F84` and p2test `0x9BC8` use candidate byte buffers at
`0xAFD` / `0xA5D`, test cursor equality, read a byte, increment/reset a
counter near the `0x7F0` candidate length, and access architectural
`0x00FF4902` (write), `0x00FF4904` (strobe), `0x00FF4900` (bit5 test).
P2test `0x9C82…0x9C8E` forms `base+index`, stores a byte, increments an
index; the analogous normal buffer producer is unresolved.

Main calls TX in both images. Case 7 creates a *queue item*, not directly
a TX byte. No proven case→TX response association or response frame header,
checksum, length or echo is reported. Other asynchronous events may enqueue
TX-independent work. Physical UART transmission was not observed.
