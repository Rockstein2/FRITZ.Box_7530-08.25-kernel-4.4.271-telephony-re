#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
#
# Verify the local OpenWrt7530 workspace layout and all canonical SHA256
# manifests. Read-only: this script never writes to reference/, evidence/,
# restore/, backups/, work/ or builds/.
#
# Usage: sh tools/verify-workspace.sh

set -u
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO=$(CDPATH= cd -- "$HERE/.." && pwd)
FON_REPO="$REPO"
. "$REPO/tools/workspace.sh"

FAILS=0
PASSES=0

pass() { PASSES=$((PASSES + 1)); printf 'PASS %s\n' "$*"; }
fail() { FAILS=$((FAILS + 1)); printf 'FAIL %s\n' "$*"; }

check_dir() {
	[ -d "$1" ] && pass "dir $1" || fail "missing dir $1"
}

check_file() {
	[ -f "$1" ] && pass "file ${1#"$FON_WORKSPACE"/}" || fail "missing file $1"
}

check_manifest() {
	dir=$1
	name=${dir#"$FON_WORKSPACE"/}
	if [ ! -f "$dir/SHA256SUMS" ]; then
		fail "manifest missing: $name/SHA256SUMS"
		return
	fi
	if ( cd "$dir" && sha256sum -c SHA256SUMS >/dev/null 2>&1 ); then
		pass "manifest $name"
	else
		fail "manifest mismatch: $name"
		( cd "$dir" && sha256sum -c SHA256SUMS 2>&1 ) |
			grep -v ': OK$' | head -10
	fi
}

# ---- canonical areas -------------------------------------------------------
for d in \
	"$FON_REFERENCE/oem-08.25/installers" \
	"$FON_REFERENCE/oem-08.25/source" \
	"$FON_REFERENCE/oem-08.25/extracted" \
	"$FON_REFERENCE/oem-08.25/extracted/rootfs" \
	"$FON_REFERENCE/oem-08.25/extracted/modules" \
	"$FON_REFERENCE/oem-08.25/extracted/firmware" \
	"$FON_REFERENCE/oem-08.25/extracted/init-scripts" \
	"$FON_REFERENCE/oem-08.25/dtb" \
	"$FON_EVIDENCE/stage-a" \
	"$FON_EVIDENCE/stage-b" \
	"$FON_EVIDENCE/stage-b-c1" \
	"$FON_EVIDENCE/stage-b-c1b" \
	"$FON_EVIDENCE/stage-c0" \
	"$FON_EVIDENCE/stage-c0-final" \
	"$FON_EVIDENCE/oem-08.25/boot-logs/2026-11-08" \
	"$FON_EVIDENCE/oem-08.25/console/2026-11-08" \
	"$FON_RESTORE/openwrt-25.12.6" \
	"$FON_BUILDS/probe-only" \
	"$FON_WORK/extracted/sysupgrade-avm_fritzbox-7530" \
	"$FON_WORK/oem-08.25/extraction/fon-d05"; do
	check_dir "$d"
done

for f in \
	"$FON_REFERENCE/oem-08.25/extracted/kernel.image" \
	"$FON_REFERENCE/oem-08.25/extracted/filesystem.image" \
	"$FON_REFERENCE/oem-08.25/dtb/HW236-subrev2.dtb" \
	"$FON_REFERENCE/oem-08.25/dtb/HW236-subrev0.dtb" \
	"$FON_BUILDS/probe-only/probe-only-initramfs-uImage.itb" \
	"$FON_RESTORE/openwrt-25.12.6/openwrt-25.12.6-ipq40xx-generic-avm_fritzbox-7530-initramfs-uImage.itb" \
	"$FON_RESTORE/openwrt-25.12.6/openwrt-25.12.6-ipq40xx-generic-avm_fritzbox-7530-squashfs-sysupgrade.bin"; do
	check_file "$f"
done

# ---- no legacy stage images in restore --------------------------------------
if [ -d "$FON_RESTORE" ]; then
	for entry in "$FON_RESTORE"/*; do
		[ -e "$entry" ] || continue
		base=${entry##*/}
		case "$base" in
		openwrt-25.12.6|README.md) ;;
		*) fail "restore contains non-recovery entry: $base" ;;
		esac
	done
	pass "restore contains only recovery entries"
fi

# ---- no old canonical duplicates -------------------------------------------
for d in \
	"$FON_REFERENCE/oem-08.25/image-extracted" \
	"$FON_REFERENCE/oem-08.25/rootfs" \
	"$FON_REFERENCE/oem-08.25/boot-logs" \
	"$FON_REFERENCE/oem-08.25/console" \
	"$FON_REFERENCE/oem-08.25/extraction"; do
	[ ! -e "$d" ] && pass "legacy removed: ${d#"$FON_WORKSPACE"/}" ||
		fail "legacy still present: ${d#"$FON_WORKSPACE"/}"
done

# ---- manifests -------------------------------------------------------------
for d in \
	"$FON_REFERENCE/oem-08.25/installers" \
	"$FON_REFERENCE/oem-08.25/source" \
	"$FON_REFERENCE/oem-08.25/extracted" \
	"$FON_REFERENCE/oem-08.25/extracted/rootfs" \
	"$FON_REFERENCE/oem-08.25/dtb" \
	"$FON_REFERENCE/sources" \
	"$FON_EVIDENCE/stage-a" \
	"$FON_EVIDENCE/stage-b" \
	"$FON_EVIDENCE/stage-b-c1" \
	"$FON_EVIDENCE/stage-b-c1b" \
	"$FON_EVIDENCE/stage-c0" \
	"$FON_EVIDENCE/stage-c0-final" \
	"$FON_EVIDENCE/oem-08.25/boot-logs/2026-11-08" \
	"$FON_EVIDENCE/oem-08.25/console/2026-11-08" \
	"$FON_BUILDS/probe-only" \
	"$FON_RESTORE/openwrt-25.12.6"; do
	check_manifest "$d"
done

printf '\n%d passed, %d failed\n' "$PASSES" "$FAILS"
[ "$FAILS" -eq 0 ]
