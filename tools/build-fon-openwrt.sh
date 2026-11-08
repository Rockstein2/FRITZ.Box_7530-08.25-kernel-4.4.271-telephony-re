#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
#
# Reproducible OpenWrt 25.12.6 SDK build for the diagnostic FON module.
# This does not install anything on a router.
#
# Usage:
#   SDK_DIR=/path/to/openwrt-sdk-25.12.6-ipq40xx \
#   sh tools/build-fon-openwrt.sh
#
# The SDK must provide the target ipq40xx/generic kernel tree and toolchain.

set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
FON_REPO="$ROOT"
. "$ROOT/tools/workspace.sh"
SDK_DIR=${SDK_DIR:-$OPENWRT_SDK}
: "${SDK_DIR:?set SDK_DIR to the extracted OpenWrt SDK root}"
PKG_SRC="$ROOT/openwrt/package/kernel/fon-tdm"
PKG_DST="$SDK_DIR/package/kernel/fon-tdm"

test -f "$SDK_DIR/include/kernel.mk"
test -f "$SDK_DIR/target/linux/ipq40xx/Makefile"
rm -rf "$PKG_DST"
mkdir -p "$SDK_DIR/package/kernel"
cp -a "$PKG_SRC" "$PKG_DST"
rm -f "$PKG_DST/src"
ln -s "$ROOT/src/fon-driver" "$PKG_DST/src"

cd "$SDK_DIR"
if [ ! -f .config ]; then
	make defconfig
fi
# The package source is an external symlink for this repository; always
# rebuild from a clean package build directory so stale objects cannot hide
# source changes.
make package/fon-tdm/clean
make package/fon-tdm/compile V=s

KO=$(find "$SDK_DIR/staging_dir" -path '*/lib/modules/*/fon_tdm_drv.ko' -print -quit)
APK=$(find "$SDK_DIR/bin/targets" -name 'kmod-fon-tdm-*.apk' -print -quit)
test -n "${KO:-}"
test -n "${APK:-}"
printf '\nmodule: %s\npackage: %s\n' "$KO" "$APK"
file "$KO"
strings "$KO" | grep -E '^(vermagic|depends|name|license)=' || true
printf '\nNo module was loaded and no hardware was touched by this script.\n'
