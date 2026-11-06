#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
#
# Rewrite cross-document links after the docs/ split into root + runbook/ +
# history/.
#
# Rules
#   1. Each link is classified by its own reference string, not by the file:
#        docs/<n>.md   -> references a file under the original flat docs/
#        <n>.md        -> same-directory reference (docs/README.md tables,
#                         or prose in the layer that owns it)
#   2. Inside docs/ the replacement is relative to the referring file.
#      Outside docs/ the replacement stays repository-relative (docs/...).
#   3. Only existing files are rewritten.  Globs, `bench/...`, `tools/...`
#      and other repo-relative paths that merely contain `.md` are untouched.
#   4. A replacement never contains the search string it replaces, so the
#      pass is idempotent.
#
# Run from anywhere; the repository root is derived from this script.

set -eu
REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DOCS="$REPO/docs"
LAYERS=". runbook history"

build_map() {
	map=""
	for l in $LAYERS; do
		for f in "$DOCS/$l"/*.md; do
			[ -f "$f" ] || continue
			map="$map $(basename "$f"):$l"
		done
	done
	# README lives at the root layer only
	map="$map README.md:."
}

build_map

layer_of() {
	for entry in $map; do
		if [ "${entry%%:*}" = "$1" ]; then echo "${entry##*:}"; return; fi
	done
	echo ""
}

rel_prefix() {
	from=$1
	to=$2
	if [ "$from" = "$to" ]; then echo ""; return; fi
	case "$from:$to" in
	".:runbook")   echo "runbook/" ;;
	".:history")   echo "history/" ;;
	"runbook:.")   echo "../" ;;
	"runbook:history") echo "../history/" ;;
	"history:.")   echo "../" ;;
	"history:runbook") echo "../runbook/" ;;
	esac
}

# $1 file, $2 layer of the referring file, $3 "" for docs-relative,
#      "docs/" for repository-relative
rewrite() {
	file=$1
	from=$2
	base=$3
	changed=0

	for entry in $map; do
		name=${entry%%:*}
		to=${entry##*:}
		prefix=$(rel_prefix "$from" "$to")
		[ -n "$base" ] && prefix="../${prefix}"

		# (a) explicit docs/<name>.md reference
		old="docs/$name"
		new="${base}${prefix}${name}"
		if [ "$old" != "$new" ] && grep -q -- "$old" "$file"; then
			sed -i "s|$old|$new|g" "$file"
			changed=1
		fi

		# (b) same-directory reference, only when it crosses a layer
		if [ "$to" != "$from" ]; then
			new2="${prefix}${name}"
			# guard: only a path token, not part of a longer word
			if grep -qE "(^|[ (\`])$name([ \)\`,]|$)" "$file"; then
				sed -i -E "s#(^|[ (\`])$name([ \)\`,])#\\1$new2\\2#g" "$file"
				changed=1
			fi
		fi
	done

	[ "$changed" = 1 ] && echo "REWROTE ${file#"$REPO/"}"
}

for f in "$DOCS"/*.md; do
	[ -f "$f" ] || continue
	rewrite "$f" "." ""
done
for f in "$DOCS"/runbook/*.md; do
	[ -f "$f" ] || continue
	rewrite "$f" "runbook" ""
done
for f in "$DOCS"/history/*.md; do
	[ -f "$f" ] || continue
	rewrite "$f" "history" ""
done

for f in "$REPO"/README.md "$REPO"/tools/README.md "$REPO"/src/*/README.md "$REPO"/bench/README.md; do
	[ -f "$f" ] || continue
	rewrite "$f" "." "docs/"
done

echo "done"
