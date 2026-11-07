# SPDX-License-Identifier: GPL-2.0-only
#
# Shared fake-root helpers for bench script tests.
#
# These stubs make it impossible for the tests to touch real hardware:
#   - insmod/rmmod/modinfo/lsmod/... are shell stubs;
#   - /sys and /proc are redirected into $FAKE_ROOT by rewriting the script;
#   - the "module" is a text file.
#
# Source this file, set FAKE_ROOT, then call fake_reset.

FAKE_ROOT=${FAKE_ROOT:?FAKE_ROOT must be set}

fake_reset() {
	rm -rf "$FAKE_ROOT"
	mkdir -p "$FAKE_ROOT/bin" "$FAKE_ROOT/state"
	mkdir -p "$FAKE_ROOT/sys/firmware/devicetree/base/soc/fon-tdm@7700000"
	mkdir -p "$FAKE_ROOT/sys/bus/platform/devices"
	mkdir -p "$FAKE_ROOT/proc"
	: >"$FAKE_ROOT/state/calls"
	: >"$FAKE_ROOT/state/loaded"
	: >"$FAKE_ROOT/state/dmesg"
	printf '%s\0' "AVM FRITZ!Box 7530" >"$FAKE_ROOT/sys/firmware/devicetree/base/model"
	printf '%s\0' "avm,fritzbox-7530" >"$FAKE_ROOT/sys/firmware/devicetree/base/compatible"
	printf '%s\0' "okay" >"$FAKE_ROOT/sys/firmware/devicetree/base/soc/fon-tdm@7700000/status"
	printf '00000000-0000-0000-0000-000000000000-00000000 : System RAM\n' >"$FAKE_ROOT/proc/iomem"
	printf 'CPU0\n 12: 1 GIC 12 Edge timer\n' >"$FAKE_ROOT/proc/interrupts"
	printf '6.12.112\n' >"$FAKE_ROOT/sys/kernel_release"

	cat >"$FAKE_ROOT/bin/uname" <<'EOF'
#!/bin/sh
if [ "${1:-}" = "-r" ]; then
	cat "$FAKE_ROOT/sys/kernel_release"
else
	echo "Linux fake 6.12.112 armv7l"
fi
EOF

	cat >"$FAKE_ROOT/bin/dmesg" <<'EOF'
#!/bin/sh
cat "$FAKE_ROOT/state/dmesg" 2>/dev/null || true
EOF

	cat >"$FAKE_ROOT/bin/lsmod" <<'EOF'
#!/bin/sh
echo "Module Size Used"
if [ -s "$FAKE_ROOT/state/loaded" ]; then
	cat "$FAKE_ROOT/state/loaded"
fi
true
EOF

	cat >"$FAKE_ROOT/bin/modinfo" <<'EOF'
#!/bin/sh
[ -f "$FAKE_ROOT/state/modinfo" ] || exit 1
cat "$FAKE_ROOT/state/modinfo"
EOF

	cat >"$FAKE_ROOT/bin/insmod" <<'EOF'
#!/bin/sh
echo "insmod $*" >>"$FAKE_ROOT/state/calls"
[ "${FAKE_INSMOD_FAIL:-0}" = 1 ] && exit 1
printf 'fon_tdm_drv 72768 0\n' >"$FAKE_ROOT/state/loaded"
[ "${FAKE_BIND_FAIL:-0}" = 1 ] && exit 0
d="$FAKE_ROOT/sys/bus/platform/devices/fon-tdm"
mkdir -p "$d"
: >"$d/driver"
printf '%s\n' "${FAKE_STAGE:-0x23}" >"$d/stage"
cat >"$d/diagnostics" <<EOD
mode=probe-only
state=1
diag_valid=0
stage=${FAKE_STAGE:-0x23}
resource_mask=0x3f
dt_overlap=0
irq_spi=156/159
irq_intid=188/191
irq=-1
dma_prepared=0
dma_started=0
EOD
echo "fon_tdm_drv: probe-only: resources=0x3f irq_spi=156/159 irq_intid=188/191" >>"$FAKE_ROOT/state/dmesg"
echo "FON probe-only ready; no MMIO/clock/reset/IRQ/DMA access" >>"$FAKE_ROOT/state/dmesg"
if [ "${FAKE_IOMEM_CHANGE:-0}" = 1 ]; then
	echo "77000000-77000033 : fon-tdm" >>"$FAKE_ROOT/proc/iomem"
fi
exit 0
EOF

	cat >"$FAKE_ROOT/bin/rmmod" <<'EOF'
#!/bin/sh
echo "rmmod $*" >>"$FAKE_ROOT/state/calls"
[ "${FAKE_RMMOD_FAIL:-0}" = 1 ] && exit 1
: >"$FAKE_ROOT/state/loaded"
d="$FAKE_ROOT/sys/bus/platform/devices/fon-tdm"
if [ "${FAKE_LEFTOVER:-0}" = 1 ]; then
	mkdir -p "$d"
	: >"$d/driver"
	printf '0x23\n' >"$d/stage"
else
	rm -rf "$d"
fi
exit 0
EOF

	# The fake SHA is controlled only by state/sha; this makes it possible
	# to test a manifest mismatch without a real binary.
	cat >"$FAKE_ROOT/bin/sha256sum" <<'EOF'
#!/bin/sh
cat "$FAKE_ROOT/state/sha" | tr -d '\n'
echo "  $1"
EOF

	cat >"$FAKE_ROOT/bin/id" <<'EOF'
#!/bin/sh
if [ "${1:-}" = "-u" ]; then
	echo 0
else
	command id "$@"
fi
EOF

	chmod +x "$FAKE_ROOT/bin/"*
}

fake_env() {
	PATH="$FAKE_ROOT/bin:$PATH"
	export PATH FAKE_ROOT
}

fake_module() {
	sha=${1:-b2a5679c45f68bab0ea7d68109dd0b9952a208937554742cf1d537876b6181c5}
	printf 'fake-module' >"$FAKE_ROOT/state/module"
	printf '%s\n' "$sha" >"$FAKE_ROOT/state/sha"
	cat >"$FAKE_ROOT/state/modinfo" <<EOF
filename:       $FAKE_ROOT/state/module
license:        GPL
depends:        
name:           fon_tdm_drv
vermagic:       6.12.112 SMP mod_unload ARMv7 p2v8 
parm:           probe_only (bool)
EOF
}
