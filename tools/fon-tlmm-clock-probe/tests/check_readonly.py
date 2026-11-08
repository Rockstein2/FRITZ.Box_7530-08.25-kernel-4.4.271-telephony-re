#!/usr/bin/env python3
"""Static guard: the probe sources must remain read-only.

This is a source check, not a substitute for review.  It rejects the obvious
ways an MMIO probe could accidentally acquire a write path, a GPIO request or
a pinctrl/clock/reset side effect.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
SOURCES = sorted(list(ROOT.glob("*.c")) + list(ROOT.glob("*.h")) +
                 list((ROOT / "kernel").glob("*.c")) +
                 list((ROOT / "kernel").glob("*.h")))

FORBIDDEN = {
    "PROT_WRITE": "writable mmap",
    "O_RDWR": "read-write /dev/mem open",
    "writel(": "kernel MMIO write helper",
    "iowrite": "kernel MMIO write helper",
    "pwrite(": "file write",
    "gpio_request": "GPIO request can interact with pinctrl",
    "gpiod_": "GPIO descriptor request/value path",
    "gpio_get_value": "GPIO subsystem read path",
    "pinctrl_": "pinctrl state change",
    "reset_control": "reset framework operation",
    "ioctl(": "unreviewed ioctl path",
    "/sys/class/gpio": "sysfs GPIO request path",
    "devmem_write": "explicit write mode",
}

# Identifier-prefix checks must not match bclk_plans or similar names.
FORBIDDEN_REGEX = {
    r"(?<![A-Za-z0-9_])clk_": "clock framework operation",
}

errors = 0
for path in SOURCES:
    text = path.read_text(errors="replace")
    for needle, why in FORBIDDEN.items():
        if needle in text:
            print(f"FAIL {path.relative_to(ROOT)}: forbidden {needle!r} ({why})")
            errors += 1
    for pattern, why in FORBIDDEN_REGEX.items():
        if re.search(pattern, text):
            print(f"FAIL {path.relative_to(ROOT)}: forbidden /{pattern}/ ({why})")
            errors += 1

main = (ROOT / "fon-tlmm-clock-probe.c").read_text(errors="replace")
checks = [
    ('userspace opens /dev/mem read-only',
     'open("/dev/mem", O_RDONLY' in main),
    ("userspace maps with PROT_READ", "PROT_READ" in main),
    ("userspace has no PROT_WRITE", "PROT_WRITE" not in main),
    ("userspace reads the IO register through reg_read",
     "reg_read(gpio_io_off" in main),
]
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        errors += 1

# The kernel skeleton, if present, must only read via readl().
kernel = ROOT / "kernel" / "fon_tlmm_probe.c"
if kernel.is_file():
    ktext = kernel.read_text(errors="replace")
    print(("PASS " if "readl(" in ktext else "FAIL ") +
          "kernel skeleton reads through readl()")
    if "readl(" not in ktext:
        errors += 1

print(f"\n{errors} failure(s)")
sys.exit(1 if errors else 0)
