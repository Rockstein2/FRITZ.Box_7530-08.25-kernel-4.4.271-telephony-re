#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
#
# Tests for bench/collect-stage-c0.sh.
#
# The collector is rewritten to read from a temporary fake root, and every
# command that could change hardware is stubbed.  The tests prove:
#   - only reads are issued;
#   - the summary reflects the fake state;
#   - missing debugfs is reported, not silently ignored.
#
# Usage: sh bench/tests/c0.sh

set -u
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO=$(CDPATH= cd -- "$HERE/../.." && pwd)
WORK=${TMPDIR:-/tmp/opencode}/fon-c0-tests
PASSES=0
FAILS=0

pass() { PASSES=$((PASSES + 1)); printf 'PASS %s\n' "$1"; }
fail() { FAILS=$((FAILS + 1)); printf 'FAIL %s\n' "$1"; }

check() {
	name=$1
	want=$2
	got=$3
	if [ "$got" = "$want" ]; then
		pass "$name"
	else
		fail "$name (got '$got' want '$want')"
	fi
}

fresh() {
	rm -rf "$WORK"
	mkdir -p "$WORK/root/bin" "$WORK/root/proc" "$WORK/root/sys/kernel/debug"
	mkdir -p "$WORK/root/sys/firmware/devicetree/base/soc/fon-tdm@7700000"
	mkdir -p "$WORK/root/etc"
	printf '%s\0' "AVM FRITZ!Box 7530" >"$WORK/root/sys/firmware/devicetree/base/model"
	printf '%s\0' "avm,fritzbox-7530" >"$WORK/root/sys/firmware/devicetree/base/compatible"
	printf '%s\0' "okay" >"$WORK/root/sys/firmware/devicetree/base/soc/fon-tdm@7700000/status"
	printf '%s\0' "8" >"$WORK/root/sys/firmware/devicetree/base/soc/fon-tdm@7700000/qcom,tdm-slots"
	printf 'DISTRIB_DESCRIPTION="OpenWrt 25.12.6"\n' >"$WORK/root/etc/openwrt_release"
	printf ' coherent_pool=4M\n' >"$WORK/root/proc/cmdline"
	printf 'ttyMSM0   -W- (EC  p  )  248:0\n' >"$WORK/root/proc/consoles"
	printf '80000000-87ffffff : System RAM\n' >"$WORK/root/proc/iomem"
	printf ' 12: 1 GIC 12 Edge timer\n' >"$WORK/root/proc/interrupts"
	printf 'MemTotal: 243932 kB\n' >"$WORK/root/proc/meminfo"

	# Every command that could touch hardware is a trap.
	for c in insmod rmmod modprobe devmem i2cset i2cget mmap; do
		printf '#!/bin/sh\necho "%s $*" >>"%s/calls"\nexit 1\n' "$c" "$WORK" >"$WORK/root/bin/$c"
		chmod +x "$WORK/root/bin/$c"
	done
	: >"$WORK/calls"

	# Copy the collector and redirect the fixed paths into the fake root.
	sed \
		-e "s#/sys/firmware/devicetree/base#$WORK/root/sys/firmware/devicetree/base#g" \
		-e "s#/sys/kernel/debug#$WORK/root/sys/kernel/debug#g" \
		-e "s#/proc/#$WORK/root/proc/#g" \
		-e "s#/etc/openwrt_release#$WORK/root/etc/openwrt_release#g" \
		"$REPO/bench/collect-stage-c0.sh" >"$WORK/collect.sh"

	PATH="$WORK/root/bin:$PATH"
	export PATH
}

run() {
	out=$1
	shift
	sh "$WORK/collect.sh" "$out" >"$WORK/run.log" 2>&1
	echo $?
}

# 1: healthy fake root, no debugfs clock file
fresh
rc=$(run "$WORK/out1")
check "runs without debugfs clocks" 0 "$rc"
check "fon node detected" 2 "$(grep -c 'qcom,tdm-slots' "$WORK/out1/fon-node.txt")"
check "no clock/reset/pinctrl in DT" "absent absent absent" \
	"$(cat "$WORK/out1/fon-clocks.txt" "$WORK/out1/fon-resets.txt" "$WORK/out1/fon-pinctrl.txt" | tr '\n' ' ' | sed 's/ $//')"
check "iomem has no ADSS owner" "no ADSS ranges claimed" "$(cat "$WORK/out1/adss-ranges.txt")"
check "irq summary" "SPI 156/159 not present" "$(cat "$WORK/out1/adss-irqs.txt")"
check "clocks unavailable is reported" \
	"clk_summary unavailable (debugfs not mounted or not configured)" \
	"$(cat "$WORK/out1/audio-clocks.txt")"
check "archive created" 1 "$([ -f "$WORK/out1.tar.gz" ] && echo 1 || echo 0)"
check "no hardware command was run" "" "$(cat "$WORK/calls")"

# 2: with clk_summary present
fresh
mkdir -p "$WORK/root/sys/kernel/debug/clk"
cat >"$WORK/root/sys/kernel/debug/clk/clk_summary" <<'EOF'
   clock                         enable_cnt  prepare_cnt ...
      pcnoc_clk_src                    6          6 ...
              gcc_audio_ahb_clk        0          0 ...
         audio_clk_src                 0          0 ...
            gcc_audio_pwm_clk          0          0 ...
EOF
rc=$(run "$WORK/out2")
check "runs with clk_summary" 0 "$rc"
check "audio clocks captured" 4 "$(grep -c 'clk' "$WORK/out2/audio-clocks.txt")"
check "ahb enable count read" 0 "$(awk '/gcc_audio_ahb_clk/ { print $2; exit }' "$WORK/out2/audio-clocks.txt")"

# 3: pinctrl present
fresh
mkdir -p "$WORK/root/sys/kernel/debug/pinctrl/1000000.pinctrl"
printf 'pin 40 (GPIO_40): (MUX UNCLAIMED) (GPIO UNCLAIMED)\n' \
	>"$WORK/root/sys/kernel/debug/pinctrl/1000000.pinctrl/pinmux-pins"
printf 'pin 22 (GPIO_22): (MUX UNCLAIMED) (GPIO UNCLAIMED)\n' \
	>>"$WORK/root/sys/kernel/debug/pinctrl/1000000.pinctrl/pinmux-pins"
rc=$(run "$WORK/out3")
check "runs with pinctrl" 0 "$rc"
check "pins 22 and 40 captured" 2 "$(grep -c '^pin' "$WORK/out3/pinctrl-pcm-40.txt")"

# 4: missing FON node
fresh
rm -rf "$WORK/root/sys/firmware/devicetree/base/soc/fon-tdm@7700000"
rc=$(run "$WORK/out4")
check "runs without FON node" 0 "$rc"
check "missing FON node reported" absent "$(cat "$WORK/out4/fon-node.txt")"

# 5: debugfs mounted but pinctrl missing
fresh
mkdir -p "$WORK/root/sys/kernel/debug/clk"
printf '   gcc_audio_ahb_clk 0 0\n' >"$WORK/root/sys/kernel/debug/clk/clk_summary"
rc=$(run "$WORK/out5")
check "runs without pinctrl" 0 "$rc"
check "missing pinctrl reported" "pinctrl debugfs unavailable" \
	"$(cat "$WORK/out5/pinctrl-pcm-40.txt")"

# 6: unwritable output
fresh
rc=$(run "/proc/nonexistent-dir/out")
if [ "$rc" -ne 0 ]; then
	pass "refuses an impossible output path"
else
	fail "refuses an impossible output path"
fi

printf '\n%d passed, %d failed\n' "$PASSES" "$FAILS"
[ "$FAILS" -eq 0 ]
