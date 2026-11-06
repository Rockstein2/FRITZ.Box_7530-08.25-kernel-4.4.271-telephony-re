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

CURRENT="README.md fon-known-facts.md fon-open-questions.md fon-go-no-go.md"
RUNBOOK="fon-first-hardware-test.md fon-recovery-plan.md fon-recovery-ram-boot.md fon-test-image-safety.md fon-test-image-build.md fon-build-validation.md"
HISTORY="fon-avm-analysis.md fon-control-path.md fon-dialog-boot.md fon-dialog-dependency.md fon-dialog-hardware-test-plan.md fon-feasibility.md fon-hardware.md fon-linux612-port.md fon-oem-bootlog-crosscheck.md fon-pcmlink-register-path.md fon-resource-audit.md fon-tdm-hardware.md"

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
OEM_DST_NAME="fritzos-08.25-oem-bootlog-reference.txt"
oem_src="$REPO/$OEM_SRC_NAME"
oem_dst="$DOCS/history/$OEM_DST_NAME"

if [ -f "$oem_dst" ] && [ ! -f "$oem_src" ]; then
	echo "PRESENT history/$OEM_DST_NAME"
elif [ -f "$oem_src" ]; then
	mv "$oem_src" "$oem_dst"
	echo "MV      $OEM_SRC_NAME -> history/$OEM_DST_NAME"
else
	echo "MISSING $OEM_SRC_NAME (already moved?)"
fi

echo
echo "Layout:"
printf '  root:    %s\n' "$(ls "$DOCS" | grep '\.md$' | tr '\n' ' ')"
printf '  runbook: %s\n' "$(ls "$DOCS/runbook" | tr '\n' ' ')"
printf '  history: %s\n' "$(ls "$DOCS/history" | tr '\n' ' ')"
