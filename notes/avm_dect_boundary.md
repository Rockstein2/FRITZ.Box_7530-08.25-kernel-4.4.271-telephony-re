# `avm_dect.ko` — `dect_io` boundary

Short static check before Phase 2. Source: `modules/avm_dect/avm_dect.ko`
(ARM EABI5, kernel 4.4.271, not stripped).

## Exported boundary

```text
avm_dect_if_init    0xad54  size 20
avm_dect_if_deinit  0xad68  size 20
avm_dect_if_tx      0xada4  size 212
```

`avm_dect_if_init(handler)` stores the handler pointer in a global.
`avm_dect_if_deinit()` clears it. `dect_io` registers `dect_uicp_from_dect`
through this call.

## `avm_dect_if_tx` contract

Input (as passed by `dect_io` after dropping the 4-byte outer header):

```text
byte 0      channel / transport selector, observed 0x14
bytes 1..2  AVM primitive, little-endian
bytes 3..   payload
length      includes byte 0
```

Observed control flow:

```text
if handler == NULL:
    return -EIO (-5)

channel = ptr[0]
primitive = le16(ptr[1..2])
length--                       // exclude channel byte
if primitive == 0x2fba:
    special 3-byte/length handling
call internal transport(channel, length, ptr+1)
return 0
```

This confirms that the AVM transport, not `dect_io`, owns the `0x14` channel
byte and the primitive/payload split. `dect_io` only validates the outer
length and forwards everything after its 4-byte header.

## Consequence for a clean driver

A mock/reimplementation must expose a transport operation equivalent to:

```c
int avm_dect_tx(u8 channel, const void *primitive_and_payload, size_t len);
```

or keep the original `avm_dect_if_tx(ptr, len)` byte layout. It must not treat
`ptr` as pure payload: byte 0 is the channel and bytes 1..2 are the primitive.

`dect_io` callback direction:

```text
avm_dect -> dect_uicp_from_dect(data, len)
    data[0..1] = primitive
    data[2..]  = payload
```

The callback path is documented and tested only statically; no module was
loaded.

## Confidence

| Statement | Confidence |
|---|---|
| init/deinit store/clear callback | high |
| tx returns `-EIO` without handler | high |
| tx strips channel and decrements length | high |
| special primitive `0x2fba` branch | medium-high |
| exact internal transport semantics | medium (out of Phase 2 scope) |
