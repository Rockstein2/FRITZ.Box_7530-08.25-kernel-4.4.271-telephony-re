#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -u
YES=0
MODULE=/tmp/fon_tdm_drv.ko
OUT=/tmp/fon-stage-b

usage() {
	printf 'usage: %s --yes [--module FILE] [--output DIR]\n' "$0"
	exit 2
}

while [ $# -gt 0 ]; do
	case "$1" in
		--yes) YES=1 ;;
		--module) shift; [ $# -gt 0 ] || usage; MODULE=$1 ;;
		--output) shift; [ $# -gt 0 ] || usage; OUT=$1 ;;
		-h|--help) usage ;;
		*) usage ;;
	esac
	shift
done

if [ "$YES" != 1 ]; then
	printf 'REFUSED: pass --yes after reading docs/fon-first-hardware-test.md\n'
	exit 2
fi
if [ "$(id -u)" != 0 ]; then
	printf 'REFUSED: run as root\n' >&2
	exit 1
fi
if [ ! -f "$MODULE" ]; then
	printf 'REFUSED: module not found: %s\n' "$MODULE" >&2
	exit 1
fi
if lsmod 2>/dev/null | grep -q '^fon_tdm_drv '; then
	printf 'REFUSED: fon_tdm_drv is already loaded\n' >&2
	exit 1
fi

mkdir -p "$OUT" || exit 1
printf 'Loading %s with probe_only=1\n' "$MODULE"
dmesg >"$OUT/dmesg-before.txt" 2>&1 || true
insmod "$MODULE" probe_only=1 || exit 1
sleep 1
dmesg >"$OUT/dmesg-after.txt" 2>&1 || true
lsmod >"$OUT/lsmod-after.txt" 2>&1 || true
find /sys/bus/platform/devices -maxdepth 1 -name '*fon*' -print >"$OUT/devices.txt" 2>&1 || true

while IFS= read -r dev; do
	[ -n "$dev" ] || continue
	[ -d "$dev" ] || continue
	printf 'device: %s\n' "$dev" >>"$OUT/sysfs.txt"
	cat "$dev/stage" >>"$OUT/sysfs.txt" 2>&1 || true
	cat "$dev/diagnostics" >>"$OUT/sysfs.txt" 2>&1 || true
done <"$OUT/devices.txt"

printf 'Captured %s\n' "$OUT"
printf 'No sysfs attributes were written and no DMA was started.\n'
