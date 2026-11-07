#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
#
# Stage C0: passive clock/pinctrl/ADSS-ownership diagnostics.
#
# Reads DT, /proc and debugfs.  Never enables a clock, never asserts a
# reset, never maps MMIO, never touches GPIO, never starts DMA.
#
# Some debugfs files are generated from cached state, but others make the
# clock or pinctrl provider read its own hardware.  Those reads are
# considered low-risk but are NOT claimed to be side-effect free.
#
# POSIX/busybox ash compatible.  Writes only under the output directory.

set -u

OUT=${1:-/tmp/fon-stage-c0-$(date +%Y%m%d-%H%M%S)}
DT=/sys/firmware/devicetree/base
FON_NODE="$DT/soc/fon-tdm@7700000"

die() {
	printf 'FAIL: %s\n' "$*" >&2
	exit 1
}

note() {
	printf '%s\n' "$*"
}

mkdir -p "$OUT" || die "cannot create $OUT"
[ -w "$OUT" ] || die "$OUT is not writable"

printf 'Collecting passive Stage C0 into %s\n' "$OUT"
printf 'No clock, reset, MMIO, GPIO or DMA operation is performed.\n'

# ---------------------------------------------------------------- identity
{
	uname -a
	printf 'release: '
	uname -r
} >"$OUT/uname.txt" 2>&1

for f in /etc/openwrt_release /proc/cmdline /proc/consoles; do
	[ -r "$f" ] && cat "$f" >"$OUT/$(basename "$f").txt" 2>&1
done

if [ -r "$DT/model" ]; then
	tr -d '\0' <"$DT/model" >"$OUT/model.txt"
fi
if [ -r "$DT/compatible" ]; then
	tr -d '\0' <"$DT/compatible" >"$OUT/compatible.txt"
fi

# ------------------------------------------------------------ FON DT node
if [ -d "$FON_NODE" ]; then
	note "FON DT node present"
	{
		# qcom,tdm-slots is a binary u32; stripping NULs would hide it.
		if [ -r "$FON_NODE/qcom,tdm-slots" ]; then
			# dtc stores cells big-endian.  busybox hexdump has no
			# endian modifier and od may be absent, so take the hex
			# bytes from hexdump -C and combine them in awk.
			# BusyBox awk has no strtonum, so combine the hex bytes by
			# string concatenation and let printf convert the result.
			# Neither strtonum nor hex string arithmetic is portable
			# across gawk and BusyBox awk, so do it with arithmetic.
			slots=$(hexdump -C -n4 "$FON_NODE/qcom,tdm-slots" 2>/dev/null |
				awk 'function h(x,  i, d) {
					d = 0
					x = tolower(x)
					for (i = 1; i <= length(x); i++) {
						c = index("0123456789abcdef", substr(x, i, 1))
						d = d * 16 + (c - 1)
					}
					return d
				}
				NR == 1 { printf "%d", h($2) * 16777216 + h($3) * 65536 + h($4) * 256 + h($5) }')
			printf 'qcom,tdm-slots: %s\n' "${slots:-unreadable}"
		fi
		if [ -r "$FON_NODE/status" ]; then
			printf 'status: '
			tr -d '\0' <"$FON_NODE/status"
			echo
		fi
		ls -1 "$FON_NODE"
	} >"$OUT/fon-node.txt" 2>&1
	tar -cf "$OUT/fon-node.tar" -C "$FON_NODE" . 2>/dev/null || true

	# Clock/reset linkage in the live DT, not in the source tree.
	[ -e "$FON_NODE/clocks" ] && echo present >"$OUT/fon-clocks.txt" || echo absent >"$OUT/fon-clocks.txt"
	[ -e "$FON_NODE/resets" ] && echo present >"$OUT/fon-resets.txt" || echo absent >"$OUT/fon-resets.txt"
	[ -e "$FON_NODE/pinctrl-0" ] && echo present >"$OUT/fon-pinctrl.txt" || echo absent >"$OUT/fon-pinctrl.txt"
else
	note "FON DT node absent - use the probe-only test image"
	echo absent >"$OUT/fon-node.txt"
	echo absent >"$OUT/fon-clocks.txt"
	echo absent >"$OUT/fon-resets.txt"
	echo absent >"$OUT/fon-pinctrl.txt"
fi

# -------------------------------------------------------- passive /proc
for f in /proc/iomem /proc/interrupts /proc/meminfo; do
	[ -r "$f" ] && cat "$f" >"$OUT/$(basename "$f").txt" 2>&1
done

{
	# A claimed range looks like "07700000-07700033 : owner".
	# A free or never-mapped range has no " : owner" suffix.
	if grep -E '^[[:space:]]*0?770[0-9a-f]{4}' "$OUT/iomem.txt" 2>/dev/null | grep -q ' : '; then
		grep -E '^[[:space:]]*0?770[0-9a-f]{4}' "$OUT/iomem.txt"
	else
		echo 'no ADSS ranges claimed'
	fi
} >"$OUT/adss-ranges.txt"

{
	grep -n 'GIC-0 *\(156\|159\)' "$OUT/interrupts.txt" 2>/dev/null || echo 'SPI 156/159 not present'
} >"$OUT/adss-irqs.txt"

# --------------------------------------------------------------- debugfs
if [ -r /sys/kernel/debug/clk/clk_summary ]; then
	cp /sys/kernel/debug/clk/clk_summary "$OUT/clk_summary.txt" 2>/dev/null || true
	{
		printf 'name enable prepare protect rate hw consumer\n'
		grep -E 'audio|pcnoc_clk_src|fepll200' "$OUT/clk_summary.txt" 2>/dev/null
	} >"$OUT/audio-clocks.txt"
	note "audio clock block captured"
else
	echo 'clk_summary unavailable (debugfs not mounted or not configured)' >"$OUT/audio-clocks.txt"
	note "debugfs clocks unavailable"
fi

if [ -d /sys/kernel/debug/pinctrl ]; then
	find /sys/kernel/debug/pinctrl -maxdepth 2 -type f -print >"$OUT/pinctrl-files.txt" 2>/dev/null || true
	for d in /sys/kernel/debug/pinctrl/*/; do
		name=$(basename "$d")
		[ -r "$d/pinmux-pins" ] && \
			grep -E 'pin (2[0-7]|40) ' "$d/pinmux-pins" >>"$OUT/pinctrl-pcm-40.txt" 2>/dev/null
	done
	[ -s "$OUT/pinctrl-pcm-40.txt" ] || echo 'no matching pinmux entries' >"$OUT/pinctrl-pcm-40.txt"
	# Are any PCM pins actually muxed to a peripheral function?
	if grep -q 'MUX UNCLAIMED' "$OUT/pinctrl-pcm-40.txt" 2>/dev/null &&
	   ! grep -vq 'MUX UNCLAIMED' "$OUT/pinctrl-pcm-40.txt" 2>/dev/null; then
		echo 'all PCM/GPIO40 pins mux-unclaimed: no audio function selected' \
			>"$OUT/pinctrl-summary.txt"
	elif grep -vq 'MUX UNCLAIMED' "$OUT/pinctrl-pcm-40.txt" 2>/dev/null; then
		echo 'some PCM pins are muxed to a function' >"$OUT/pinctrl-summary.txt"
	else
		echo 'no pinctrl data' >"$OUT/pinctrl-summary.txt"
	fi
else
	echo 'pinctrl debugfs unavailable' >"$OUT/pinctrl-pcm-40.txt"
fi

# ------------------------------------------------------------------ gates
# Decide once, then print.  Splitting the decision from the output avoids the
# command-substitution precedence trap that produced two lines on hardware.
# A claimed range looks like "0a000000-... : owner".  The header line of
# /proc/iomem has no colon, so testing for ' : ' anywhere in the file would
# report "claimed" on a completely empty map.
# Only the ADSS window counts for the FON gate.
if grep -Eq '^[[:space:]]*0?77[0-9a-f]{5}-[0-9a-f]+[[:space:]]*: ' \
	"$OUT/iomem.txt" 2>/dev/null; then
	owner=claimed
else
	owner=free
fi
ahb=unknown
if [ -r "$OUT/clk_summary.txt" ]; then
	v=$(awk '/gcc_audio_ahb_clk/ { print $2; exit }' "$OUT/clk_summary.txt")
	[ -n "${v:-}" ] && ahb=$v
fi
{
	printf 'gate\tstate\n'
	printf 'fon-node\t%s\n' "$([ -d "$FON_NODE" ] && echo present || echo absent)"
	printf 'fon-clocks\t%s\n' "$(cat "$OUT/fon-clocks.txt" 2>/dev/null)"
	printf 'fon-resets\t%s\n' "$(cat "$OUT/fon-resets.txt" 2>/dev/null)"
	printf 'audio-ahb-enable\t%s\n' "$ahb"
	printf 'adss-iomem-owner\t%s\n' "$owner"
} >"$OUT/gates.txt"

tar -czf "$OUT.tar.gz" -C "$(dirname "$OUT")" "$(basename "$OUT")" 2>/dev/null || true

note "Stage C0 archive: $OUT.tar.gz"
note "Read-only: nothing was enabled, reset, mapped, written or started."
