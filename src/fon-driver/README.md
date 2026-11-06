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
```

The first hardware test uses `probe_only=1`.

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
