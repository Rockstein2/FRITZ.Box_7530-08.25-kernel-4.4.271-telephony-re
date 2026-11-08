#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
#
# Split docs/ into three layers:
#
#   docs/            current truth      (known-facts, open-questions, go-no-go)
#   docs/runbook/    operational        (procedures, build records)
#   docs/history/    analysis records   (reasoning trail, marked historical)
#
# Uses `git mv` so history follows the file.  Idempotent: a file already in its
# target directory is reported PRESENT and left alone.
#
# Link rewriting is a separate script: tools/docs-rewrite-links.sh

set -eu
REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DOCS="$REPO/docs"

CURRENT="README.md fon-known-facts.md fon-open-questions.md fon-go-no-go.md fon-d06-summary.md fon-adss-clock-reset.md fon-dialog-minimal-loader.md fon-tdm-control-only-plan.md"
RUNBOOK="fon-first-hardware-test.md fon-recovery-plan.md fon-recovery-ram-boot.md fon-test-image-safety.md fon-test-image-build.md fon-build-validation.md fon-stage-c1.md fon-stage-d0-uart-identification.md fon-stage-d05-pcm-net-identification.md fon-stage-d06-readonly.md fon-oem-dtb-extraction.md fon-dialog-hw-test-plan.md fon-dialog-uart-sniff-plan.md fon-tdm-passive-test.md"
HISTORY="fon-avm-analysis.md fon-control-path.md fon-dialog-boot.md fon-dialog-dependency.md fon-dialog-hardware-test-plan.md fon-feasibility.md fon-hardware.md fon-linux612-port.md fon-oem-bootlog-crosscheck.md fon-pcmlink-register-path.md fon-resource-audit.md fon-tdm-hardware.md fon-d05-pcm-net-identification.md fon-d06-dect-reset-path.md fon-d06-pcm-pinmux.md fon-d06-sc14448-startup-sequence.md fon-d06-inverter-hypotheses.md fon-adss-avm-init-sequence.md fon-adss-tdm-channel-map.md fon-audio-ahb-clock-warning.md fon-dialog-address-alias-hypotheses.md fon-dialog-board-uart-identification.md fon-dialog-boot-branch-decoding.md fon-dialog-boot-disps25.md fon-dialog-boot-handoff.md fon-dialog-boot-memory-map.md fon-dialog-copy-helper-28d56.md fon-dialog-cr16-addressing.md fon-dialog-cr16-branches.md fon-dialog-cr16-cfg.md fon-dialog-cr16-disasm.md fon-dialog-cr16-register-effects.md fon-dialog-cr16-system-registers.md fon-dialog-cr16-vector-map.md fon-dialog-external-register-map.md fon-dialog-ff6006-callgraph.md fon-dialog-firmware-pcm.md fon-dialog-firstlevel-cfg.md fon-dialog-init-dependencies.md fon-dialog-low-memory-analysis.md fon-dialog-pcm-hypotheses.md fon-dialog-peripheral-init.md fon-dialog-peripheral-map.md fon-dialog-peripheral-xrefs.md fon-dialog-uart-boot-comparison.md fon-dialog-uart-boot-protocol.md fon-tdm-clock-software-check.md"

mkdir -p "$DOCS/runbook" "$DOCS/history"

move() {
	name=$1
	dest=$2
	src="$DOCS/$name"
	dst="$DOCS/$dest/$name"

	if [ -f "$dst" ] && [ ! -f "$src" ]; then
		echo "PRESENT $dest/$name"
		return
	fi
	[ -f "$src" ] || { echo "MISSING $name"; return; }

	cd "$REPO"
	if git ls-files --error-unmatch "docs/$name" >/dev/null 2>&1; then
		git mv "docs/$name" "docs/$dest/$name"
		echo "GIT-MV  $name -> $dest/"
	else
		mv "$src" "$dst"
		echo "MV      $name -> $dest/"
	fi
}

for f in $RUNBOOK; do move "$f" runbook; done
for f in $HISTORY; do move "$f" history; done

# The reference-only OEM boot log lives next to its analysis document.
OEM_SRC_NAME="OEM-BootLog.txt"
OEM_DST_NAME="wiki-fritzos-oem-bootlog-reference.txt"
oem_src="$REPO/$OEM_SRC_NAME"
oem_dst="$DOCS/history/$OEM_DST_NAME"

if [ -f "$oem_dst" ] && [ ! -f "$oem_src" ]; then
	echo "PRESENT history/$OEM_DST_NAME"
elif [ -f "$oem_src" ]; then
	cd "$REPO"
	if git ls-files --error-unmatch "$OEM_SRC_NAME" >/dev/null 2>&1; then
		git mv "$OEM_SRC_NAME" "docs/history/$OEM_DST_NAME"
	else
		mv "$oem_src" "$oem_dst"
	fi
	echo "MV      $OEM_SRC_NAME -> history/$OEM_DST_NAME"
else
	echo "MISSING $OEM_SRC_NAME (already moved?)"
fi

echo
echo "Layout:"
printf '  root:    %s\n' "$(ls "$DOCS" | grep '\.md$' | tr '\n' ' ')"
printf '  runbook: %s\n' "$(ls "$DOCS/runbook" | tr '\n' ' ')"
printf '  history: %s\n' "$(ls "$DOCS/history" | tr '\n' ' ')"
