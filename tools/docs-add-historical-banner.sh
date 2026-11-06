#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
#
# Add a "historical document" banner to docs files that are analysis records
# rather than current state.  Idempotent: a file that already has the banner
# is left untouched.  Prints one line per file: ADDED / PRESENT / SKIP.

set -eu
DOCS=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)/docs
# Restructured layout: runbooks and history live in subdirectories.
RUNBOOK_DIR="$DOCS/runbook"
HISTORY_DIR="$DOCS/history"

# Files that describe current state and must NOT get the banner.
CURRENT="fon-known-facts.md fon-open-questions.md fon-go-no-go.md"
# Files that are operational plans/runbooks: they get a different banner.
RUNBOOK="fon-first-hardware-test.md fon-recovery-plan.md fon-recovery-ram-boot.md fon-test-image-safety.md fon-test-image-build.md fon-build-validation.md"

HIST_BANNER='> **Status: historical analysis.**
> This document records the reasoning and evidence as of the date it was
> written.  Some of its `UNKNOWN` / `UNVERIFIED` markers have since been
> answered.
> - Current confirmed facts: `docs/fon-known-facts.md`
> - Current open questions: `docs/fon-open-questions.md`
> - This file is kept for the reasoning trail, not as a status report.'

RUN_BANNER='> **Status: operational document.**
> This is a runbook, not an evidence record.  Hardware facts are maintained in
> `docs/fon-known-facts.md`; unresolved items in `docs/fon-open-questions.md`.'

insert_banner() {
	file=$1
	banner=$2
	marker='> **Status:'

	if grep -q '^> \*\*Status: historical analysis' "$file" ||
		grep -q '^> \*\*Status: operational document' "$file"; then
		echo "PRESENT $file"
		return
	fi
	if grep -q '^> \*\*Status:' "$file"; then
		echo "SKIP    $file (has its own Status banner)"
		return
	fi

	# Insert after the first heading line.
	tmp="$file.banner.tmp"
	awk -v banner="$banner" '
		BEGIN { done = 0 }
		{ print }
		!done && /^# / { print ""; print banner; done = 1 }
	' "$file" >"$tmp"
	mv "$tmp" "$file"
	echo "ADDED   $file"
}

for f in "$DOCS"/*.md "$HISTORY_DIR"/*.md; do
	name=$(basename "$f")
	skip=0
	for c in $CURRENT $RUNBOOK; do
		[ "$name" = "$c" ] && skip=1
	done
	[ "$skip" = 1 ] && continue
	insert_banner "$f" "$HIST_BANNER"
done

for c in $RUNBOOK; do
	[ -f "$RUNBOOK_DIR/$c" ] && insert_banner "$RUNBOOK_DIR/$c" "$RUN_BANNER"
done

# The reference-only OEM boot log is not a document; nothing to banner.
