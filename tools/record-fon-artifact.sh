# SPDX-License-Identifier: GPL-2.0-only
#
# Copy the staged module from the OpenWrt SDK and record both hashes.
#
# Usage:
#   SDK_DIR=/path/to/openwrt-sdk sh tools/record-fon-artifact.sh
#
# It does not load, flash or modify anything on a router.

set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
: "${SDK_DIR:?set SDK_DIR to the extracted OpenWrt SDK}"

KO=$SDK_DIR/staging_dir/target-arm_cortex-a7+neon-vfpv4_musl_eabi/root-ipq40xx/lib/modules/6.12.112/fon_tdm_drv.ko
APK=$SDK_DIR/bin/targets/ipq40xx/generic/packages/kmod-fon-tdm-6.12.112-r1.apk

[ -f "$KO" ] || { echo "missing $KO" >&2; exit 1; }
[ -f "$APK" ] || { echo "missing $APK" >&2; exit 1; }

ko_sha=$(sha256sum "$KO" | awk '{print $1}')
apk_sha=$(sha256sum "$APK" | awk '{print $1}')

cp "$KO" "$ROOT/bench/fon_tdm_drv.ko"
{
	printf '# SHA-256 of the target fon_tdm_drv.ko used for this bench kit.\n'
	printf '# Copy that exact .ko to /tmp/fon_tdm_drv.ko before load-probe-only.sh.\n'
	printf '%s  fon_tdm_drv.ko\n' "$ko_sha"
} >"$ROOT/bench/fon_tdm_drv.sha256"

{
	printf 'module:   %s\n' "$KO"
	printf 'module_sha256: %s\n' "$ko_sha"
	printf 'package:  %s\n' "$APK"
	printf 'package_sha256: %s\n' "$apk_sha"
} >"$ROOT/bench/artifact.txt"

printf 'Recorded module %s\n' "$ko_sha"
printf 'Recorded package %s\n' "$apk_sha"
