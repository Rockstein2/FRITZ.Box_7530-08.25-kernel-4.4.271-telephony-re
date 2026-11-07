# OpenWrt DTS test patches

These files are not part of the default OpenWrt patch queue.  They document
the two DTS states used by this project.

## Order

Apply from the **OpenWrt source root**:

```sh
patch -p1 < /path/to/900-arm-dts-ipq4019-fritzbox-7530-fon.patch
patch -p1 < /path/to/901-arm-dts-ipq4019-fritzbox-7530-probe-only.patch
```

`901` is a diff against the result of `900`; it must not be applied alone.
`tools/prepare-fon-openwrt-tree.sh` applies the same order and supports
`FON_PROBE_ONLY=0|1`.

## What each patch changes

```text
900  adds a board-specific avm,fon-tdm node to
     qcom-ipq4019-fritzbox-7530.dts and leaves status = "disabled".
     The node also carries the C1 preparation links
     clocks = <&gcc GCC_AUDIO_AHB_CLK> and
     resets = <&gcc GCC_AUDIO_BCR>.  They are DT descriptions only: a
     probe-only load must not acquire them, and only an explicitly
     authorised C1 stage may.

901  changes only that FON node's status to "okay".
     It is for a separate probe-only test image.
```

Neither patch changes another IPQ4019 board.

## Safety

`901` must **never** be included in a production image.  The production-safe
state is `900` only, with the FON node disabled.  `901` does not enable MMIO,
DMA, clocks, reset, GPIO40, firmware or line/ring; the module's `probe_only=1`
default is separately required.

The node's DT resources and IRQ values are only a static description.  Runtime
ownership must be checked with `/proc/iomem` and `/proc/interrupts` before any
full-mode test.
