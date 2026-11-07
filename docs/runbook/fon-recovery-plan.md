# FON test recovery and rollback plan

> **Status: operational document.**
> This is a runbook, not an evidence record.  Hardware facts are maintained in
> `../fon-known-facts.md`; unresolved items in `../fon-open-questions.md`.

Status: **prepared, not executed on hardware**

This workspace contains one FRITZ!Box 7530 (`RckBox`).  A RAM-only test may
use it only after production service has been moved to another router, with
explicit per-step authorization and with NAND left untouched.

## 1. Which image is running

Before loading the module, record:

```sh
uname -a
cat /etc/openwrt_release
cat /proc/cmdline
cat /sys/firmware/devicetree/base/model
```

There are two possible test arrangements:

### A. Module-only test on the production image

The production DTS keeps the FON node `status = "disabled"`.  The module can
be loaded with `probe_only=1`, but it will not bind to a platform device.
This only tests module load/unload and ABI compatibility.

### B. Probe-only test image

A separate image applies the optional `901` DTS patch so the FON node is
`status = "okay"`.  This permits the probe-only platform-device test.

Do not install image B on the production device without a separate decision,
a verified recovery route, and a known-good image.

### Returning to production

Verified on `RckBox` on 2026-11-07 over the serial console, read-only:

- installed firmware: official OpenWrt 25.12.6 `r33311-981c978eff`;
- installed kernel content is **byte-identical** to the official 25.12.6
  `avm_fritzbox-7530` kernel;
- installed rootfs is the same release but **not byte-identical** (132 bytes
  more squashfs data; same build time and inode count);
- flash layout is AVM UBI: kernel in `ubi0_0`, squashfs rootfs in `ubi0_1`
  (`ubiblock0_1`), overlay in `ubi0_4`, AVM volumes in `ubi0_2`/`ubi0_3`;
- `urlader0`/`urlader1` partitions are present, so the AVM EVA recovery
  partitions exist (their runtime behaviour is still unverified);
- `/sbin/sysupgrade` is available;
- configuration backups live outside the repository in `../../backups/`.

Return paths, in order of preference:

1. **RAM-only test (planned):** NAND is never written.  Rollback is "remove
   power" and boot the normal image.  This is the only path that needs no
   flash restore.
2. **If NAND is ever modified:** flash the verified official sysupgrade image
   from `../../restore/` (SHA-256 `011e020205fed455c79ee68ebb4d9ce43e6b05698bd99b05ebfc5c851f7ceb73`)
   and restore the latest configuration tarball from `../../backups/`.  This
   restores the same release and settings, not a byte-identical rootfs.
3. **If the bootloader is damaged:** use the AVM EVA recovery route.  It is
   **not verified on this unit** and must not be attempted without a separate
   decision.

Do not run `sysupgrade`, `mtd`, `ubi` or `ubirmvol` during the RAM test.

Byte-exact recovery of the current rootfs would require reading `/dev/ubi0_1`
(5 374 478 bytes) before any change.  That dump was deliberately not taken,
because the planned procedure does not write NAND.

Before Stage B the operator must still move production service to another
router, disconnect the analog line, and have physical power-cycle access.

### C. RAM-only boot (recommended first contact)

A third arrangement boots a test initramfs over TFTP and never writes NAND.
See `fon-recovery-ram-boot.md`.  Its rollback is "remove power", which
makes it the only arrangement usable before a flash rollback has been
verified on the bench.

## 2. Serial console / recovery observations

Confirmed statically:

- The target console UART is `serial@78af000`, 0x200 bytes, GIC SPI 107.
- The DTS pinctrl uses GPIO16/17.
- The DECT/console path shares this UART on the AVM design.
- The FON driver does not open, stop or write this UART.

**UNVERIFIED:**

- physical serial header/pads and voltage levels on the 7530 board;
- console baud rate and flow control;
- whether the installed bootloader exposes an EVA/recovery console;
- the exact recovery web/FTP/bootloader procedure for this OpenWrt image;
- whether a runtime DTB overlay is supported by the installed bootloader.

Do not connect a serial adapter until the physical pinout and voltage are
verified.  Do not stop the console or open the DECT UART for writing.

## 3. Mandatory stop conditions

Stop immediately and roll back if any occurs:

- kernel `WARNING`, `BUG`, `Oops`, panic, lockdep or refcount complaint;
- driver-core probe/bind/unbind complaint;
- boot hang or console loss;
- unexpected reboot or watchdog;
- MMIO region conflict or unexpected `/proc/iomem` change;
- clock/reset/pinctrl error;
- Ethernet or Wi-Fi instability;
- unexpected GPIO/line state change;
- `rmmod` failure, module refcount leak, or sysfs attributes surviving
  unbind;
- inability to reload the module or return to a shell.

Do not attempt to repair the situation by writing arbitrary registers,
toggling GPIO40, uploading firmware or changing the bootloader.

## 4. Recovery sequence

1. Disconnect the analog line.
2. Stop all driver operations.
3. Preserve:
   - serial console output;
   - `dmesg`;
   - `/proc/iomem`;
   - `/proc/interrupts`;
   - the Stage A/B tarballs.
4. Power-cycle only if the console is unresponsive and the documented
   recovery method permits it.
5. Reboot the known-good image using the verified procedure.
6. If the test image is unbootable, use the verified bootloader/initramfs
   recovery route.
7. Do not flash or restore anything until the known-good image and recovery
   medium are confirmed.

## 5. Pre-Stage-B confirmation checklist

- [ ] Production image and configuration backed up.
- [ ] Exact tested `.ko` SHA-256 matches `bench/fon_tdm_drv.sha256`.
- [ ] Test image identity and DTS state recorded (`disabled` or `okay`).
- [ ] Serial/recovery console physically verified, or another independent
      recovery path confirmed.
- [ ] Known-good rollback procedure verified on the bench.
- [ ] Test image is isolated from the production network segment.
- [ ] No automatic module load is configured.
- [ ] Analog line disconnected.
- [ ] Operator knows to run only `probe_only=1` and no sysfs writes.
- [ ] Stage A baseline archived.

If any box is unchecked, do not start Stage B.
