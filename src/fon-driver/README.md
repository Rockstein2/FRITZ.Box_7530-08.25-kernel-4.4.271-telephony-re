# `fon_tdm_drv` — minimal diagnostic FON transport

This directory is a standalone Linux kernel module, not the AVM telephony
stack.  It is intentionally limited to the QCA ADSS/TDM/MBOX transport.

```text
fon_tdm.h/.c   pure 16-bit frame and FON control/status helpers
fon_hw.h/.c    platform driver, DT resources, safe diagnostics, DMA ring prep
tests/         host-side tests for the pure helpers
```

## Modes

```text
probe_only=1  (default)  report DT resources only; no MMIO/clock/reset/DMA
probe_only=0            map resources and obtain optional clock/reset/pinctrl
                        handles, but still no read/write/clock enable/DMA
C1/C2 (opt-in)          run_c1 / run_c2 bounded MMIO test, then restore
C3 dry-run              dma_prepare fills TX buffers with AVM-shaped frames
                        (zero control word, zero audio); no DMA, no IRQ, no MMIO
C3 passive RX           NOT IMPLEMENTED — needs hardware-validated clocks
C4 active TDM           NOT IMPLEMENTED — dma_start returns -EOPNOTSUPP
```

There is no automatic transition between stages, and no mode that arms a
line, a ring or a firmware upload.

The first hardware test uses `probe_only=1`.

## C3 control-only frame layout

`dma_prepare` builds frames that match the AVM `tdm@0` geometry
(`docs/history/fon-adss-tdm-channel-map.md`):

```text
byte 0x00  0x0000      header
byte 0x02  0xfefe      header (sync rail)
byte 0x04  0xfefe      header (sync rail)
byte 0x06  0xfefe      header (sync rail)
byte 0x08  0x5555      AVM writes 0x5555 when TDMPriv+0x808 == 0 (no FPGA).
                       The 7530 runs abmode=1 (no FPGA), so 0x5555 is the
                       board-correct value; tdm_hdr08_zero=1 selects the
                       FPGA branch 0x0000
byte 0x0a  16-bit control word (physical slot 5) — 0x0000 after prepare
byte 0x0c  audio slots, zeroed
```

**This frame is not "all silence".**  Bytes 0x02–0x08 carry AVM framing rails
whose SC14448 meaning is not decoded; only 0x0c onward is audio.

`slots = 8`, 16 bytes per frame.  `FON_DMA_FRAMES_PER_BUFFER = 32` is a
**configuration constant of this offline driver**, matching the GPL comment
`4 ms == 32`.  It is not the value OEM `pcmlink.ko` passes: that is
`[r5] / [r5+8]` from the board config, whose numbers are not recovered.  So
`fs_per_dma` for HW236 is **UNRESOLVED (Q76)** and the 512-byte half is only
correct if 32 turns out to be right.

The control word stays 0x0000 after prepare.  That is **default buffer
contents, not a proven line-idle command**: AVM's `build_slic_ctrl(0, 0, 0)`
returns `0x4000`, so the zero word is not the AVM idle encoding, and its
meaning to the SC14448 is unknown.  `dma_start` therefore stays blocked.

## State machine

```text
UNINITIALIZED
    -> RESOURCES_READY      probe mapped all DT resources
    -> DMA_PREPARED         explicit dma_prepare sysfs action
```

The diagnostic driver has no user-accessible `DMA_RUNNING` or `TDM_ACTIVE`
state.  Repeated prepare is idempotent; repeated release is a no-op; removal
sets a `removing` flag under the same mutex and releases rings before the
device is unbound.

## Safety defaults

- No clock or reset is enabled during probe.
- No MMIO is read or written during probe.
- `diag_refresh` is the only MMIO read path and requires
  `allow_mmio_reads=1`; the caller must first prove the ADSS clock/reset state.
- No DMA is started automatically.
- `dma_prepare` only allocates and fills descriptor/buffer memory.
- `dma_start` requires `allow_dma=1` and `allow_hw_writes=1`, and currently
  returns `-EOPNOTSUPP` because the SC14448/MBOX start semantics are not
  hardware-validated.
- No line/ring voltage is controlled.

## Build

Against a prepared kernel tree:

```sh
make -C /path/to/linux-6.12 \
     M=$PWD/src/fon-driver \
     CONFIG_FON_TDM=m modules
```

No in-tree AVM module is used.

## Offline tests

```sh
cd src/fon-driver/tests
make run
```

## DT node

The driver binds only to:

```text
compatible = "avm,fon-tdm";
```

See `../../docs/history/fon-linux612-port.md` for named MMIO resources and the example node.
The node must not overlap an enabled `qca,ipq4019-tdm`/`qca,ipq4019-pcm`
driver.

## Sysfs

With the node instantiated, the platform device exposes:

```text
stage          bitmask of reached diagnostic stages
diagnostics    cached state and last explicitly refreshed register snapshot
diag_refresh   1 = perform read-only MMIO refresh (requires allow_mmio_reads=1)
dma_prepare    1 = allocate/fill rings; 0 = release
dma_release    1 = release rings
dma_start      1 = explicit start request; gated and currently unsupported
```

The first safe test is read-only and does not write `dma_prepare` or
`dma_start`.  See the final report and `../../docs/history/fon-linux612-port.md`.
