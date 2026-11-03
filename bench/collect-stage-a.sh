#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Read-only Stage A collector. Writes only under /tmp (or the supplied path).
set -u
OUT=${1:-/tmp/fon-stage-a-$(date +%Y%m%d-%H%M%S)}

mkdir -p "$OUT" || exit 1
printf 'Collecting read-only FON stage A into %s\n' "$OUT"

save() {
	name=$1
	shift
	"$@" >"$OUT/$name" 2>&1 || printf 'unavailable: %s\n' "$name" >>"$OUT/$name"
}

save uname.txt uname -a
save openwrt_release.txt cat /etc/openwrt_release
save cmdline.txt cat /proc/cmdline
save model.txt cat /sys/firmware/devicetree/base/model
save iomem.txt cat /proc/iomem
save interrupts.txt cat /proc/interrupts
save consoles.txt cat /proc/consoles
save dmesg.txt dmesg
save lsmod.txt lsmod
save tty.txt sh -c 'ls -l /dev/ttyMSM* /dev/ttyS* 2>/dev/null || true'
save dt_fon_status.txt sh -c 'tr -d "\\0" </sys/firmware/devicetree/base/soc/fon-tdm@7700000/status 2>/dev/null || true'

if command -v modinfo >/dev/null 2>&1; then
	save modinfo.txt modinfo fon_tdm_drv
fi
if [ -d /sys/firmware/devicetree/base ]; then
	tar -cf "$OUT/devicetree.tar" -C /sys/firmware/devicetree/base . 2>/dev/null || true
fi
if [ -r /sys/kernel/debug/clk/clk_summary ]; then
	cp /sys/kernel/debug/clk/clk_summary "$OUT/clk_summary.txt" 2>/dev/null || true
fi
if [ -d /sys/kernel/debug/pinctrl ]; then
	find /sys/kernel/debug/pinctrl -maxdepth 2 -type f -print >"$OUT/pinctrl-files.txt" 2>/dev/null || true
fi

tar -czf "$OUT.tar.gz" -C "$(dirname "$OUT")" "$(basename "$OUT")"
printf 'Stage A archive: %s.tar.gz\n' "$OUT"
printf 'No hardware state was changed.\n'
