#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
#
# Unload the probe-only FON module and verify the driver/sysfs components are
# gone.  The platform device itself may remain; that is not an error.
#
# Never writes sysfs, never resets anything, never retries automatically.

set -u

YES=0
OUT=

usage() {
	printf '%s\n' "usage: $0 --yes [--output DIR]"
}

die() {
	printf 'FAIL: %s\n' "$*" >&2
	exit 1
}

while [ $# -gt 0 ]; do
	case $1 in
		--yes) YES=1 ;;
		--output) shift; [ $# -gt 0 ] || { usage; exit 2; }; OUT=$1 ;;
		-h|--help) usage; exit 0 ;;
		*) usage; exit 2 ;;
	esac
	shift
done

[ "$YES" -eq 1 ] || die "refused: pass --yes"
[ "$(id -u)" -eq 0 ] || die "must run as root"

for t in rmmod lsmod dmesg find cat; do
	command -v "$t" >/dev/null 2>&1 || die "missing tool: $t"
done

if ! lsmod 2>/dev/null | grep -q '^fon_tdm_drv '; then
	printf 'Module is not loaded; nothing to do.\n'
	exit 0
fi

OUT=${OUT:-/tmp/fon-stage-b-unload-$(date +%Y%m%d-%H%M%S)}
[ ! -e "$OUT" ] || die "output dir already exists: $OUT"
mkdir -p "$OUT" || die "cannot create $OUT"

dev_before=$(find /sys/bus/platform/devices -maxdepth 1 -name '*fon*' -print 2>/dev/null | head -1)
printf '%s\n' "${dev_before:-none}" >"$OUT/device-before.txt"

rmmod fon_tdm_drv >"$OUT/rmmod.log" 2>&1 || die "rmmod failed (see $OUT/rmmod.log)"
dmesg >"$OUT/dmesg-unload.txt" 2>&1 || true
lsmod >"$OUT/lsmod-after.txt" 2>&1 || true

fail=0
if lsmod 2>/dev/null | grep -q '^fon_tdm_drv '; then
	printf 'FAIL: module still listed by lsmod\n'; fail=1
fi

dev_after=$(find /sys/bus/platform/devices -maxdepth 1 -name '*fon*' -print 2>/dev/null | head -1)
if [ -n "$dev_after" ]; then
	printf '%s\n' "$dev_after" >"$OUT/device-after.txt"
	if [ -e "$dev_after/driver" ]; then
		printf 'FAIL: driver binding still present: %s/driver\n' "$dev_after"; fail=1
	fi
	for attr in stage diagnostics diag_refresh dma_prepare dma_release dma_start; do
		if [ -e "$dev_after/$attr" ]; then
			printf 'FAIL: sysfs attribute still present: %s\n' "$dev_after/$attr"; fail=1
		fi
	done
else
	printf 'none\n' >"$OUT/device-after.txt"
fi

grep -qE 'WARNING:|BUG:|Oops|lockdep|refcount' "$OUT/dmesg-unload.txt" 2>/dev/null && {
	printf 'FAIL: kernel warning/oops recorded during unload\n'; fail=1; }

[ "$fail" -eq 0 ] || die "post-unload verification failed"
printf 'PASS: module unloaded and cleanup verified; results in %s\n' "$OUT"
