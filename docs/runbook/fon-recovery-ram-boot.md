# FON bench recovery: RAM-only boot via TFTP

> **Status: operational document.**
> This is a runbook, not an evidence record.  Hardware facts are maintained in
> `../fon-known-facts.md`; unresolved items in `../fon-open-questions.md`.

Status: **procedure written, never executed on hardware**

This document covers the RAM-only test path: boot a self-built initramfs over
TFTP, run the FON probe-only test, power-cycle, NAND untouched.  It is the
recommended first hardware contact because the rollback path is "remove
power" rather than "write flash".

Nothing here has been run on a real 7530 in this workspace.  Every step is
marked with its evidence level:

- **DOC** — documented by upstream OpenWrt or AVM material;
- **STATIC** — confirmed from source/DTS/binaries in this repository;
- **UNVERIFIED** — plausible but not confirmed for this unit.

The production router `RckBox` is not a test target.

---

## 1. Why RAM-only

The AVM installation route loads a small U-Boot into RAM through the AVM
EVA FTP server (`adam2`), and that U-Boot then fetches a file named
`FRITZ7530.bin` from a TFTP server and boots it. **DOC**

Consequences that matter here:

- the image is loaded into RAM, not written to NAND;
- if the image is bad, the board simply fails to reach a shell and is
  power-cycled;
- the installed flash image is not touched unless an explicit
  `sysupgrade`, `mtd write` or `ubirmvol` command is run. **UNVERIFIED for
  this unit — confirm the bootloader behaviour on the bench first.**

Do **not** run `sysupgrade`, `mtd`, `ubirmvol` or `ubi` commands during the
RAM test.  They are listed nowhere in this procedure on purpose.

---

## 2. Assets

| Asset | Source | Purpose |
|---|---|---|
| `FRITZ7530.bin` | our own initramfs build (or the stock one as a first sanity boot) | booted into RAM |
| `uboot-fritz7530.bin` | `downloads.openwrt.org/releases/25.12.6/targets/ipq40xx/generic/u-boot-fritz7530/` | small U-Boot loaded via EVA |
| `eva_ramboot.py` | `scripts/flashing/eva_ramboot.py` in the OpenWrt tree | sends U-Boot to EVA over FTP |
| TFTP server | host tool, run by the operator | serves `FRITZ7530.bin` |

`eva_ramboot.py` uses FTP login `adam2`/`adam2` against the AVM EVA server
and asks it to load the image to the given offset with
`kernel_args_tmp mtdram1=...`. **STATIC**

Record SHA-256 of every asset before the test.

---

## 3. Network addresses

| Role | Address |
|---|---|
| Bench PC on AVM EVA | `192.168.178.1` is the box; PC uses an address in the same subnet |
| Bench PC on OpenWrt U-Boot | `192.168.1.70/24`, box is `192.168.1.1` |
| TFTP file name | exactly `FRITZ7530.bin` in the TFTP root |

**DOC** for both address pairs.  The box changing subnet between EVA and
U-Boot is normal and is the reason two static PC configurations are needed.

---

## 4. Procedure

### 4.1 Before touching the bench unit

- [ ] Bench unit is **not** the production router.
- [ ] Analog line disconnected.
- [ ] The unit is disconnected from any production network.
- [ ] Assets hashed and recorded.
- [ ] Stock initramfs available and ready to boot first (section 4.2).
- [ ] The site can be power-cycled physically without damage.

### 4.2 First boot: stock initramfs (sanity, no FON code)

Boot the **stock** image (official or our self-built stock-equivalent)
through the same path.  If the stock image reaches a shell, the whole
transport chain is proven independent of our code.

Fallback if EVA FTP is unavailable: try the TFTP route directly (U-Boot
already installed) or the AVM recovery program. **UNVERIFIED which applies
to this unit.**

### 4.3 Second boot: our probe-only initramfs

Same path, `FRITZ7530.bin` replaced by the FON build.

1. Power off.
2. Start the TFTP server with the file in place.
3. Power on.
4. Watch for the file being fetched; **DOC** the box retries every ~5 s and
   the transfer can take a couple of minutes.
5. Reach a shell.
6. Mount the USB stick, copy evidence, run `bench/load-probe-only.sh --yes`
   and then `bench/unload.sh --yes` (see `../../bench/README.md`).
7. Power off.  Do not reboot into anything else and do not write NAND.

### 4.4 After the test

- [ ] Evidence copied off the stick.
- [ ] Board powered off, not left running.
- [ ] Installed flash image unchanged (compare before/after if the unit was
      later booted normally).
- [ ] No `sysupgrade`/`mtd`/`ubi` command was run.

---

## 5. Stop conditions

Stop and power off immediately if any of these occur:

- kernel panic, `BUG`, `Oops`, lockdep or refcount complaint;
- probe/bind error storm;
- boot hang, no console, or the board reboots unexpectedly;
- MMIO conflict or unexpected `/proc/iomem` change;
- the FON driver reports `diag_valid != 0`, DMA started, or any IRQ
  requested in probe-only mode;
- Ethernet/Wi-Fi instability;
- `rmmod` failure or sysfs attributes surviving unbind.

Do not attempt to "fix" a stop condition by writing registers, toggling
GPIO40, uploading SC14448 firmware, or touching the bootloader.

---

## 6. What this procedure does NOT prove

- that the installed bootloader is the upstream `uboot-fritz7530.bin`;
- that the EVA FTP server is reachable on this unit;
- that `FRITZ7530.bin` is the file name this bootloader expects (the 7520
  variant uses `FRITZ7520.bin`); **DOC**
- that the unit's flash chip is one of the supported variants;
- that the FON hardware behaves as assumed (GPIO40 polarity, SC14448 state,
  TDM clocks, slot 5).

Each of these is a separate gate.  Passing the RAM boot does not authorize
flashing anything.

---

## 7. References

- `scripts/flashing/eva_ramboot.py` in the OpenWrt tree (STATIC).
- `target/linux/ipq40xx/image/generic.mk`, `Device/avm_fritzbox-7530`
  (STATIC).
- `package/boot/uboot-fritz4040/Makefile`, `U-Boot/fritz7530` (STATIC).
- OpenWrt downloads tree for 25.12.6, `u-boot-fritz7530/` (DOC).
- Upstream installation guides for 7530/7520 (DOC, external).
