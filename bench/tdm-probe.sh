#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
#
# Passive TDM clock probe: count level changes on the PCM candidate pins.
#
# This only READS /sys/class/gpio/*/value.  It does not change direction,
# pinmux, clock, reset or interrupt configuration.  Exporting a pin is the
# only state change and it is undone before exit.
#
# Method (recovered from pcmlink's ipq40xxtdm_checkhw): sample each pin as
# fast as possible and count 0->1 and 1->0 transitions.  A TDM clock counts
# two transitions per period.
#
# Usage: tdm-probe.sh [SECONDS]

set -u
SECS=${1:-2}
# busybox ash without the SECONDS builtin falls back to /proc/uptime.
now() {
	if [ -r /proc/uptime ]; then
		set -- $(cat /proc/uptime)
		echo "${1%%.*}"
	else
		date +%s
	fi
}
BASE=$(awk '$0 ~ /gpiochip512/ { print 512 }' /dev/null 2>/dev/null)
[ -n "${BASE:-}" ] || BASE=512
PINS="20 21 22 23 24 25 26 27"

echo "TDM passive probe: $SECS s per pin, no pinmux or direction change"
printf '%-6s %-8s %-10s %-10s\n' pin level edges frequency

for p in $PINS; do
	g=$((BASE + p))
	sys=/sys/class/gpio/gpio$g
	if ! echo "$g" >/sys/class/gpio/export 2>/dev/null; then
		[ -e "$sys/value" ] || { printf '%-6s export failed\n' "GPIO$p"; continue; }
	fi

	# Sample in a tight loop; the shell is slow, so the measurable rate is
	# bounded by the shell, not by the pin.  That is fine: we only need to
	# know whether the pin toggles at all beyond noise.
	first=$(cat "$sys/value" 2>/dev/null)
	last=$first
	edges=0
	prev=$first
	start=$(now)
	iter=0
	while [ $(( $(now) - start )) -lt "$SECS" ]; do
		v=$(cat "$sys/value" 2>/dev/null)
		if [ "$v" != "$prev" ]; then
			edges=$((edges + 1))
			prev=$v
			last=$v
		fi
		iter=$((iter + 1))
		[ "$iter" -ge 200000 ] && break
	done

	elapsed=$(( $(now) - start ))
	[ "$elapsed" -lt 1 ] && elapsed=1
	# Two edges per period.
	freq=$((edges / 2 / elapsed))

	printf '%-6s %-8s %-10s %-10s\n' "GPIO$p" "$last" "$edges" "${freq} Hz"
	echo "$g" >/sys/class/gpio/unexport 2>/dev/null
done

echo "probe finished; no direction, mux, clock or reset was changed"
