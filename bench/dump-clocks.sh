#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Read-only. Never mounts debugfs.
if [ ! -r /sys/kernel/debug/clk/clk_summary ]; then
	printf 'clk_summary unavailable (debugfs not mounted or no permission)\n'
	exit 0
fi
cat /sys/kernel/debug/clk/clk_summary
