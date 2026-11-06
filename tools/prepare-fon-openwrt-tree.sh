#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
#
# Prepare an OpenWrt source tree for the FON module.  This does not build or
# flash anything and does not touch a router.
#
# Usage:
#   OPENWRT_DIR=/path/to/openwrt \
#   FON_PROBE_ONLY=0 sh tools/prepare-fon-openwrt-tree.sh
#
# FON_PROBE_ONLY=1 applies the separate test-only DTS patch that changes the
# FON node from disabled to okay.  The default is 0 (production-safe disabled
# node).
#
# Re-running is idempotent for an already-prepared tree; patches are only
# applied when they are not already present.  It NEVER reverse-applies a
# patch.  An unreadable/unexpected tree is refused.

set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
: "${OPENWRT_DIR:?set OPENWRT_DIR to an OpenWrt source tree}"
FON_PROBE_ONLY=${FON_PROBE_ONLY:-0}

case $FON_PROBE_ONLY in
	0|1) ;;
	*) printf 'REFUSED: FON_PROBE_ONLY must be 0 or 1 (got %s)\n' "$FON_PROBE_ONLY" >&2; exit 2 ;;
esac

DTS=target/linux/ipq40xx/files-6.12/arch/arm/boot/dts/qcom/qcom-ipq4019-fritzbox-7530.dts
P900="$ROOT/openwrt/target/linux/ipq40xx/patches-6.12/900-arm-dts-ipq4019-fritzbox-7530-fon.patch"
P901="$ROOT/openwrt/test-patches/901-arm-dts-ipq4019-fritzbox-7530-probe-only.patch"

test -f "$OPENWRT_DIR/rules.mk" || { echo "REFUSED: not an OpenWrt tree" >&2; exit 2; }
test -d "$OPENWRT_DIR/package/kernel" || { echo "REFUSED: no package/kernel" >&2; exit 2; }
test -f "$OPENWRT_DIR/target/linux/ipq40xx/Makefile" || {
	echo "REFUSED: no ipq40xx target" >&2; exit 2; }
test -f "$OPENWRT_DIR/$DTS" || { echo "REFUSED: board DTS missing" >&2; exit 2; }

cd "$OPENWRT_DIR"

mkdir -p package/kernel/fon-tdm
# Copy only the package Makefile; the src symlink is created below.
cp -a "$ROOT/openwrt/package/kernel/fon-tdm/Makefile" package/kernel/fon-tdm/
rm -rf package/kernel/fon-tdm/src
ln -s "$ROOT/src/fon-driver" package/kernel/fon-tdm/src
[ -f package/kernel/fon-tdm/src/fon_hw.c ] || {
	echo "REFUSED: package src symlink is broken" >&2; exit 2; }

has_fon_node() {
	grep -q 'fon_tdm: fon-tdm@7700000' "$DTS"
}

has_p900() {
	has_fon_node
}

has_p901() {
	# awk is used to avoid grep-A portability issues in busybox.
	awk '/fon_tdm: fon-tdm@7700000/ { in_node = 1; next }
	     in_node && /^[[:space:]]*};[[:space:]]*$/ { exit }
	     in_node && /status = "okay";/ { found = 1 }
	     END { exit(found ? 0 : 1) }' "$DTS"
}

# 900: add the disabled node.  If present but the tree is not a pristine
# state (node already okay and FON_PROBE_ONLY=0), refuse rather than
# silently reverse.
if has_p900; then
	printf 'Patch 900 already applied; not re-applying.\n'
else
	patch -p1 -N <"$P900" || { echo "REFUSED: 900 failed to apply" >&2; exit 2; }
	has_p900 || { echo "REFUSED: 900 did not produce the FON node" >&2; exit 2; }
	printf 'Applied 900 (FON node disabled).\n'
fi

if [ "$FON_PROBE_ONLY" = "1" ]; then
	if has_p901; then
		printf 'Patch 901 already applied; not re-applying.\n'
	else
		patch -p1 <"$P901" || { echo "REFUSED: 901 failed to apply" >&2; exit 2; }
		has_p901 || { echo "REFUSED: 901 did not enable the FON node" >&2; exit 2; }
		printf 'Applied 901 (FON node okay, test image only).\n'
	fi
	printf 'Prepared probe-only test tree; FON node status=okay.\n'
else
	if has_p901; then
		printf 'WARNING: tree already has the probe-only 901 state; not reversing it.\n'
		printf 'Use a pristine tree for a production-safe image.\n'
	else
		printf 'Prepared production-safe tree; FON node status=disabled.\n'
	fi
fi

printf 'Package installed in %s/package/kernel/fon-tdm.\n' "$OPENWRT_DIR"
printf 'No build, flash, module load or hardware action was performed.\n'
