#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
#
# Tests for bench/load-probe-only.sh and bench/unload.sh using only stubs.
# No real insmod/rmmod/sysfs/GPIO/UART/DMA/flash operation is possible:
# /sys and /proc are rewritten to a temporary fake tree, and all module
# commands are shell stubs.
#
# Usage: sh bench/tests/run.sh
# Exit status: 0 only if every scenario passes.

set -u
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO=$(CDPATH= cd -- "$HERE/../.." && pwd)
WORK=${TMPDIR:-/tmp/opencode}/fon-bench-tests
FAILS=0
PASSES=0

command -v sha256sum >/dev/null 2>&1 || { echo "sha256sum missing"; exit 1; }

fresh() {
	rm -rf "$WORK"
	mkdir -p "$WORK"
	FAKE_ROOT="$WORK/fake"
	export FAKE_ROOT
	. "$HERE/fake-root.sh"
	fake_reset
	fake_env
	fake_module
	sed -e "s#/sys/#$FAKE_ROOT/sys/#g" \
	    -e "s#/proc/#$FAKE_ROOT/proc/#g" \
	    "$REPO/bench/load-probe-only.sh" >"$WORK/load.sh"
	sed -e "s#/sys/#$FAKE_ROOT/sys/#g" \
	    -e "s#/proc/#$FAKE_ROOT/proc/#g" \
	    "$REPO/bench/unload.sh" >"$WORK/unload.sh"
	chmod +x "$WORK/load.sh" "$WORK/unload.sh"
	printf '%s  fon_tdm_drv.ko\n' "$(cat "$FAKE_ROOT/state/sha")" >"$WORK/manifest"
}

# expect <name> <exit> <needle|-> <script> [args...]
expect() {
	name=$1
	want_rc=$2
	needle=$3
	shift 3
	out=$(sh "$@" 2>&1)
	rc=$?
	ok=1
	[ "$rc" -eq "$want_rc" ] || ok=0
	if [ "$needle" != "-" ]; then
		printf '%s\n' "$out" | grep -q "$needle" || ok=0
	fi
	if [ "$ok" -eq 1 ]; then
		PASSES=$((PASSES + 1))
		printf 'PASS %s\n' "$name"
	else
		FAILS=$((FAILS + 1))
		printf 'FAIL %s (rc=%s want=%s)\n' "$name" "$rc" "$want_rc"
		printf '%s\n' "$out" | sed 's/^/    /'
	fi
}

insmod_calls() {
	grep -c '^insmod ' "$FAKE_ROOT/state/calls" 2>/dev/null || true
}

no_insmod() {
	if [ "$(insmod_calls)" -eq 0 ]; then
		PASSES=$((PASSES + 1))
		printf 'PASS pre-flight blocked insmod\n'
	else
		FAILS=$((FAILS + 1))
		printf 'FAIL insmod was called before a refused load\n'
	fi
}

L="$WORK/load.sh"

# 1
fresh
expect "refuses without --yes" 1 "refused" "$L" --module "$FAKE_ROOT/state/module" --output "$WORK/o1"
no_insmod

# 2
fresh
printf '%s  fon_tdm_drv.ko\n' "0000000000000000000000000000000000000000000000000000000000000000" >"$WORK/manifest"
expect "wrong SHA-256" 1 "SHA-256 mismatch" "$L" --yes --module "$FAKE_ROOT/state/module" --manifest "$WORK/manifest" --output "$WORK/o2"
no_insmod

# 3
fresh
printf '%s\0' "Some Other Board" >"$FAKE_ROOT/sys/firmware/devicetree/base/model"
expect "wrong board model" 1 "unexpected DT model" "$L" --yes --module "$FAKE_ROOT/state/module" --manifest "$WORK/manifest" --output "$WORK/o3"
no_insmod

# 3a: the near-miss spelling used to be accepted by mistake.  "FRITZ.Box" is
# not the DT string; the board DTB says "FRITZ!Box".  This must be refused.
fresh
printf '%s\0' "AVM FRITZ.Box 7530" >"$FAKE_ROOT/sys/firmware/devicetree/base/model"
expect "model with dot instead of bang is refused" 1 "unexpected DT model" "$L" --yes --module "$FAKE_ROOT/state/module" --manifest "$WORK/manifest" --output "$WORK/o3a"
no_insmod

# 3b: the real DT string from the built board DTB must be accepted, i.e. it
# must NOT be rejected by the model check.  The run then fails later on the
# missing FON node, which proves the model gate itself passed.
fresh
printf '%s\0' "AVM FRITZ!Box 7530" >"$FAKE_ROOT/sys/firmware/devicetree/base/model"
out3b=$(sh "$L" --yes --module "$FAKE_ROOT/state/module" --manifest "$WORK/manifest" --output "$WORK/o3b" 2>&1)
if printf '%s\n' "$out3b" | grep -q "unexpected DT model"; then
	FAILS=$((FAILS + 1))
	printf 'FAIL model with bang rejected by the model gate\n'
else
	PASSES=$((PASSES + 1))
	printf 'PASS model with bang (real DTB) passes the model gate\n'
fi

# 4
fresh
printf '%s\0' "other,board" >"$FAKE_ROOT/sys/firmware/devicetree/base/compatible"
expect "wrong compatible" 1 "unexpected DT compatible" "$L" --yes --module "$FAKE_ROOT/state/module" --manifest "$WORK/manifest" --output "$WORK/o4"
no_insmod

# 5
fresh
printf '6.6.1\n' >"$FAKE_ROOT/sys/kernel_release"
expect "wrong kernel" 1 "unexpected kernel" "$L" --yes --module "$FAKE_ROOT/state/module" --manifest "$WORK/manifest" --output "$WORK/o5"
no_insmod

# 6
fresh
sed -i '/probe_only/d' "$FAKE_ROOT/state/modinfo"
expect "module lacks probe_only" 1 "no probe_only" "$L" --yes --module "$FAKE_ROOT/state/module" --manifest "$WORK/manifest" --output "$WORK/o6"
no_insmod

# 7
fresh
rm -rf "$FAKE_ROOT/sys/firmware/devicetree/base/soc/fon-tdm@7700000"
expect "FON node missing" 1 "FON DT node missing" "$L" --yes --module "$FAKE_ROOT/state/module" --manifest "$WORK/manifest" --output "$WORK/o7"
no_insmod

# 8
fresh
printf '%s\0' "disabled" >"$FAKE_ROOT/sys/firmware/devicetree/base/soc/fon-tdm@7700000/status"
expect "FON node disabled" 1 "expected okay" "$L" --yes --module "$FAKE_ROOT/state/module" --manifest "$WORK/manifest" --output "$WORK/o8"
no_insmod

# 9
fresh
printf 'fon_tdm_drv 72768 0\n' >"$FAKE_ROOT/state/loaded"
expect "already loaded" 1 "already loaded" "$L" --yes --module "$FAKE_ROOT/state/module" --manifest "$WORK/manifest" --output "$WORK/o9"
no_insmod

# 10
fresh
FAKE_INSMOD_FAIL=1 expect "insmod failure" 1 "insmod failed" "$L" --yes --module "$FAKE_ROOT/state/module" --manifest "$WORK/manifest" --output "$WORK/o10"

# 11
fresh
FAKE_BIND_FAIL=1 expect "no bind" 1 "not bound to a FON platform device" "$L" --yes --module "$FAKE_ROOT/state/module" --manifest "$WORK/manifest" --output "$WORK/o11"

# 12
fresh
FAKE_STAGE=0x03 expect "wrong stage" 1 "stage != 0x23" "$L" --yes --module "$FAKE_ROOT/state/module" --manifest "$WORK/manifest" --output "$WORK/o12"

# 13
fresh
FAKE_IOMEM_CHANGE=1 expect "iomem changed" 1 "/proc/iomem changed" "$L" --yes --module "$FAKE_ROOT/state/module" --manifest "$WORK/manifest" --output "$WORK/o13"

# 14
fresh
expect "probe-only success" 0 "PASS: probe-only verified" "$L" --yes --module "$FAKE_ROOT/state/module" --manifest "$WORK/manifest" --output "$WORK/o14"

# 15
expect "existing output refused" 1 "already exists" "$L" --yes --module "$FAKE_ROOT/state/module" --manifest "$WORK/manifest" --output "$WORK/o14"

# 16
fresh
if sh "$L" --yes --module "$FAKE_ROOT/state/module" --manifest "$WORK/manifest" --output "$WORK/o16" >/dev/null 2>&1; then
	expect "unload success" 0 "PASS: module unloaded" "$WORK/unload.sh" --yes --output "$WORK/u16"
else
	FAILS=$((FAILS + 1)); echo "FAIL setup load for unload test"
fi

# 17
fresh
if sh "$L" --yes --module "$FAKE_ROOT/state/module" --manifest "$WORK/manifest" --output "$WORK/o17" >/dev/null 2>&1; then
	FAKE_RMMOD_FAIL=1 expect "rmmod failure" 1 "rmmod failed" "$WORK/unload.sh" --yes --output "$WORK/u17"
else
	FAILS=$((FAILS + 1)); echo "FAIL setup load for rmmod-failure test"
fi

# 18
fresh
if sh "$L" --yes --module "$FAKE_ROOT/state/module" --manifest "$WORK/manifest" --output "$WORK/o18" >/dev/null 2>&1; then
	FAKE_LEFTOVER=1 expect "leftover sysfs" 1 "driver binding still present" "$WORK/unload.sh" --yes --output "$WORK/u18"
else
	FAILS=$((FAILS + 1)); echo "FAIL setup load for leftover test"
fi

# 19
fresh
expect "unload without --yes" 1 "refused" "$WORK/unload.sh" --output "$WORK/u19"

# 20
fresh
FAKE_STAGE=0x03 sh "$L" --yes --module "$FAKE_ROOT/state/module" --manifest "$WORK/manifest" --output "$WORK/o20" >/dev/null 2>&1
if ! "$FAKE_ROOT/bin/lsmod" 2>/dev/null | grep -q '^fon_tdm_drv '; then
	PASSES=$((PASSES + 1)); echo "PASS failed verification cleans up module"
else
	FAILS=$((FAILS + 1)); echo "FAIL failed verification left module loaded"
fi

printf '\n%s passed, %s failed\n' "$PASSES" "$FAILS"
[ "$FAILS" -eq 0 ] || exit 1
