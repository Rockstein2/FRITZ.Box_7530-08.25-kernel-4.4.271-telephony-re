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

HIST_BANNER='> **Status: historical analysis.**
> This document records the reasoning and evidence as of the date it was
> written.  Some of its `UNKNOWN` / `UNVERIFIED` markers have since been
> answered.
> - Current confirmed facts: `../fon-known-facts.md`
> - Current open questions: `../fon-open-questions.md`
> - This file is kept for the reasoning trail, not as a status report.'

RUN_BANNER='> **Status: operational document.**
> This is a runbook, not an evidence record.  Hardware facts are maintained in
> `../fon-known-facts.md`; unresolved items in `../fon-open-questions.md`.'

insert_banner() {
	file=$1
	banner=$2
	marker='> **Status:'

	if grep -q '^> \*\*Status: historical analysis' "$file" ||
		grep -q '^> \*\*Status: operational document' "$file" ||
		grep -q '^> \*\*Historical .*record' "$file"; then
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

for f in "$HISTORY_DIR"/*.md; do
	insert_banner "$f" "$HIST_BANNER"
done

for f in "$RUNBOOK_DIR"/*.md; do
	insert_banner "$f" "$RUN_BANNER"
done

# The reference-only OEM boot log is not a document; nothing to banner.
