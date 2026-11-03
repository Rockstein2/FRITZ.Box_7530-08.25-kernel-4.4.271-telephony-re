# FON probe-only bench kit

This kit is for the **probe-only** first test only.  It does not start DMA,
reset GPIO40, open the DECT UART, upload firmware, or touch the analog line.

## Files

```text
collect-stage-a.sh    read-only system/DT snapshot -> tarball
load-probe-only.sh    load exact .ko with probe_only=1
unload.sh             rmmod and capture dmesg
dump-clocks.sh        read clk_summary if debugfs already mounted
dump-pinctrl.sh       read pinmux-pins for relevant GPIOs
expected-stage-a.txt  Stage A template/annotations
expected-stage-b.txt  expected probe-only dmesg/sysfs subset
expected-clocks.txt   expected passive TDM clocks, to be measured
fon_tdm_drv.sha256    exact tested artifact hash
```

## Before copying to the router

```sh
sha256sum /path/to/fon_tdm_drv.ko
cat bench/fon_tdm_drv.sha256
```

They must match.  The `.ko` itself is not in Git.

## Operator sequence

```sh
# on the workstation
scp bench/*.sh /tmp/fon_tdm_drv.ko root@<test-router>:/tmp/

# on the test router (serial console available)
cd /tmp
sh collect-stage-a.sh /tmp/fon-stage-a
sh load-probe-only.sh --yes --module /tmp/fon_tdm_drv.ko
sh unload.sh --yes
```

Do not run `load-probe-only.sh` without `--yes`; it refuses.  Do not run
`probe_only=0`, `diag_refresh`, `dma_prepare`, `dma_start`, GPIO40 reset,
firmware upload, or any line/ring command.

`irq=188` is expected from the driver because raw DT `GIC_SPI 156` becomes
Linux virq 156+32.  Always read the actual value from dmesg and
`/proc/interrupts`; do not hard-code it in a safety decision.

## Stop immediately if

- `WARNING`, `BUG`, `Oops`, lockdep or refcount message appears;
- `/proc/iomem` changes after probe-only;
- Ethernet/Wi-Fi becomes unstable;
- the console disappears;
- `rmmod` fails or sysfs does not disappear;
- the device cannot be reloaded.

Follow `docs/fon-recovery-plan.md`; do not improvise at the bench.
