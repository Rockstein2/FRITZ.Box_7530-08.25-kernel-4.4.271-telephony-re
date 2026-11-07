# First-level image: full disassembly and CFG

Status: **offline analysis** of `firmware/dectfw_firstlevel_441_slow.hex`.
L1 bytes, L2 decode, L3 control flow.

The image is **one block of 618 bytes at `0x10080`** (Intel record type 04
sets the upper address to `0x00010000`, then a single data record at
`0x0080`).  It ends at `0x102E9`.

---

## 1. Register and I/O map used by the image

| Address | Access | Site(s) | Meaning |
|---|---|---|---|
| `CFG` (proc. reg) | read/write | `0x10080`, `0x10088`, `0x10278`, `0x10280` | bit 8 toggled |
| `PSR` (proc. reg) | read/write | `0x1008C`, `0x10094` | bits 9 and 11 cleared |
| `0x000F4020` | `storb` | `0x1009C` | byte `0x30` |
| `0x000F400E` | RMW | `0x100A0`–`0x100AA` | clear bits 0–2, set bit 0 |
| `0x000F4000` | RMW | `0x100AE`–`0x100C6`, `0x100FC` | clear/set bits 0–4, `sbitw $7` |
| `0x000F4838` | bit | `0x100CA`, `0x10270` | set / clear bit 0 |
| `0x000F4836` | RMW | `0x100CE`–`0x100E2`, `0x10254`–`0x1026C` | handshake bits |
| `0x000F4900` | RMW, `loadb` | `0x100E6`–`0x100F8`, `0x102A8`, `0x102D6` | **UART status** |
| `0x000F4902` | `loadw`/`storw` | `0x102BE`, `0x102CE` | **UART data** |
| `0x000F4904` | `storw $1` | `0x102E4` | TX strobe |
| `0x000F4906` | `storw $1` | `0x102BA` | RX strobe |
| `0x000F4C00` | `storw $0xFF` | `0x102A0`, `0x102CA` | watchdog or timer kick |

## 2. Two helper functions

### `0x1029C` — receive one byte

```text
0x1029C  movw   $0xff, r0
0x102A0  storw  r0, 0xf4c00          ; kick
0x102A4  movw   $0xc350, r1          ; 50000 iterations
0x102A8  loadb  0xf4900, r0
0x102AC  tbit   $6, r0               ; PSR.F = bit 6
0x102AE  bfs    +0x102BA             ; bit 6 set -> data ready
0x102B0  addw   $-1, r1
0x102B2  cmpw   $0, r1
0x102B4  bne    -0x102A8             ; poll
0x102B6  movw   $0, r0               ; timeout: r0 = 0
0x102B8  jump   (ra)                 ; return
0x102BA  storw  $1, 0xf4906          ; acknowledge
0x102BE  loadw  0xf4902, r2          ; the byte
0x102C2  movw   $1, r0               ; r0 = 1
0x102C4  jump   (ra)                 ; return
```

**Contract:** returns `r0 = 1` and the byte in `r2`, or `r0 = 0` on timeout.

### `0x102C6` — send one byte

```text
0x102C6  movw   $0xff, r0
0x102CA  storw  r0, 0xf4c00
0x102CE  storw  r2, 0xf4902          ; write the byte
0x102D2  movw   $0xc350, r1
0x102D6  loadb  0xf4900, r0
0x102DA  tbit   $5, r0
0x102DC  bfs    +0x102E4             ; bit 5 set -> transmitter ready
0x102DE  addw   $-1, r1
0x102E0  cmpw   $0, r1
0x102E2  bne    -0x102D6
0x102E4  storw  $1, 0xf4904          ; strobe (also on timeout)
0x102E8  jump   (ra)
```

**Contract:** takes the byte in `r2`, returns nothing.

`tbit $n, r` copies bit `n` of `r` into `PSR.F` (CR16A manual, `TBIT`);
`bfs` is "branch if flag set".  So the two bit tests are genuinely "status
bit 6 set?" and "status bit 5 set?".

## 3. Control flow

```text
0x10080  CFG bit 8 <- 0
0x1008C  PSR bits 9,11 <- 0
0x10098  I/O bring-up (0xf4020, 0xf400e, 0xf4000, 0xf4838, 0xf4836,
                      0xf4900, sbitw $7 on 0xf4000)
0x10100  retry: r2 = 2
0x10102  call 0x102C6 (send)          -> sends r2
0x10106  call 0x1029C (receive)       -> r1? no: r0/r2
0x1010A  if r0 == 0 -> 0x10100        (timeout: restart)
0x1010E  if r2 == 2 -> 0x10118
0x10112  if r2 != 1 -> 0x10100
0x10116  -> 0x1011E                   (header path)
0x10118  call 0x1029C
0x1011C  -> 0x1010A
0x1011E  read four bytes, build a 32-bit big-endian value in (r13)
0x1014C  if (r13) != 0 -> 0x10180     (block/data path)
0x10150  send 0x15, then the four bytes of (r13) big-endian
0x1017C  br <unresolved>              (hand-off)
0x10180  send 0x06
0x10186  r11 = 0 (checksum), (r10,r9) = 0 (total), (r6,r5) = 0
0x1018C  r3 = 4
0x1018E  receive: if timeout -> 0x1028A (error)
0x10198  checksum ^= byte; shift into (r12); counter++
0x101C4  ...
0x101D4  r3 = 6
0x101E0  ...
0x1021A  loop while (r8,r7) != 0
0x10220  r3 = 7
0x10224  receive byte, store at (r12)++, counters++
0x10236  loop while (r6,r5) < (r8,r7)
0x1023A  loop while (r10,r9) < (r13)
0x10240  send the checksum r11
0x10246  receive a reply; retry while timeout
0x1024E  if reply != 0x06 -> 0x10100 (restart the whole exchange)
0x10254  I/O handshake
0x10278  CFG bit 8 <- 1
0x10284  6-byte br (target form not decoded, Q51)
0x1028A  error: send 0x15, then r3
0x10298  br <unresolved>              (hand-off)
```

## 4. The two exits to low addresses

| Site | Bytes | Target |
|---|---|---|
| `0x1017C` | `e0 18 85 ff` | **UNKNOWN** (Q51: 4-byte `0x18` form) |
| `0x10298` | `e0 18 69 fe` | **UNKNOWN** (same form) |
| `0x10284` | `10 00 ef 0e 85 fd` | **UNKNOWN** (Q51: 6-byte form) |

The `0x18` family decodes inconsistently with the current rules: using
`disp = word1` reproduces three known second-level targets exactly, but
gives `0x10101` here, and `0x10101` is not an instruction boundary.  The
target is therefore **not established**.  It must not be described as
`0x7C`; that reading came from a different hypothesis that does not fit the
known cases.

## 5. What the image does *not* contain

* no code at `0x7C` — the image starts at `0x10080`;
* no write below `0x10000`;
* no `INTBASE`, `ISP` or `USP` access;
* no instruction that masks or rebases an address;
* no branch into the second-level code range `0x0`–`0x28DCD`.

The image configures I/O and speaks a byte protocol; it does not place code
in memory itself.
