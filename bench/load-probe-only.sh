#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
#
# Probe-only Stage B loader + verifier.
#
# Loads the exact module with probe_only=1 and verifies the resulting state.
# Never writes driver sysfs attributes, never starts DMA, never touches
# GPIO/UART/firmware/line.  On verification failure it performs exactly one
# cleanup rmmod (never a retry/reload) and exits non-zero.
#
# POSIX/busybox ash compatible.

set -u

YES=0
MODULE=/tmp/fon_tdm_drv.ko
MANIFEST=
OUT=
KVER=6.12
EXPECT_MODEL="AVM FRITZ!Box 7530"
EXPECT_COMPAT="avm,fritzbox-7530"
EXPECT_STAGE=0x23
EXPECT_MASK=0x3f
MODNAME=fon_tdm_drv

usage() {
	printf '%s\n' \
		"usage: $0 --yes [--module FILE] [--manifest FILE] [--output DIR] \\" \
		"          [--kernel MAJOR.MINOR] [--model STR] [--compatible STR]"
}

die() {
	printf 'FAIL: %s\n' "$*" >&2
	exit 1
}

while [ $# -gt 0 ]; do
	case $1 in
		--yes) YES=1 ;;
		--module) shift; [ $# -gt 0 ] || { usage; exit 2; }; MODULE=$1 ;;
		--manifest) shift; [ $# -gt 0 ] || { usage; exit 2; }; MANIFEST=$1 ;;
		--output) shift; [ $# -gt 0 ] || { usage; exit 2; }; OUT=$1 ;;
		--kernel) shift; [ $# -gt 0 ] || { usage; exit 2; }; KVER=$1 ;;
		--model) shift; [ $# -gt 0 ] || { usage; exit 2; }; EXPECT_MODEL=$1 ;;
		--compatible) shift; [ $# -gt 0 ] || { usage; exit 2; }; EXPECT_COMPAT=$1 ;;
		-h|--help) usage; exit 0 ;;
		*) usage; exit 2 ;;
	esac
	shift
done

[ "$YES" -eq 1 ] || die "refused: pass --yes (see docs/fon-first-hardware-test.md)"
[ "$(id -u)" -eq 0 ] || die "must run as root"
[ -f "$MODULE" ] || die "module not found: $MODULE"
case $MODULE in /*) ;; *) die "module path must be absolute" ;; esac
[ ! -e "$OUT" ] || die "output dir already exists: $OUT"

for t in sha256sum insmod rmmod modinfo lsmod uname dmesg cat grep tr find date mkdir awk head cmp; do
	command -v "$t" >/dev/null 2>&1 || die "missing tool: $t"
done

if [ -z "$MANIFEST" ]; then
	MANIFEST=$(dirname "$0")/fon_tdm_drv.sha256
fi
[ -f "$MANIFEST" ] || die "manifest not found: $MANIFEST"
want=$(awk '/^[0-9a-f]+/ { print $1; exit }' "$MANIFEST")
[ -n "$want" ] || die "no lowercase SHA-256 in manifest"

meta=$(modinfo "$MODULE" 2>/dev/null) || die "modinfo failed"
printf '%s\n' "$meta" | grep -q "^name:[[:space:]]*$MODNAME$" || die "bad module name"
printf '%s\n' "$meta" | grep -q '^license:[[:space:]]*GPL$' || die "module is not GPL"
printf '%s\n' "$meta" | grep -q "^vermagic:[[:space:]]*$KVER\." || die "unexpected vermagic"
printf '%s\n' "$meta" | grep -q '^parm:[[:space:]]*probe_only[[:space:]]*[(][Bb][Oo][Oo][Ll][)]$' || die "no probe_only parameter"
printf '%s\n' "$meta" | grep -q '^depends:[[:space:]]*$' || die "module has dependencies"

got=$(sha256sum "$MODULE" | awk '{print $1}')
[ "$got" = "$want" ] || die "SHA-256 mismatch: got $got want $want"

uname_r=$(uname -r)
case $uname_r in "$KVER".*) ;; *) die "unexpected kernel $uname_r" ;; esac

model=$(tr -d '\0' </sys/firmware/devicetree/base/model 2>/dev/null)
[ "$model" = "$EXPECT_MODEL" ] || die "unexpected DT model '$model'"
compat=$(tr -d '\0' </sys/firmware/devicetree/base/compatible 2>/dev/null)
[ "$compat" = "$EXPECT_COMPAT" ] || die "unexpected DT compatible '$compat'"

node=/sys/firmware/devicetree/base/soc/fon-tdm@7700000
[ -d "$node" ] || die "FON DT node missing (use the probe-only test image)"
status=$(tr -d '\0' <"$node/status" 2>/dev/null)
[ "$status" = okay ] || die "FON node status '$status', expected okay"

lsmod 2>/dev/null | grep -q "^$MODNAME " && die "$MODNAME already loaded"

OUT=${OUT:-/tmp/fon-stage-b-$(date +%Y%m%d-%H%M%S)}
[ ! -e "$OUT" ] || die "output dir already exists: $OUT"
mkdir -p "$OUT" || die "cannot create $OUT"

{
	printf 'module=%s\nsha256=%s\nkernel=%s\nmodel=%s\ncompatible=%s\nnode_status=%s\n' \
		"$MODULE" "$got" "$uname_r" "$model" "$compat" "$status"
} >"$OUT/preflight.txt"
printf '%s\n' "$meta" >"$OUT/modinfo.txt"
printf '%s\n' "$got" >"$OUT/sha256.txt"

cat /proc/iomem >"$OUT/iomem-before.txt"
cat /proc/interrupts >"$OUT/interrupts-before.txt"
dmesg >"$OUT/dmesg-before.txt" 2>&1 || true
lsmod >"$OUT/lsmod-before.txt" 2>&1 || true

printf 'Pre-flight OK; loading %s with probe_only=1\n' "$MODULE"
insmod "$MODULE" probe_only=1 >"$OUT/insmod.log" 2>&1 || die "insmod failed (see $OUT/insmod.log)"

sleep 1
cat /proc/iomem >"$OUT/iomem-after.txt"
cat /proc/interrupts >"$OUT/interrupts-after.txt"
dmesg >"$OUT/dmesg-after.txt" 2>&1 || true
lsmod >"$OUT/lsmod-after.txt" 2>&1 || true

fail=0
dev=$(find /sys/bus/platform/devices -maxdepth 1 -name '*fon*' -print 2>/dev/null | head -1)
if [ -n "$dev" ] && [ -e "$dev/driver" ]; then
	printf '%s\n' "$dev" >"$OUT/device.txt"
	cat "$dev/stage" >"$OUT/stage.txt" 2>&1 || true
	cat "$dev/diagnostics" >"$OUT/diagnostics.txt" 2>&1 || true
else
	printf 'FAIL: not bound to a FON platform device\n'
	: >"$OUT/stage.txt"
	: >"$OUT/diagnostics.txt"
	fail=1
fi

if [ "$(cat "$OUT/stage.txt" 2>/dev/null)" != "$EXPECT_STAGE" ]; then
	printf 'FAIL: stage != %s\n' "$EXPECT_STAGE"
	fail=1
fi

for want_line in "mode=probe-only" "resource_mask=$EXPECT_MASK" \
		 "diag_valid=0" "dma_prepared=0" "dma_started=0" \
		 "irq_spi=156/159" "irq_intid=188/191" "irq=-1"; do
	if ! grep -qx "$want_line" "$OUT/diagnostics.txt" 2>/dev/null; then
		printf 'FAIL: missing %s\n' "$want_line"
		fail=1
	fi
done

if ! grep -q 'probe-only' "$OUT/dmesg-after.txt" 2>/dev/null; then
	printf 'FAIL: no probe-only dmesg\n'
	fail=1
fi

if ! cmp -s "$OUT/iomem-before.txt" "$OUT/iomem-after.txt"; then
	printf 'FAIL: /proc/iomem changed\n'
	# diff may be absent in slim initramfs images; keep a byte-identical
	# copy instead of failing the script on a missing diagnostic tool.
	cp -f "$OUT/iomem-after.txt" "$OUT/iomem-after.changed.txt" 2>/dev/null || true
	fail=1
fi

cat "$OUT/diagnostics.txt" 2>/dev/null || true
if [ "$fail" -ne 0 ]; then
	if lsmod 2>/dev/null | grep -q "^$MODNAME "; then
		rmmod "$MODNAME" >>"$OUT/cleanup.log" 2>&1 || true
	fi
	die "post-load verification failed; see $OUT"
fi
printf 'PASS: probe-only verified; results in %s\n' "$OUT"
