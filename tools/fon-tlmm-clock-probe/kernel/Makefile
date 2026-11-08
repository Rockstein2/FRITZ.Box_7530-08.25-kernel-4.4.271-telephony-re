# SPDX-License-Identifier: GPL-2.0-only
#
# Optional kernel-side alternative.  This is NOT part of the default build.
# Build only in an offline copy of the target kernel tree:
#
#   make -C /path/to/linux-6.12.112 \
#        M=$PWD/tools/fon-tlmm-clock-probe/kernel modules
#
# Do not load the resulting module without the separate hardware approval in
# docs/runbook/fon-stage-c0plus-software-clock-probe.md.

obj-m += fon_tlmm_probe.o
