# FON test recovery and rollback plan

> **Status: operational document.**
> This is a runbook, not an evidence record.  Hardware facts are maintained in
> `../fon-known-facts.md`; unresolved items in `../fon-open-questions.md`.

Status: **prepared, not executed**

This plan is for a separate bench/test image only.  The production router
`RckBox` is not a test target unless the user explicitly authorizes it.

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

The exact FRITZ!Box 7530 OpenWrt rollback/flash route is **UNVERIFIED** in
this workspace.  It depends on the currently installed OpenWrt boot
layout/FIT image and the available recovery method.  Do not invent a
`sysupgrade`/EVA command.

Before Stage B, the operator must have a tested, documented procedure to
return to the known-good production image, including any required bootloader
or recovery-tool steps.  The procedure is outside this repository until it
has been verified on the bench.

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
