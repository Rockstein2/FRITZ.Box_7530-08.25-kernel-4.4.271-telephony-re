# `dect_io.ko` — reconstructed ABI and behavior

Phase 1 static analysis. Source module:

```text
modules/dect_io/dect_io.ko
SHA-256 verified by SHA256SUMS
ARM EABI5, kernel 4.4.271, not stripped
```

Addresses below are section offsets for the module and PIE virtual addresses
for `dect_manager`. They are not runtime addresses after relocation.

## 1. Module overview

`dect_io.ko` is a small character-device shim between the AVM userspace
`dect_manager` and `avm_dect.ko`.

It provides:

```text
/dev/dect_io
```

and one AVM callback:

```text
avm_dect_if_init(dect_uicp_from_dect)
```

The device is not a DECT driver. It does not touch the DECT radio, UART,
GPIO, PCM, or firmware. It only:

1. accepts framed messages from userspace;
2. passes them to `avm_dect_if_tx()`;
3. queues framed messages received from `avm_dect.ko`;
4. wakes a blocking reader and returns those messages.

The module cannot work without `avm_dect.ko`.

### Init and exit

`init_module` and `dect_uicp_file_init` are aliases (`0x0`, size `0x184`,
`.init.text`).

Init sequence, confirmed by disassembly:

```text
alloc_chrdev_region(&dect_uicp_file.dev, 0, 1, "dect_io")
cdev_alloc()
cdev->ops    = &dect_uicp_file_fops
cdev->owner  = THIS_MODULE
kobject_set_name(cdev_kobj, ...)
cdev_add(cdev, dev, 1)
avm_dect_if_init(dect_uicp_from_dect)
avm_DebugCallRegister(...)
```

Exact error unwinding is kernel-4.4-specific; the important external effects
are dynamic major allocation, minor 0, cdev registration, and callback
registration.

`cleanup_module` and `dect_uicp_file_cleanup` are aliases (`0x0`, size `0x6c`,
`.exit.text`):

```text
avm_DebugCallUnRegister(dbg_handle)
avm_dect_if_deinit()
cdev_del(cdev)
unregister_chrdev_region(dev, 1)
```

The init script creates the node manually:

```sh
major=`grep dect_io /proc/devices`
major=${major%dect_io}
mknod -m 0660 /dev/dect_io c "$major" 0
```

Confirmed from `reference/init.d/E41-capi`.

### Module parameters

`debug_level` is a 32-bit global at `.data+0x0`, default `3`.
`dect_uicp_parse_cmdline()` recognizes the `debug` command-line token and
`dect_uicp_handle_debug_cmd()` accepts values `0..15`.

Debug bits from strings:

```text
bit 0  DEB_ERR
bit 1  DEB_WARN
bit 2  DEB_INFO
bit 3  DEB_TRC
```

## 2. `file_operations` mapping

`dect_uicp_file_fops` is at `.rodata+0xc8`, size 108 bytes.
Relocations give this exact mapping:

| fops offset | Method | Module offset | Behavior |
|---:|---|---:|---|
| `0x00` | `owner` | — | `THIS_MODULE` |
| `0x08` | `read` | `0x268` | blocking/queued framed read |
| `0x0c` | `write` | `0x72c` | framed transmit to AVM DECT stack |
| `0x1c` | `poll` | `0x000` | readable if queue nonempty; always writable |
| `0x20` | `unlocked_ioctl` | `0x58c` | commands `1` and `2` |
| `0x2c` | `open` | `0x164` | single-open enforcement |
| `0x34` | `release` | `0x0f0` | fasync cleanup, free private data |
| `0x40` | `fasync` | `0x09c` | `fasync_helper` only |

There is no `llseek`, no `compat_ioctl`, no `mmap`, and no `read_iter`/`write_iter`.

## 3. Userspace-to-kernel sequence

Observed `dect_manager` transmit path:

```text
dect_manager
  dmgt_dect_to_api()
       |
       | build 7-byte prefix + payload
       v
  write(/dev/dect_io, frame, 7 + payload)
       |
       v
  dect_uicp_file_write()
       |
       | validate length + 4 == write_count
       | copy whole frame into static buffer
       | discard first 4 bytes
       v
  avm_dect_if_tx(frame + 4, header.length)
```

`dect_uicp_file_write()` does **not** propagate `avm_dect_if_tx()` failure.
It returns the original `write_count` on every otherwise valid frame, even
when `avm_dect_if_tx()` returns an error. The error is only logged when
`debug_level & DEB_WARN`.

### Write validation

Facts from `0x72c..0x97c`:

```text
count <= 3                 -> -EIO
count > 0x3040             -> -EIO
access_ok fails            -> -EIO, static buffer zeroed
copy_from_user fails       -> -EIO (partial copy remains)
count <= 6                 -> -EIO
u16le(frame[0]) + 4 != count
                           -> -EIO
```

On success:

```text
r0 = dect_uicp_from_user_buffer + 4
r1 = u16le(frame[0])
call avm_dect_if_tx(r0, r1)
return count
```

The `0x3040` limit is the size of the static `dect_uicp_from_user_buffer`
(`.bss+0x118`, 12352 bytes).

### Userspace frame written by `dmgt_dect_to_api`

Observed at `dect_manager+0x10e700..0x10e854`:

```text
offset  size  value / meaning
0x00    2     payload_len + 3
0x02    2     0x8052
0x04    1     0x14
0x05    2     AVM primitive, little-endian
0x07    N     payload
total         N + 7
```

The kernel `dect_io` checks only `u16(0) + 4 == total`; it ignores `0x8052`
and passes from offset 4 onward to `avm_dect_if_tx`. Therefore the AVM
transport receives:

```text
[0x14][primitive_le16][payload...]
```

with length `N + 3`. This was confirmed in `avm_dect_if_tx()`: it reads
byte 0 as the channel (`r8 = [ptr]`), the primitive at `[ptr+1]` as a
16-bit value, and decrements the length by one before processing.

## 4. Kernel-to-userspace sequence

`avm_dect.ko` calls the registered callback:

```text
avm_dect.ko
  -> dect_uicp_from_dect(data, len)
       data[0..1] = primitive
       data[2..]  = payload
```

`dect_uicp_from_dect()` at `0xbc4`:

1. checks `is_open` (`.bss+0x4`);
2. if closed, logs and discards;
3. rejects `len <= 1`;
4. calls `dect_uicp_fpapi_handle_to_user(data, len)`;
5. if the queue is nonempty, calls:
   `__wake_up(&dect_uicp_read_wait_queue_head, TASK_NORMAL, 1, NULL)`.

`dect_uicp_fpapi_handle_to_user()` at `0xa80` allocates `len + 0x19` bytes
with `dect_uicp_manage_kcalloc()` (which ORs `0x8000`, the observed zeroing
flag, into the GFP mask), then builds:

```text
entry+0x00  list.next
entry+0x04  list.prev
entry+0x08  total = len + 5
entry+0x0c  copied = 0
entry+0x10  u32: low16 = len + 1, high16 = 0x8053
entry+0x14  status = 0
entry+0x15  original message (len bytes)
```

It inserts the entry at the tail of `dect_uicp_to_api_list` under
`dio_spin_lock`.

### Userspace read path observed in `dect_manager`

`dmgt_dect_dev_read` at `0x115758..0x1158a0`:

```text
read(fd, hdr4, 4)                     // {u16 length, u16 0x8053}
if length > 0: read(fd, buf, length)
if hdr4[2] != 0x53: drop             // low byte of the 0x8053 tag
if length <= 2: drop
primitive = u16le(buf[1..2])
dmgt_dect_from_api(primitive, length - 3, buf + 3)
```

`buf[0]` is the status byte and is not checked by this caller.
Thus the complete read frame returned by the driver is:

```text
offset  size  value / meaning
0x00    2     N + 3  (status + primitive + payload)
0x02    2     0x8053
0x04    1     status = 0
0x05    2     AVM primitive
0x07    N     payload
total         N + 7
```

where `N` is the original AVM payload length. The original message length is
`N + 2` (primitive + payload); the `length` field is that plus the status
byte, `N + 3`.

### `dect_manager` call sites

Confirmed from the PIE disassembly:

```text
dmgt_dect_init            0x115a70  open64("/dev/dect_io", O_RDWR)
dmgt_dect_to_api          0x10e700  write framed message
dmgt_dect_dev_read        0x115758  read 4-byte header, then length bytes
dmgt_timer_get_system_ticks 0x12cab0 ioctl(fd, 1, &time8)
dmgt_dect_finit           0x115c94  close
```

There is no `O_NONBLOCK` in the open call and no direct poll/fasync use.
The only direct caller of `dmgt_manage_ioctl` uses command 1. See
`reports/dect_manager-dect_io-xrefs.txt` for exact addresses.

## 5. `dect_uicp_file_read` details

Offsets `0x268..0x58c`.

- Only one open is allowed, but the queue itself is global.
- `dect_uicp_to_api_list` is `.data+0x10`; its list head is used as the
  empty test.
- If the queue is empty:
  - `O_NONBLOCK` (`file->f_flags & 0x800`) -> `-EAGAIN` (`-11`);
  - otherwise wait on `dect_uicp_read_wait_queue_head` (`.data+0x4`);
  - signal interruption -> `-ERESTARTSYS` (`0xfffffe00`).
- If an entry exists:

```text
available = entry->total - entry->copied
chunk     = min(available, user_count)
source    = entry + 0x10 + entry->copied
copy_to_user(user_buf, source, chunk)
entry->copied += chunk
*ppos += chunk
```

- If `entry->copied == entry->total`:
  - remove the entry from the queue under `dio_spin_lock`;
  - `kfree(entry)`;
  - reset `*ppos` to zero.
- If partial, `*ppos` is advanced but the entry remains queued.
- If `copy_to_user` fails, returns `-EFAULT` (`-14`).
- If an entry has `total <= 6`, it logs `ill length`, still removes/frees it.
- `*ppos` is not used to seek within an entry; the per-entry `copied` field
  is authoritative. There is no `llseek`.

The returned data starts at `entry+0x10`, so the first returned bytes are
the 5-byte prefix:

```text
u16 length = original_message_len + 1  // original_message_len = 2 + payload_len
u16 tag    = 0x8053
u8  status = 0
```

then the original message (primitive + payload).

## 6. `poll`, `fasync`, `open`, `close`

### `poll` (`0x000`)

If `wait && wait->qproc`, calls:

```text
qproc(filp, &dect_uicp_read_wait_queue_head, wait)
```

Return mask:

```text
queue empty:      0x104 = POLLOUT | POLLWRNORM
queue nonempty:   0x145 = POLLIN | POLLRDNORM | POLLOUT | POLLWRNORM
```

There is no error/hangup condition.

### `fasync` (`0x09c`)

`private = filp->private_data` (`file+0x94` on this kernel).
Calls:

```text
fasync_helper(fd, filp, on, &private->fasync)
```

`private+0xc` is the fasync slot. The module imports `fasync_helper` but
**does not import or call `kill_fasync`**. New data wakes the read wait queue
only; SIGIO delivery is therefore incomplete/unused.

### `open` (`0x164`)

- atomically increments `dect_uicp_open_flag` (`.bss+0x0`);
- if the resulting count is greater than 1, returns `-EBUSY` (`-16`);
- rejects `O_APPEND` (`file->f_flags & 0x400`) and returns `-EFAULT` (`-14`)
  with the string `open O_APPEND not supported`;
- allocates a zeroed object from the kmalloc cache selected by
  `kmalloc_caches[6]` (observed `kmalloc_caches+0x18`);
- `private+0x8 = &filp->f_pos` (file+0x48); this field is not used by the
  read/write paths in this module;
- `private+0xc = 0` (zeroed allocation);
- stores `private` into `filp->private_data`;
- sets `is_open` (`.bss+0x4`) to 1;
- returns 0.

Allocation failure and O_APPEND failure share the same return value `-14`
(`-EFAULT`) in the disassembly; this is unusual but exact.

### `close` (`0x0f0`)

- if `private_data` exists:
  - `fasync_helper(-1, filp, 0, &private->fasync)`;
  - `kfree(private)`;
  - clear `private_data`;
- clears `dect_uicp_open_flag` and `is_open`;
- returns 0.

## 7. ioctl table

Handler: `dect_uicp_file_ioctl` at `0x58c`, registered as `unlocked_ioctl`.
Commands are raw integers; there is no `_IO` encoding.

| cmd | arg type | kernel action | return |
|---:|---|---|---|
| `1` | pointer to 8 bytes | write `{u32 jiffies, u32 250}` to user | 0 |
| `2` | pointer to 256 bytes | copy 256 bytes, NUL-terminate/truncate, `printk("%s\n")` | 0 |
| other | — | none | `-EFAULT` (`-14`) |

### cmd 1 — observed name `DECT_IO_IOCTL_GET_TIME`

Facts:

- checks `access_ok(VERIFY_WRITE, arg, 8)`;
- fills local `{jiffies, 250}`;
- `copy_to_user(arg, &local, 8)`;
- `access_ok` or copy failure -> `-EINVAL` (`-22`);
- success -> 0.

`dect_manager` call site: `dmgt_timer_get_system_ticks()` at
`0x12cab0..0x12cb28` calls `dmgt_manage_ioctl(fd, 1, &local8)`, takes the
first word (jiffies) as its return value and stores the second word (250)
through its output pointer. This is consistent with `jiffies` + `HZ`.

`dmgt_manage_ioctl()` at `0x11d374..0x11d42c` retries the syscall up to 10
times when `errno == EINTR`, then returns the last result.

### cmd 2 — observed name `DECT_IO_IOCTL_DEBUG_PRINT`

Facts:

- copies exactly 256 bytes from `arg` into the static `buf.25011`
  (`.bss+0xc`);
- if no NUL is present in 256 bytes, writes `...` at `buf[253..255]`;
- calls `printk("\x013%s\n", buf)` (KERN_ERR prefix);
- returns 0 even if `access_ok` or `copy_from_user` failed;
- copy/access failure zeroes the 256-byte buffer and sets the logged length
  to 256.

No direct caller of `dmgt_manage_ioctl(..., 2, ...)` exists in
`dect_manager`; the command appears to be a debug hook.

## 8. Data layout and concurrency

### `.data`

```text
0x00  u32 debug_level = 3
0x04  wait_queue_head_t dect_uicp_read_wait_queue_head (12 bytes)
0x10  struct list_head dect_uicp_to_api_list (8 bytes)
```

### `.bss`

```text
0x0000  u32 dect_uicp_open_flag
0x0004  u32 is_open
0x0008  spinlock_t dio_spin_lock
0x000c  u8 buf.25011[256]
0x010c  struct { dev_t dev; struct cdev *cdev; } dect_uicp_file (8 bytes)
0x0114  void *dbg_handle
0x0118  u8 dect_uicp_from_user_buffer[12352]
```

### Locking and queue model

- `dio_spin_lock` protects insertion into and removal from
  `dect_uicp_to_api_list`.
- `dect_uicp_fpapi_handle_to_user()` inserts at the tail under
  `spin_lock_irqsave`.
- `dect_uicp_file_read()` removes a fully consumed entry under the same lock.
- The read wait queue is woken with `__wake_up()` after insertion.
- The allocation path uses an atomic/zeroing allocation helper; this is
  consistent with callback context.
- `dect_uicp_from_dect()` checks the list head and calls `__wake_up()`
  outside `dio_spin_lock`; this is a small race window, though the queue
  insertion itself is locked.
- There is no mutex and no per-open queue: the single-open restriction is the
  only serialization between userspace readers/writers.

## 9. Dependencies to replace on Linux 6.12

These are facts from imports/metadata; they are not a complete port plan.

| Original dependency | Why it matters | Linux 6.12 replacement |
|---|---|---|
| `avm_dect_if_init/deinit/tx` | proprietary AVM transport | clean `dect_transport` ops / callback |
| `avm_DebugCallRegister/UnRegister` | AVM debug registry | optional tracepoint or debugfs |
| `kmem_cache_alloc(kmalloc_caches[6], ...)` | hardcoded cache index | `kzalloc(size, GFP_ATOMIC)` |
| `struct file` offsets `0x20`, `0x48`, `0x94` | direct layout assumptions | use `file->f_flags`, `file->f_pos`, `file->private_data` |
| `access_ok` / `arm_copy_to_user/from_user` | old uaccess API | `copy_to_user()` / `copy_from_user()` |
| `prepare_to_wait_event` / `finish_wait` | old wait-queue API | `wait_event_interruptible()` or current wait API |
| `spin_lock_irqsave` around list | atomic callback context | `spin_lock_irqsave` + `wake_up_interruptible` outside lock |
| hardcoded `250` HZ | specific FRITZ kernel config | report actual `HZ` or use `jiffies_to_msecs` |
| `fasync_helper` without `kill_fasync` | incomplete SIGIO | add proper `kill_fasync` if async is required |
| `cdev_alloc` / `cdev_add` / manual mknod | old char-device pattern | `alloc_chrdev_region` + `cdev_init`/`cdev_add`, or `miscdevice` |
| `debug_level` module param | AVM debug bits | standard `module_param`/debugfs |

The biggest semantic issue is not API churn: the original `avm_dect_if_tx()`
expects a 3-byte AVM subheader `[0x14][primitive_le16]`, while the callback
receives `[primitive_le16][payload]`. A clean implementation must define this
boundary explicitly and test both directions with a mock.

## 10. Unresolved questions

1. Exact symbolic names of ioctl commands 1/2 and tags `0x8052`/`0x8053`.
   Only numeric values are proven.
2. Whether any shipped binary other than `dect_manager` uses cmd 2. The local
   rootfs search found `/dev/dect_io` only in `dect_manager` and the
   `E41-capi` init script; `dect_manager` has only a cmd-1 call site.
3. Exact kmalloc size class and whether the observed `0x8000` flag is
   `__GFP_ZERO` in this kernel configuration. The helper name and behavior
   strongly suggest zeroing, but this is inferred.
4. Why `open` maps allocation failure and O_APPEND failure to `-EFAULT`
   instead of `-ENOMEM`/`-EINVAL`. This is reproduced from disassembly, not
   corrected.
5. Whether `read` can return `-ERESTARTSYS` directly to userspace or the
   syscall layer converts it to `EINTR`; userspace should treat it as an
   interrupted read.
6. Exact behavior of `avm_dect_if_tx()` for malformed 3-byte subheaders and
   primitive `0x2fba`; that belongs to Phase 2 / `avm_dect.ko`, not this module.
7. Whether `fasync` was intended to signal SIGIO; no `kill_fasync` symbol is
   imported, so the current implementation cannot deliver it.

## 11. Confidence

| Conclusion | Confidence | Basis |
|---|---|---|
| fops mapping and module init/exit | high | relocations + full disassembly |
| write framing and max size | high | `0x72c..0x97c` |
| read framing and queue entry layout | high | `0x268..0x58c`, `0xa80..0xbc4` |
| ioctl 1 `{jiffies, 250}` | high | `0x58c..0x72c`, manager call site |
| ioctl 2 prints 256-byte debug string | high | `0x58c..0x72c` |
| manager open/read/write path | high | `dect_manager` disassembly and xrefs |
| zeroing allocation / exact GFP symbol | medium | flag `0x8000` inferred as `__GFP_ZERO` |
| `private+8` purpose | medium | stored `&filp->f_pos`, unused in this module |
| race window in `from_dect` wakeup | medium | static control flow; no runtime race test |

## 12. Userspace mock checklist

A mock that reproduces this ABI needs only the following state:

```text
bool opened;
bool nonblock;
struct list_head queue;
wait_queue_head_t readq;
struct fasync_struct *fasync;
```

Implementation rules:

1. Allow only one `open`; reject `O_APPEND`; return the observed errors.
2. `write`:
   - reject `count <= 3` or `count > 0x3040` with `-EIO`;
   - reject `le16(buf[0]) + 4 != count` with `-EIO`;
   - pass `buf+4` and `le16(buf[0])` to the transport callback;
   - return `count`, even if the transport callback fails.
3. Transport callback:
   - reject `len <= 1`;
   - build an entry with the 5-byte prefix `{len+1, 0x8053, 0}` followed by
     the original message `{primitive, payload}`;
   - append to the queue and wake readers.
4. `read`:
   - if empty: `-EAGAIN` for nonblocking, otherwise wait; a signal yields
     `-ERESTARTSYS`;
   - copy from `entry+0x10+entry->copied`, at most `entry->total-copied`;
   - if fully consumed, remove/free and reset `*ppos` to zero;
   - otherwise advance `entry->copied` and `*ppos`;
   - return copied bytes or `-EFAULT` on user-copy failure.
5. `poll`: return `0x104` when empty, `0x145` when nonempty; register the
   read wait queue.
6. `ioctl 1`: return 0 and write `{jiffies, 250}` to the 8-byte user pointer;
   `ioctl 2`: accept 256 bytes and print them; invalid command: `-EFAULT`.
7. `fasync`: store the fasync pointer; do not claim SIGIO delivery, because
   the original never calls `kill_fasync`.

## Evidence files

```text
reports/dect_io.disasm.txt
reports/dect_io.annotated.txt
reports/dect_io-callgraph.txt
reports/dect_manager-dect_io-xrefs.txt
reports/dect_manager-dect_io-disasm.txt
reports/dect_manager-dect-core-disasm.txt
reports/dect_manager-init-disasm.txt
reports/dect_manager-io-xrefs.txt
reports/dect_manager-dect_io-callers.txt
```
