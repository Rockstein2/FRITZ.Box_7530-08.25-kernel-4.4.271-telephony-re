# FON-C0+-K kernel build report

> **Status: offline build only.**
> The module was compiled and then removed from the working tree.  It was
> **not** copied to a router, loaded or triggered.

Baseline source commit: `3127558`
(`fix(fon): validate OEM TDM timing and harden software clock probe`).
The R2 source changes are the working-tree change set described in
`fon-c0plus-kernel-safety-review.md`.

---

## 1. Kernel tree identity

| Item | Value |
|---|---|
| OpenWrt source tree | `openwrt-25.12.6-source` |
| Kernel build tree | `build_dir/target-arm_cortex-a7+neon-vfpv4_musl_eabi/linux-ipq40xx_generic/linux-6.12.112` |
| Kernel version | `6.12.112` |
| Architecture | ARMv7, SMP, musl EABI |
| Toolchain | `OpenWrt GCC 14.3.0 r33311-981c978eff` |
| `CONFIG_MODULES` | `y` |
| `CONFIG_MODULE_UNLOAD` | `y` |
| `CONFIG_DEBUG_FS` | `y` |
| `CONFIG_DEBUG_FS_ALLOW_ALL` | `y` |
| `CONFIG_MODVERSIONS` | **not set** |
| `CONFIG_MODULE_SIG` | **not set** |
| `Module.symvers` | present, 532 776 bytes at build time |
| Expected `uname -r` | `6.12.112` (vermagic must match exactly) |

`CONFIG_MODVERSIONS` being off means there is no per-symbol CRC check.
Matching vermagic is necessary but **not sufficient** proof of ABI
compatibility; K1 must still compare the exact kernel release, module
`vermagic`, and the tree used for the build.

## 2. Build command

```sh
export STAGING_DIR=/path/to/openwrt-25.12.6-source/staging_dir
make -C /path/to/linux-6.12.112 \
     M=$PWD/tools/fon-tlmm-clock-probe/kernel \
     ARCH=arm \
     CROSS_COMPILE=/path/to/toolchain/bin/arm-openwrt-linux-muslgnueabi- \
     modules
```

The module is built as `obj-m += fon_tlmm_probe.o`; no additional module
dependency is declared.

## 3. Artifact

| Item | Value |
|---|---|
| File | `fon_tlmm_probe.ko` |
| Size | 53 248 bytes |
| SHA256 | `31173cc9eacf34c8487442cc1fd89270d3b48067fead164301b917ed79312a60` |
| Architecture | ARMv7 |
| Vermagic | `6.12.112 SMP mod_unload ARMv7 p2v8` |
| `depends:` | empty |
| Parameters | `gpio:int`, `duration_ms:uint`, `expected_hz:int` |

The SHA256 is a build record, not a committed binary.  Rebuild and compare
the exact hash before any hardware use.

### 3.1 Undefined kernel symbols at link time

The module has no module-to-module dependencies.  Its unresolved symbols are
normal kernel/compiler-runtime imports, including:

```text
ioremap, iounmap, readl/__do_div64, __aeabi_uidivmod,
debugfs_create_file, debugfs_remove, simple_open, simple_read_from_buffer,
ktime_get, mutex_lock, mutex_trylock, mutex_unlock, cond_resched,
scnprintf, param_ops_int, param_ops_uint
```

This list is not proof that every symbol is exported by the exact target
image; K1 must check `modprobe`/`insmod` error output and `dmesg`.

## 4. What the artifact proves

- The source compiles against the selected 6.12.112 tree.
- The expected vermagic is generated.
- The module links without an unresolved module dependency.
- The kernel-side timing logic and its host tests compile in the same source
  tree.

It does **not** prove:

- that the router is running this exact kernel;
- that `insmod` succeeds on the router;
- that debugfs is mounted or writable;
- that the TLMM mapping coexists safely with the running pinctrl owner;
- that the measurement is electrically meaningful.

Those are K1/K2 hardware checks, not build results.

## 5. Readiness

| Stage | Status |
|---|---|
| Offline build | **PASS** |
| Offline kernel logic tests | **PASS** |
| K1 module load/unload safety | **NOT RUN** |
| K2 one-shot measurement | **NOT RUN** |

K1 is the next possible hardware step, and only with separate approval.  K2
requires K1 to pass first.
