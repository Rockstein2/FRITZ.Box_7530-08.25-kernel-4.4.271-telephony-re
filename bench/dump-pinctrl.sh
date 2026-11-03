#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Read-only. Never mounts debugfs or writes pinmux.
if [ ! -d /sys/kernel/debug/pinctrl ]; then
	printf 'pinctrl debugfs unavailable\n'
	exit 0
fi
for f in $(find /sys/kernel/debug/pinctrl -maxdepth 2 -type f -name 'pinmux-pins' 2>/dev/null); do
	printf '=== %s\n' "$f"
	grep -E 'gpio(16|17|20|21|22|23|24|25|26|27|40)|pin (16|17|20|21|22|23|24|25|26|27|40)' "$f" 2>/dev/null || true
done
