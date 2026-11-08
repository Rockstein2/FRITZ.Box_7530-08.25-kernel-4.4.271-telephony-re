#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
#
# Tests for tools/prepare-fon-openwrt-tree.sh against temporary OpenWrt-like
# trees.  No real OpenWrt tree is modified and nothing is built or flashed.
#
# Usage: sh tools/tests/prepare-fon-tree.sh

set -u
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO=$(CDPATH= cd -- "$HERE/../.." && pwd)
FON_REPO="$REPO"
. "$REPO/tools/workspace.sh"
SRC=${OPENWRT_SRC:-$FON_WORKSPACE/openwrt-25.12.6-source}
PRISTINE=${PRISTINE_DTS:-$REPO/tools/tests/data/qcom-ipq4019-fritzbox-7530-pristine.dts}
WORK=${TMPDIR:-/tmp/opencode}/fon-prepare-tests
FAILS=0
PASSES=0

DTS=target/linux/ipq40xx/files-6.12/arch/arm/boot/dts/qcom/qcom-ipq4019-fritzbox-7530.dts

pass() { PASSES=$((PASSES + 1)); echo "PASS $*"; }
fail() { FAILS=$((FAILS + 1)); echo "FAIL $*"; }

check() {
	if eval "$1"; then pass "$2"; else fail "$2"; fi
}

fresh() {
	rm -rf "$WORK"
	mkdir -p "$WORK/target/linux/ipq40xx/files-6.12/arch/arm/boot/dts/qcom"
	mkdir -p "$WORK/package/kernel"
	: >"$WORK/rules.mk"
	cp "$SRC/target/linux/ipq40xx/Makefile" "$WORK/target/linux/ipq40xx/Makefile"
	cp "$PRISTINE" "$WORK/$DTS"
	cp "$PRISTINE" "$WORK/original.dts"
}

run_prepare() {
	OPENWRT_DIR="$WORK" FON_PROBE_ONLY="$1" sh "$REPO/tools/prepare-fon-openwrt-tree.sh" \
		>"$WORK/prepare.log" 2>&1
}

# Print just disabled/okay so the assertion does not depend on indentation.
status() {
	sed -n '/fon_tdm: fon-tdm@7700000/,/^[[:space:]]*};/p' "$WORK/$DTS" |
		sed -n 's/.*status = "\([a-z]*\)";.*/\1/p' | head -1
}

# 0: disabled
fresh
if run_prepare 0; then
	check '[ "$(status)" = disabled ]' "FON_PROBE_ONLY=0 leaves node disabled"
else
	fail "FON_PROBE_ONLY=0 returned non-zero"
	cat "$WORK/prepare.log"
fi
check '[ -L "$WORK/package/kernel/fon-tdm/src" ]' "src symlink exists"
check '[ -f "$WORK/package/kernel/fon-tdm/src/fon_hw.c" ]' "src symlink resolves"

# 1: okay
fresh
if run_prepare 1; then
	check '[ "$(status)" = okay ]' "FON_PROBE_ONLY=1 enables node"
else
	fail "FON_PROBE_ONLY=1 returned non-zero"; cat "$WORK/prepare.log"
fi

# only the FON node changes in the DTS
fresh
run_prepare 1
check '[ "$(status)" = okay ]' "okay marker present"
check '[ "$(grep -c "fon_tdm: fon-tdm@7700000" "$WORK/$DTS")" -eq 1 ]' "exactly one FON node"
# no other DTS changed
check '[ -z "$(find "$WORK/target/linux/ipq40xx/files-6.12" -name "*.dts" ! -name "$(basename "$DTS")")" ]' "no extra DTS created"

# idempotent 0
fresh
run_prepare 0
cp "$WORK/$DTS" "$WORK/after0.dts"
if run_prepare 0; then
	check 'cmp -s "$WORK/after0.dts" "$WORK/$DTS"' "second FON_PROBE_ONLY=0 does not reverse/modify"
else
	fail "second FON_PROBE_ONLY=0 failed"
fi

# idempotent 1
fresh
run_prepare 1
cp "$WORK/$DTS" "$WORK/after1.dts"
if run_prepare 1; then
	check 'cmp -s "$WORK/after1.dts" "$WORK/$DTS"' "second FON_PROBE_ONLY=1 is unchanged"
else
	fail "second FON_PROBE_ONLY=1 failed"
fi

# invalid value
fresh
if run_prepare 2; then
	fail "invalid FON_PROBE_ONLY was accepted"
else
	check 'grep -q "must be 0 or 1" "$WORK/prepare.log"' "invalid FON_PROBE_ONLY refused clearly"
fi

# already-okay tree + FON_PROBE_ONLY=0 must not reverse
fresh
run_prepare 1
if run_prepare 0; then
	check '[ "$(status)" = okay ]' "does not auto-reverse 901"
	check 'grep -q "not reversing" "$WORK/prepare.log"' "warns instead of reversing"
else
	fail "FON_PROBE_ONLY=0 on probe tree failed instead of warning"
fi

# missing tree
if OPENWRT_DIR=/nonexistent FON_PROBE_ONLY=0 sh "$REPO/tools/prepare-fon-openwrt-tree.sh" >/dev/null 2>&1; then
	fail "missing tree accepted"
else
	pass "missing tree refused"
fi

printf '\n%s passed, %s failed\n' "$PASSES" "$FAILS"
[ "$FAILS" -eq 0 ] || exit 1
