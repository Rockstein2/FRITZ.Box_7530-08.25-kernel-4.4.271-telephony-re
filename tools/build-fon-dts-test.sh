#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
#
# Reproducible syntax/DTC check for the FON node.  This does not build a
# complete OpenWrt image and does not touch a router.
#
# Required:
#   KERNEL_INCLUDE = path to a Linux 6.12 include/ directory containing
#                    dt-bindings/ and a qcom-ipq4019.dtsi include path
#   DTC            = path to the dtc binary
#   DTS_BASE_DIR   = directory containing qcom-ipq4019.dtsi (optional;
#                    defaults to openwrt/dts)
#
# Example:
#   KERNEL_INCLUDE=/tmp/opencode/sdk/build_dir/.../linux-6.12.112/include \
#   DTC=/tmp/opencode/sdk/.../linux-6.12.112/scripts/dtc/dtc \
#   sh tools/build-fon-dts-test.sh

set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
: "${KERNEL_INCLUDE:?set KERNEL_INCLUDE}"
: "${DTC:?set DTC}"
TMPDIR=${TMPDIR:-/tmp/opencode/fon-dts}
mkdir -p "$TMPDIR"
PRE="$TMPDIR/fon-tdm-7530-preprocessed.dts"
OUT="$TMPDIR/fon-tdm-7530.dtb"

cpp -x assembler-with-cpp -D__DTS__ -nostdinc \
	-I"$KERNEL_INCLUDE" -I"$DTS_BASE_DIR" \
	"$ROOT/openwrt/dts/fon-tdm-7530-dtc-test.dts" > "$PRE"
"$DTC" -I dts -O dtb -o "$OUT" "$PRE"
test -s "$OUT"
printf 'DTS OK: %s\n' "$OUT"
"$DTC" -I dtb -O dts "$OUT" | grep -A12 'fon-tdm@7700000'
