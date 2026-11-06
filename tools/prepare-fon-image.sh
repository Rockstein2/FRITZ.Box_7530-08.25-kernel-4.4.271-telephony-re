# SPDX-License-Identifier: GPL-2.0-only
#
# Reproducible OpenWrt 25.12.6 image preparation (not a full build).
#
# It configures a source tree for the FRITZ!Box 7530, applies the FON DTS
# patches in the requested mode, and produces the exact board DTB that a full
# image build would install.  It never flashes, never runs sysupgrade, never
# touches a router.
#
# Usage:
#   OPENWRT_DIR=/path/to/openwrt-25.12.6-source \
#   OUT_DIR=/tmp/opencode/fon-dtb \
#   FON_PROBE_ONLY=1 \
#   sh tools/prepare-fon-image.sh
#
# FON_PROBE_ONLY=0 -> production-safe disabled node
# FON_PROBE_ONLY=1 -> probe-only test image (okay node)

set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
: "${OPENWRT_DIR:?set OPENWRT_DIR to an OpenWrt 25.12.6 source tree}"
OUT_DIR=${OUT_DIR:-/tmp/opencode/fon-dtb}
FON_PROBE_ONLY=${FON_PROBE_ONLY:-0}

case $FON_PROBE_ONLY in
	0|1) ;;
	*) echo "REFUSED: FON_PROBE_ONLY must be 0 or 1" >&2; exit 2 ;;
esac

DTS_REL=target/linux/ipq40xx/files-6.12/arch/arm/boot/dts/qcom/qcom-ipq4019-fritzbox-7530.dts
DTS=$OPENWRT_DIR/$DTS_REL

test -f "$OPENWRT_DIR/Makefile"
test -f "$DTS" || { echo "REFUSED: board DTS not found: $DTS" >&2; exit 2; }

mkdir -p "$OUT_DIR"

OPENWRT_DIR="$OPENWRT_DIR" FON_PROBE_ONLY="$FON_PROBE_ONLY" \
	sh "$ROOT/tools/prepare-fon-openwrt-tree.sh" >"$OUT_DIR/prepare.log" 2>&1
tail -n 4 "$OUT_DIR/prepare.log"

# Locate the kernel include tree used by the target: either a prepared kernel
# build or the source tree's generated headers.
INCLUDES=${KERNEL_INCLUDE:-}
if [ -z "$INCLUDES" ]; then
	for cand in "$OPENWRT_DIR"/build_dir/target-*/linux-ipq40xx_generic/linux-6.12.*/include; do
		[ -d "$cand" ] && INCLUDES=$cand && break
	done
fi
[ -n "${INCLUDES:-}" ] || {
	echo "REFUSED: no prepared kernel include dir; run 'make target/linux/prepare' first" >&2
	exit 2
}

DTC=${DTC:-}
if [ -z "$DTC" ]; then
	for cand in "$OPENWRT_DIR"/build_dir/target-*/linux-ipq40xx_generic/linux-6.12.*/scripts/dtc/dtc; do
		[ -x "$cand" ] && DTC=$cand && break
	done
fi
if [ -z "$DTC" ]; then
	if command -v dtc >/dev/null 2>&1; then
		DTC=$(command -v dtc)
	elif [ -x "$OPENWRT_DIR/staging_dir/host/bin/dtc" ]; then
		DTC=$OPENWRT_DIR/staging_dir/host/bin/dtc
	else
		echo "REFUSED: no dtc (install device-tree-compiler or prepare the host tools)" >&2
		exit 2
	fi
fi

KERNEL_DTSDIR=$INCLUDES/../arch/arm/boot/dts/qcom
DTSDIR=$(dirname "$DTS")
PRE="$OUT_DIR/qcom-ipq4019-fritzbox-7530.pre.dts"
DTB="$OUT_DIR/qcom-ipq4019-fritzbox-7530-$( [ "$FON_PROBE_ONLY" = 1 ] && echo probe || echo normal ).dtb"

cpp -x assembler-with-cpp -D__DTS__ -nostdinc \
	-I"$INCLUDES" -I"$DTSDIR" -I"$KERNEL_DTSDIR" "$DTS" -o "$PRE"
"$DTC" -I dts -O dtb -o "$DTB" "$PRE" 2>"$OUT_DIR/dtc.log" || {
	echo "REFUSED: dtc failed; see $OUT_DIR/dtc.log" >&2
	exit 2
}

sha256sum "$DTB" >"$DTB.sha256"
"$DTC" -I dtb -O dts "$DTB" 2>/dev/null |
	sed -n '/fon-tdm@7700000/,/};/p' >"$OUT_DIR/fon-node.txt"

printf '\nDTB: %s\n' "$DTB"
cat "$DTB.sha256"
printf 'FON node:\n'
cat "$OUT_DIR/fon-node.txt"
printf '\nNo image was flashed and no router was touched.\n'
