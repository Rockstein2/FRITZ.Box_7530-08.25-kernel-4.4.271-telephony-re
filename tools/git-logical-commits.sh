#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
#
# Create the logical commit series for the probe-only work plus the
# documentation restructure.  Prints every commit; stops on the first failure.
#
#   sh tools/git-logical-commits.sh           # dry run: show the plan
#   sh tools/git-logical-commits.sh --apply   # create the commits
#
# Nothing is pushed.  User-owned files (`fon-last10.patch`, `fon-log.txt`) are
# never staged.

set -eu
REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$REPO"
APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

docs_plan() { printf '  %s\n' "$@"; }

if [ "$APPLY" = 0 ]; then
	cat <<'EOF'
Commit plan (8 commits):

 1 feat(driver): parse DT IRQ specifiers without requesting them
      src/fon-driver/fon_hw.c, src/fon-driver/fon_hw.h

 2 dts: regenerate 900/901 patches against the pristine board DTS
      openwrt/target/linux/ipq40xx/patches-6.12/900-*.patch
      openwrt/test-patches/901-*.patch

 3 build: make DT preparation idempotent and add DTB/test helpers
      tools/prepare-fon-openwrt-tree.sh, tools/prepare-fon-image.sh,
      tools/build-fon-dts-test.sh (if changed), tools/record-fon-artifact.sh,
      tools/tests/

 4 bench: strict probe-only load/unload with fake-root test suite
      bench/load-probe-only.sh, bench/unload.sh, bench/README.md,
      bench/expected-stage-a.txt, bench/expected-stage-b.txt,
      bench/fon_tdm_drv.sha256, bench/tests/

 5 docs: split documentation into known-facts / runbook / history
      docs/README.md, docs/fon-known-facts.md, docs/fon-open-questions.md,
      docs/fon-go-no-go.md, docs/runbook/*, docs/history/*,
      root/tools/src READMEs, tools/docs-*.sh

 6 docs: record the OEM FRITZ!OS bootlog as reference-only
      docs/history/wiki-fritzos-oem-bootlog-reference.txt,
      docs/history/fon-oem-bootlog-crosscheck.md

 7 docs: record stock and probe-only openwrt image builds
      docs/runbook/fon-build-validation.md

 8 chore: ignore private task files
      .gitignore

Run with --apply to execute.
EOF
	exit 0
fi

commit() {
	msg=$1
	shift
	git commit -q -m "$msg" -- "$@"
	echo "committed: $(git log -1 --format='%h %s')"
}

# 1 — driver
git add src/fon-driver/fon_hw.c src/fon-driver/fon_hw.h
commit "feat(driver): parse DT IRQ specifiers without requesting them

Probe-only mode now reads the raw DT interrupt specifiers (SPI 156/159,
INTID 188/191) with of_irq_parse_one() and reports them through sysfs,
without calling platform_get_irq_optional() or requesting any IRQ.

Also releases the node references it takes and adds the diagnostics fields
used by the bench scripts." \
	src/fon-driver/fon_hw.c src/fon-driver/fon_hw.h

# 2 — device tree patches
git add openwrt/target/linux/ipq40xx/patches-6.12/900-arm-dts-ipq4019-fritzbox-7530-fon.patch \
	openwrt/test-patches/901-arm-dts-ipq4019-fritzbox-7530-probe-only.patch
commit "dts: regenerate 900/901 patches against the pristine board DTS

900 adds the FON node with status = \"disabled\"; 901 flips only that line to
\"okay\" for a dedicated test image.  Both are now derived from an unpatched
board DTS with diff -u, so they apply in order to the OpenWrt 25.12.6 tree
and 901 reverses cleanly." \
	openwrt/target/linux/ipq40xx/patches-6.12/900-arm-dts-ipq4019-fritzbox-7530-fon.patch \
	openwrt/test-patches/901-arm-dts-ipq4019-fritzbox-7530-probe-only.patch

# 3 — tools
git add tools/prepare-fon-openwrt-tree.sh tools/prepare-fon-image.sh \
	tools/record-fon-artifact.sh tools/tests \
	tools/docs-restructure.sh tools/docs-rewrite-links.sh \
	tools/docs-add-historical-banner.sh tools/README.md
[ -f tools/build-fon-dts-test.sh ] && git add tools/build-fon-dts-test.sh
commit "build: make DT preparation idempotent and add DTB/test helpers

prepare-fon-openwrt-tree.sh no longer copies the package source directory
(which turned the src symlink into a directory), applies 900 with -N so a
re-run is a no-op, and never reverse-applies 901.

New helpers: prepare-fon-image.sh compiles the real board DTB from a prepared
kernel tree; record-fon-artifact.sh stores .ko/.apk hashes; three docs
scripts keep the documentation layout and links reproducible.
Tests: tools/tests/ (23 cases, all pass)." \
	tools/prepare-fon-openwrt-tree.sh tools/prepare-fon-image.sh \
	tools/record-fon-artifact.sh tools/tests \
	tools/docs-restructure.sh tools/docs-rewrite-links.sh \
	tools/docs-add-historical-banner.sh tools/README.md $( [ -f tools/build-fon-dts-test.sh ] && echo tools/build-fon-dts-test.sh )

# 4 — bench
git add bench/load-probe-only.sh bench/unload.sh bench/README.md \
	bench/expected-stage-a.txt bench/expected-stage-b.txt \
	bench/fon_tdm_drv.sha256 bench/tests
commit "bench: strict probe-only load/unload with fake-root test suite

load-probe-only.sh now fails closed before insmod on any unmet precondition
(SHA-256, manifest, module metadata, kernel, board, FON node state, output
directory reuse) and verifies the post-load diagnostics before reporting
success.  unload.sh verifies module, binding and sysfs removal.

bench/tests/ runs both scripts against a fake root with stub commands:
29 cases, 0 failures, including proof that insmod is never invoked when a
pre-flight check refuses." \
	bench/load-probe-only.sh bench/unload.sh bench/README.md \
	bench/expected-stage-a.txt bench/expected-stage-b.txt \
	bench/fon_tdm_drv.sha256 bench/tests

# 5 — docs restructure
git add docs/README.md docs/fon-known-facts.md docs/fon-open-questions.md \
	docs/fon-go-no-go.md docs/runbook docs/history/fon-*.md \
	README.md src/fon-driver/README.md src/fon-firmware/README.md
git rm -r --cached --ignore-unmatch docs/fon-*.md >/dev/null 2>&1 || true
commit "docs: split documentation into known-facts / runbook / history

Layer 1 (current truth): fon-known-facts.md (every confirmed fact with its
evidence class), fon-open-questions.md (Q1-Q26, the only open-questions
list) and fon-go-no-go.md (gates linked to question ids).

Layer 2 (runbook/): procedures and build records, unchanged in substance.
Layer 3 (history/): the analysis trail, each file now carrying a
\"Status: historical analysis\" banner so stale UNKNOWN markers cannot be
mistaken for current state.

All cross-document links were rewritten and verified; three idempotent
scripts under tools/ regenerate the layout, the links and the banners." \
	docs/README.md docs/fon-known-facts.md docs/fon-open-questions.md \
	docs/fon-go-no-go.md docs/runbook docs/history/fon-avm-analysis.md \
	docs/history/fon-control-path.md docs/history/fon-dialog-boot.md \
	docs/history/fon-dialog-dependency.md \
	docs/history/fon-dialog-hardware-test-plan.md \
	docs/history/fon-feasibility.md docs/history/fon-hardware.md \
	docs/history/fon-linux612-port.md docs/history/fon-pcmlink-register-path.md \
	docs/history/fon-resource-audit.md docs/history/fon-tdm-hardware.md \
	README.md src/fon-driver/README.md src/fon-firmware/README.md

# 6 — OEM bootlog
git add docs/history/wiki-fritzos-oem-bootlog-reference.txt \
	docs/history/fon-oem-bootlog-crosscheck.md
commit "docs: record the OEM FRITZ!OS bootlog as reference-only

wiki-fritzos-oem-bootlog-reference.txt is a boot log from the original AVM
firmware (kernel 4.4.60), kept only for comparison.  The cross-check document
states what it proves (INTID 191 for mbox3, DMA channels 0/7, GPIO40 vs
GPIO35, TDM 8 kHz / ~1.0257 MHz, firmware uploaded before pcmlink) and what
it cannot prove for our 6.12 build." \
	docs/history/wiki-fritzos-oem-bootlog-reference.txt \
	docs/history/fon-oem-bootlog-crosscheck.md

# 7 — build records
git add docs/runbook/fon-build-validation.md
commit "docs: record stock and probe-only OpenWrt image builds

Both images were built from the OpenWrt 25.12.6 tree on this workstation.
The record lists the exact config deltas, sizes, SHA-256 values, the extracted
FIT contents and the finding that the embedded DTB is byte-identical to the
built board DTB." \
	docs/runbook/fon-build-validation.md

# 8 — gitignore
git add .gitignore
commit "chore: ignore private task files" .gitignore

echo
git log --oneline -8
echo
git status --short
