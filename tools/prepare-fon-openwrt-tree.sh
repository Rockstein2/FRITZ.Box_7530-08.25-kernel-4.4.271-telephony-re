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

set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
: "${OPENWRT_DIR:?set OPENWRT_DIR to an OpenWrt source tree}"
FON_PROBE_ONLY=${FON_PROBE_ONLY:-0}

test -f "$OPENWRT_DIR/rules.mk"
test -d "$OPENWRT_DIR/package/kernel"
test -f "$OPENWRT_DIR/target/linux/ipq40xx/Makefile"

mkdir -p "$OPENWRT_DIR/package/kernel/fon-tdm"
cp -a "$ROOT/openwrt/package/kernel/fon-tdm/." \
	"$OPENWRT_DIR/package/kernel/fon-tdm/"
rm -f "$OPENWRT_DIR/package/kernel/fon-tdm/src"
ln -s "$ROOT/src/fon-driver" \
	"$OPENWRT_DIR/package/kernel/fon-tdm/src"

cd "$OPENWRT_DIR"
patch -p1 < "$ROOT/openwrt/target/linux/ipq40xx/patches-6.12/900-arm-dts-ipq4019-fritzbox-7530-fon.patch"

if [ "$FON_PROBE_ONLY" = "1" ]; then
	patch -p1 < "$ROOT/openwrt/test-patches/901-arm-dts-ipq4019-fritzbox-7530-probe-only.patch"
	printf 'Prepared probe-only test tree; FON node status=okay.\n'
else
	printf 'Prepared production-safe tree; FON node status=disabled.\n'
fi

printf 'Package installed in %s/package/kernel/fon-tdm.\n' "$OPENWRT_DIR"
printf 'No build, flash, module load or hardware action was performed.\n'
