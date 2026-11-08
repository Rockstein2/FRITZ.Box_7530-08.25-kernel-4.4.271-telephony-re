# SPDX-License-Identifier: GPL-2.0-only
# Source this helper from other tools. It locates the workspace one level
# above the Git repository and loads the local workspace.env if present.
if [ -z "${FON_REPO:-}" ]; then
	FON_REPO=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
fi
_fon_repo=$FON_REPO
FON_WORKSPACE=${FON_WORKSPACE:-$(CDPATH= cd -- "$FON_REPO/.." && pwd)}
if [ -f "$FON_WORKSPACE/workspace.env" ]; then
	# shellcheck disable=SC1090
	. "$FON_WORKSPACE/workspace.env"
fi
: "${FON_REFERENCE:=$FON_WORKSPACE/reference}"
: "${FON_EVIDENCE:=$FON_WORKSPACE/evidence}"
: "${FON_RESTORE:=$FON_WORKSPACE/restore}"
: "${FON_BACKUPS:=$FON_WORKSPACE/backups}"
: "${FON_WORK:=$FON_WORKSPACE/work}"
: "${FON_BUILDS:=$FON_WORKSPACE/builds}"
: "${OPENWRT_SRC:=$FON_WORKSPACE/openwrt-25.12.6-source}"
: "${OPENWRT_SDK:=$FON_WORKSPACE/openwrt-sdk-25.12.6-ipq40xx-generic}"
export FON_REPO FON_WORKSPACE FON_REFERENCE FON_EVIDENCE FON_RESTORE
export FON_BACKUPS FON_WORK FON_BUILDS OPENWRT_SRC OPENWRT_SDK
