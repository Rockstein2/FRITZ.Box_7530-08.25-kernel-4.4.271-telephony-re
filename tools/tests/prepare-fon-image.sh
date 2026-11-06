# SPDX-License-Identifier: GPL-2.0-only
#
# Tests for tools/prepare-fon-image.sh DTB generation.  Runs on temporary
# OpenWrt-like trees and a read-only prepared kernel include tree; never
# builds firmware, flashes or touches a router.
#
# Usage:
#   KERNEL_INCLUDE=/path/to/prepared/kernel/include \
#   DTC=/path/to/dtc sh tools/tests/prepare-fon-image.sh

set -u
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO=$(CDPATH= cd -- "$HERE/../.." && pwd)
SRC=${OPENWRT_SRC:-/home/rck/Downloads/OpenWrt7530/openwrt-25.12.6-source}
PRISTINE=${PRISTINE_DTS:?set PRISTINE_DTS to an unpatched board DTS}
WORK=${TMPDIR:-/tmp/opencode}/fon-image-tests
: "${KERNEL_INCLUDE:?set KERNEL_INCLUDE to a prepared kernel include dir}"
: "${DTC:?set DTC}"
FAILS=0
PASSES=0

DTS=target/linux/ipq40xx/files-6.12/arch/arm/boot/dts/qcom/qcom-ipq4019-fritzbox-7530.dts

pass() { PASSES=$((PASSES + 1)); echo "PASS $*"; }
fail() { FAILS=$((FAILS + 1)); echo "FAIL $*"; }

# Each run gets a completely separate source tree and output dir.
run() {
	mode=$1
	d=$WORK/tree-$mode
	rm -rf "$d" "$WORK/out-$mode"
	mkdir -p "$d/target/linux/ipq40xx/files-6.12/arch/arm/boot/dts/qcom"
	mkdir -p "$d/package/kernel"
	: >"$d/rules.mk"
	: >"$d/Makefile"
	# The preparation script only checks that these exist; empty stubs keep
	# the test independent of the host OpenWrt tree.
	: >"$d/target/linux/ipq40xx/Makefile"
	cp "$PRISTINE" "$d/$DTS"
	OPENWRT_DIR="$d" OUT_DIR="$WORK/out-$mode" FON_PROBE_ONLY="$mode" \
	KERNEL_INCLUDE="$KERNEL_INCLUDE" DTC="$DTC" \
		sh "$REPO/tools/prepare-fon-image.sh" >"$WORK/log-$mode.txt" 2>&1
}

node_status() {
	sed -n '/fon-tdm@7700000/,/};/p' "$WORK/out-$1/fon-node.txt" |
		sed -n 's/.*status = "\([a-z]*\)";.*/\1/p' | head -1
}

mkdir -p "$WORK"
if run 0; then
	pass "normal: script exit 0"
	[ "$(node_status 0)" = disabled ] && pass "normal: status=disabled" || fail "normal: status wrong"
	[ -s "$WORK/out-0/qcom-ipq4019-fritzbox-7530-normal.dtb" ] && pass "normal: DTB exists" || fail "normal: no DTB"
	sha256sum "$WORK/out-0/qcom-ipq4019-fritzbox-7530-normal.dtb" >"$WORK/normal.sha256"
	grep -q '^[0-9a-f]\{64\} ' "$WORK/out-0/qcom-ipq4019-fritzbox-7530-normal.dtb.sha256" &&
		pass "normal: SHA-256 recorded" || fail "normal: no SHA-256 file"
else
	fail "normal: script failed"; cat "$WORK/log-0.txt"
fi

# probe DTB
if run 1; then
	pass "probe: script exit 0"
	[ "$(node_status 1)" = okay ] && pass "probe: status=okay" || fail "probe: status wrong"
	[ -s "$WORK/out-1/qcom-ipq4019-fritzbox-7530-probe.dtb" ] && pass "probe: DTB exists" || fail "probe: no DTB"
else
	fail "probe: script failed"; cat "$WORK/log-1.txt"
fi

# the only node difference is the status line
run 0 || fail "normal setup failed"
cp "$WORK/out-0/fon-node.txt" "$WORK/node-normal.txt"
run 1 || fail "probe setup failed"
cp "$WORK/out-1/fon-node.txt" "$WORK/node-probe.txt"
diff "$WORK/node-normal.txt" "$WORK/node-probe.txt" >"$WORK/node.diff" 2>&1
if [ "$(grep -c '^[<>]' "$WORK/node.diff")" -eq 2 ] &&
   grep -q '< .*status = "disabled";' "$WORK/node.diff" &&
   grep -q '> .*status = "okay";' "$WORK/node.diff"; then
	pass "normal/probe differ only by the status line"
else
	fail "normal/probe node diff unexpected"; cat "$WORK/node.diff"
fi

# invalid value
d=$WORK/tree-x
rm -rf "$d"; mkdir -p "$d/$(dirname "$DTS")"; : >"$d/Makefile"; cp "$PRISTINE" "$d/$DTS"
if OPENWRT_DIR="$d" OUT_DIR="$WORK/out-x" FON_PROBE_ONLY=2 \
	KERNEL_INCLUDE="$KERNEL_INCLUDE" DTC="$DTC" \
	sh "$REPO/tools/prepare-fon-image.sh" >/dev/null 2>&1; then
	fail "invalid FON_PROBE_ONLY accepted"
else
	pass "invalid FON_PROBE_ONLY refused"
fi

# missing DTC
d=$WORK/tree-y
rm -rf "$d"; mkdir -p "$d/$(dirname "$DTS")"; : >"$d/Makefile"; cp "$PRISTINE" "$d/$DTS"
if OPENWRT_DIR="$d" OUT_DIR="$WORK/out-y" FON_PROBE_ONLY=0 \
	KERNEL_INCLUDE="$KERNEL_INCLUDE" DTC=/nonexistent/dtc \
	sh "$REPO/tools/prepare-fon-image.sh" >/dev/null 2>&1; then
	fail "missing DTC accepted"
else
	pass "missing DTC refused"
fi

printf '\n%s passed, %s failed\n' "$PASSES" "$FAILS"
[ "$FAILS" -eq 0 ] || exit 1
