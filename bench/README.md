# FON probe-only bench kit

This kit is for the **probe-only** first test only.  It never starts DMA,
resets GPIO40, opens the DECT UART, uploads firmware, writes driver sysfs
attributes, or touches the analog line.

## Files

```text
collect-stage-a.sh    read-only system/DT snapshot -> tarball
load-probe-only.sh    strict pre-flight + load + verify (probe_only=1)
unload.sh             rmmod + verify cleanup
dump-clocks.sh        read clk_summary if debugfs is already mounted
dump-pinctrl.sh       read pinmux state for GPIO16/17/20-27/40
tests/                host-side fake-root tests (no hardware)
expected-stage-a.txt  Stage A template/annotations
expected-stage-b.txt  expected probe-only dmesg/sysfs
expected-clocks.txt   expected passive TDM clocks, to be measured
fon_tdm_drv.sha256    SHA-256 of the exact tested artifact
```

`bench/fon_tdm_drv.ko` itself is **not** committed; it is placed locally by
`tools/record-fon-artifact.sh` and excluded via `.git/info/exclude`.

## Before copying to the router

```sh
sha256sum /path/to/fon_tdm_drv.ko
cat bench/fon_tdm_drv.sha256
```

They must match.  `load-probe-only.sh` refuses on mismatch.

## Operator sequence

```sh
# on the workstation
scp bench/*.sh bench/fon_tdm_drv.sha256 /tmp/fon_tdm_drv.ko \
    root@<test-router>:/tmp/

# on the test router (isolated bench, serial console available)
cd /tmp
sh collect-stage-a.sh /tmp/fon-stage-a
sh load-probe-only.sh --yes --module /tmp/fon_tdm_drv.ko
sh unload.sh --yes
```

The loader enforces, before any `insmod`:

- `--yes`;
- root;
- absolute module path;
- SHA-256 from the manifest;
- `name=fon_tdm_drv`, `license=GPL`, `vermagic=6.12.x`,
  `parm=probe_only:bool`, empty `depends`;
- kernel `6.12.x`;
- DT `model = "AVM FRITZ!Box 7530"`;  (exact string, including the `!`)
- DT `compatible = "avm,fritzbox-7530"`;
- FON node exists and `status = "okay"`;
- module not already loaded;
- output directory does not already exist.

After `insmod` it verifies `stage=0x23`, `mode=probe-only`,
`resource_mask=0x3f`, `diag_valid=0`, `dma_prepared=0`, `dma_started=0`,
`irq_spi=156/159`, `irq_intid=188/191`, `irq=-1`, and that `/proc/iomem` did
not change.  On failure it performs one cleanup `rmmod` and exits non-zero.

`unload.sh` verifies the module disappears, no driver binding remains, and
the driver sysfs attributes are gone.  The platform device itself may remain.

## IRQ terminology

```text
raw DT GIC SPI      156 / 159
GIC INTID           188 / 191
Linux virq          not requested in probe-only; diagnostics prints irq=-1
```

Never substitute 188 for an unknown runtime virq.

## What a passing result does NOT prove

- no hardware access happened: reading debugfs clocks/pinctrl can itself
  touch registers;
- an unchanged `/proc/iomem` means only "no new visible claim", not "no
  mapping/conflict anywhere";
- the module bound: a successful `insmod` is not a successful probe;
- the FON hardware, clocks, TDM or SC14448 work.

## Stop immediately if

- `WARNING`, `BUG`, `Oops`, lockdep or refcount message appears;
- `/proc/iomem` changes after probe-only;
- Ethernet/Wi-Fi becomes unstable;
- the console disappears;
- `rmmod` fails or sysfs survives unbind;
- the device cannot be reloaded.

Follow `../docs/runbook/fon-recovery-plan.md`; do not improvise at the bench.

## Host-side script tests

No hardware is touched; `/sys` and `/proc` are redirected to a fake tree and
`insmod`/`rmmod`/`modinfo`/... are stubs:

```sh
sh bench/tests/run.sh
```

Covers no `--yes`, wrong SHA, wrong board/kernel/module, missing/disabled FON
node, already loaded, insmod failure, bind failure, wrong diagnostics,
changed `/proc/iomem`, output-directory reuse, unload failure, leftover sysfs,
and cleanup after failed verification.  Every pre-load refusal also proves
that the `insmod` stub was not called.
