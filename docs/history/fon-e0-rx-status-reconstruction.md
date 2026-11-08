# FON-E0 — RX slot-5 status reconstruction

> **Status: offline static analysis.**
> `pcmlink.ko` SHA256
> `6620510bc1d4b0f4d670e1e93d3f308dc3002785d3129521156eb5e1bc4a363b`.
> No hardware or firmware execution.

`PutRxDMA` (`0x9a60`) reads a 16-bit status word from the RX DMA frame and
writes a decoded value to the virtual register table.  The Linux-side
transformation is proven; the SC14448 meaning of the status bits is not.

---

## 1. Instruction-level path

```text
status = u16 [rx_frame + EOR(0x0a, 2)]

if (status & 0x8000):
        raw_status_slot = status
        mark event bit 0x1000
        no register-0x44 update
else:
        if ((status & 0xfffffc00) != 0x4000)
                raw_status_slot = status ? status : 0xbad00000
        reg44 = 0x00020008
              | ((status << 3) & 0x00000f00)
              | ((status << 4) & 0x000000ff)
        value_table[0x44] = reg44
```

The source confirms `TDMPriv+0x73c` is the raw status/event slot and
`TDMPriv+0x750` is the value-table entry for register `0x44`.

## 2. Bit mapping

| RX status bit | Destination in reg 0x44 | Linux-side proof | SC14448 meaning |
|---:|---|---|---|
| 0 | bit 4 | `(status << 4) & 0xff` | **UNKNOWN** |
| 1 | bit 5 | same | **UNKNOWN** |
| 2 | bit 6 | same | **UNKNOWN** |
| 3 | **bit 7 (hook for SLIC0)** | same; `slic_get_hook_state` extracts bit 7 | **INFERRED hook/line state** |
| 4 | not mapped | shifted out by masks | **UNKNOWN** |
| 5 | bit 8 | `(status << 3) & 0xf00` | **UNKNOWN** |
| 6 | bit 9 | same | **UNKNOWN** |
| 7 | bit 10 | same | **UNKNOWN** |
| 8 | bit 11 | same | **UNKNOWN** |
| 9-14 | not mapped to reg 0x44 | masks | **UNKNOWN** |
| 15 | special: no reg-0x44 update | `tst #0x8000` | **UNKNOWN marker** |

`reg44` also contains constants `0x00020008` (bits 3 and 17).  The read mask
for register `0x44` is `0x01100fff`; bit 17 is not in that mask, so it is
served from the shadow/current table rather than the live status path.  Only
bits 0-11 of reg44 are in the read mask; hook bit 7 is one of them.

The hook extraction is:

```text
hook = (reg44 >> 7) & 1
```

Therefore **status bit 3 -> reg44 bit 7 -> hook**.  Calling this bit
"off-hook" is an interpretation from the caller name, not a datasheet fact.

## 3. Markers and invalid handling

| Status condition | Raw status slot `+0x73c` | reg44 |
|---|---|---|
| bit 15 set | status | **not updated** |
| `(status & 0xfffffc00) == 0x4000` | **not updated** | updated normally |
| status == 0 | `0xbad00000` | updated normally |
| other | status | updated normally |

`0x4000` and `0x8000` are therefore **not interchangeable**:
`0x8000` suppresses the register update; `0x4000` does not.

## 4. Register 0x44 read path

`lpcmlink_ul_readregister` does not issue a hardware read.  It merges the
current value table with the shadow using the metadata read mask:

```text
value = ((real ^ shadow) & read_mask) ^ shadow
```

For register `0x44`, `real` is the value written by `PutRxDMA`, and the read
mask is `0x01100fff`.

## 5. What remains unknown

- physical meaning of status bits 0-2, 4-14;
- whether bit 3 is hook switch, loop current, or a threshold;
- whether `0x4000`/`0x8000` are frame markers, fault flags or something else;
- the SC14448 firmware site that assembles the status word;
- the electrical line interface that produces it.

No bit is named beyond the proven Linux-side mapping.  The only semantic label
is the **inferred** hook bit.
