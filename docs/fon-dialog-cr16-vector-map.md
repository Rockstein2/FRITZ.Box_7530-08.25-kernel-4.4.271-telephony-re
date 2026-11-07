# SC14448 interrupt/dispatch table (INTBASE = 0x24)

Status: **offline analysis.**  L1 bytes, L2 decode, plus an external
reference used as a *candidate* only.

Reference: [TobleMiner/dialog-cr16c-uart-boot](https://github.com/TobleMiner/dialog-cr16c-uart-boot),
commit `3d041a68`, MIT, Copyright 2022 Tobias Schramm.  It targets
SC14441/Gigaset hardware.

Report: `tools/reports/cr16-vector-map.json` from `tools/cr16_vector_map.py`.

---

## 1. The encoding, confirmed by the reference

`device/vectors.s`:

```asm
vector_table_fixup:
        loadd 0x0(r1,r0), (r5,r4)
        lshd $-1, (r5,r4)              ; shift right by one bit
        stord (r5,r4), 0x0(r1,r0)
```

The stored 32-bit value is the handler byte address **divided by 2**.  Our
own data confirms it: `0x146E5 × 2 = 0x28DCA`, an instruction boundary; the
stored value alone is odd and therefore not an address.

## 2. The table, both images

`INTBASE = 0x24`, 32 entries, `0x24`–`0xA3`.

| idx | reference name | normal | p2test | handler |
|---|---|---|---|---|
| 0–23 | reserved / traps / uart / spi / tim0 | `0x28DCA` | `0x9FFC` | shared stub (`nop`,`retx`) |
| **24** | `tim1_int` | **`0x28996`** | **`0x2772A`** | real handler |
| 25 | `clk100_int` | `0x28DCA` | `0x9FFC` | stub |
| **26** | `dip_int` | **`0x28CD0`** | **`0x27C88`** | real handler |
| 27, 28 | `ad_int`, `spi2` | `0x28DCA` | `0x9FFC` | stub |
| **29** | `dsp_int` | **`0x28A94`** | **`0x27914`** | real handler |
| 30 | `reserved30` | `0x28DCA` | `0x9FFC` | stub |
| 31 | `reserved31` | `0x1FFFE0A02` | same | out of range, not a handler |

Both images have the **same set** of real handlers ({24, 26, 29}) and the
same shared stub.  Only the addresses differ.

## 3. What each real handler does

| idx | site (normal) | first instructions | memory touched |
|---|---|---|---|
| 24 | `0x28996` | `push $3,r0`; increment a counter at `0x2B6`; `storw $0x100,0xF5402`; `pop`; `retx` | `0x2B6`, `0x000F5402` ← `0x0100` |
| 26 | `0x28CD0` | `push $7,r0,RA`; increment a counter at `0x93C9`; `loadw 0xF6006`; `storw $0x400,0xF5402`; `bal 0x28732` | `0x93C9`, `0x000F6006`, `0x000F5402` ← `0x0400` |
| 29 | `0x28A94` | `push $8,r0,RA`; read/write `0x93CB`; walk `0xD6`; `ei`; … `storw $0x2000,0xF5402`; `retx` | `0x93CB`, `0xD6`, `0x000F5402` ← `0x2000` |

All three write a **single bit** to `0x000F5402` ("reset interrupt pending"
in the reference, `RESET_INT_PENDING_REG`): `0x0100`, `0x0400`, `0x2000`.

**The bit numbers do not match the reference's UART bits** (UART TI = `1<<5`,
RI = `1<<4`).  So either the SC14448 assigns different bits to different
sources, or the reference numbering does not carry over.  What *is*
established: the three handlers acknowledge three different pending bits.

## 4. Vectors 20, 21, 22 — the hypothesis from the task does not hold

The task proposed that `0x74`/`0x7C` (vectors 20/22) are UART RX and SPI.
Measured:

| vector | table address | normal | p2test |
|---|---|---|---|
| 20 (`uart_ri_int`) | `0x74` | `0x28DCA` stub | `0x9FFC` stub |
| 21 (`uart_ti_int`) | `0x78` | `0x28DCA` stub | `0x9FFC` stub |
| 22 (`spi_int`) | `0x7C` | `0x28DCA` stub | `0x9FFC` stub |

**Those three vectors are stubs.**  The earlier reading came from
`(0x74-0x24)/4 = 20` combined with the values *at those offsets being
different*, which they are not — `0x74`, `0x78` and `0x7C` all hold the same
`0x146E5` in `normal`.

Therefore **the interrupt numbering of the SC14448 firmware does not
confirm the SC14441 numbering**: the vectors that are UART/SPI on the
reference are unused here, and the three that are used (24, 26, 29) would be
`tim1`, `dip`, `dsp` under the reference naming.

## 5. Status

| Claim | Level |
|---|---|
| the table is at `0x24` and has 32 entries of `u32le` | L1 |
| the value is a handler address ÷ 2 | L2 (reference + our boundaries) |
| vectors 24, 26, 29 are real handlers | L2 |
| they acknowledge three different bits of `0x000F5402` | L2 |
| their *names* (tim1/dip/dsp) | **candidate only** — SC14441 numbering |
| UART/SPI are vectors 20/22 | **refuted for this firmware** |
