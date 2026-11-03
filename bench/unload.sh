#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -u
YES=0
OUT=/tmp/fon-stage-b

while [ $# -gt 0 ]; do
	case "$1" in
		--yes) YES=1 ;;
		--output) shift; [ $# -gt 0 ] || exit 2; OUT=$1 ;;
		*) printf 'usage: %s --yes [--output DIR]\n' "$0"; exit 2 ;;
	esac
	shift
done

if [ "$YES" != 1 ]; then
	printf 'REFUSED: pass --yes after confirming the module is the only intended change\n'
	exit 2
fi
if [ "$(id -u)" != 0 ]; then
	printf 'REFUSED: run as root\n' >&2
	exit 1
fi
if ! lsmod 2>/dev/null | grep -q '^fon_tdm_drv '; then
	printf 'Module is not loaded; nothing to do.\n'
	exit 0
fi

mkdir -p "$OUT" || exit 1
rmmod fon_tdm_drv || exit 1
dmesg >"$OUT/dmesg-unload.txt" 2>&1 || true
find /sys/bus/platform/devices -maxdepth 1 -name '*fon*' -print >"$OUT/devices-after-unload.txt" 2>&1 || true
printf 'Unloaded fon_tdm_drv; captured %s\n' "$OUT"
