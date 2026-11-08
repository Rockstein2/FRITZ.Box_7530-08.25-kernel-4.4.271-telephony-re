#!/usr/bin/env python3
"""Offline guard for the slot-5 reference library."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
TEXT = "\n".join(p.read_text(errors="replace") for p in
                 sorted(list(ROOT.glob("*.c")) + list(ROOT.glob("*.h"))))
FORBIDDEN = ("readl(", "writel(", "ioremap", "mmap(", "open(",
             "ioctl(", "gpio_", "pinctrl_", "clk_", "reset_control",
             "request_irq", "dma_")
errors = 0
for needle in FORBIDDEN:
    if needle in TEXT:
        print(f"FAIL forbidden hardware API: {needle}")
        errors += 1
print(f"{errors} failure(s)")
sys.exit(1 if errors else 0)
