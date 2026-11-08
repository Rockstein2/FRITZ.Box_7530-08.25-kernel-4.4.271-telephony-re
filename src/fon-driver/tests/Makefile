# SPDX-License-Identifier: GPL-2.0-only
CC ?= cc
CFLAGS ?= -Wall -Wextra -Werror -O2 -I..

all: fon_tdm_test fon_dma_test fon_c2_test

fon_tdm_test: fon_tdm_test.c ../fon_tdm.c ../fon_tdm.h
	$(CC) $(CFLAGS) ../fon_tdm.c fon_tdm_test.c -o $@

fon_dma_test: fon_dma_test.c ../fon_dma.c ../fon_dma.h
	$(CC) $(CFLAGS) ../fon_dma.c fon_dma_test.c -o $@

# The C2 helpers are pure; only linux/types.h is stubbed for the host.
HOSTINC ?= $(TMPDIR_HOST)/objcode-include
fon_c2_test: fon_c2_test.c ../fon_c2_bits.h
	@mkdir -p $(HOSTINC)/linux
	@printf '#include <stdint.h>\n#include <stdbool.h>\ntypedef uint32_t u32;\ntypedef uint16_t u16;\ntypedef uint8_t u8;\n#define BIT(n) (1UL << (n))\n' > $(HOSTINC)/linux/types.h
	$(CC) $(CFLAGS) -I$(HOSTINC) fon_c2_test.c -o $@

run: all
	./fon_tdm_test
	./fon_dma_test
	./fon_c2_test

# --- 32-bit semantics -------------------------------------------------------
#
# The IPQ4019 is ARMv7, where size_t is 32 bits.  The host is usually
# x86_64, where size_t is 64 bits, so an overflow test can silently pass for
# the wrong reason.  `make run32` rebuilds the pure TDM test with a 32-bit
# size_t and runs it there.  This is a hard requirement, not optional:
# `run-all` fails if the 32-bit build is unavailable.
#
# Two mechanisms are tried, in order:
#   1. a CROSS32_CC (e.g. arm-openwrt-linux-muslgnueabi-gcc + qemu-arm)
#   2. the host compiler with -m32
CROSS32_CC ?=
QEMU_ARM   ?= qemu-arm

fon_tdm_test32: fon_tdm_test.c ../fon_tdm.c ../fon_tdm.h
	@if [ -n "$(CROSS32_CC)" ]; then \
		echo "$(CROSS32_CC) (ARMv7)"; \
		$(CROSS32_CC) $(CFLAGS) ../fon_tdm.c fon_tdm_test.c -o $@; \
	elif echo 'int main(void){return 0;}' | $(CC) -m32 -x c - -o /dev/null 2>/dev/null; then \
		echo "$(CC) -m32 (32-bit host)"; \
		$(CC) -m32 $(CFLAGS) ../fon_tdm.c fon_tdm_test.c -o $@; \
	else \
		echo "no 32-bit toolchain available" >&2; \
		exit 2; \
	fi

run32: fon_tdm_test32
	@if file fon_tdm_test32 2>/dev/null | grep -q 'ARM'; then \
		$(QEMU_ARM) ./fon_tdm_test32; \
	else \
		./fon_tdm_test32; \
	fi

# --- sanitizers -------------------------------------------------------------
#
# ASan+UBSan on the pure helpers.  The tdm test walks buffers, so this also
# catches the write-past-the-end that a bad geometry check would cause.
SANFLAGS = -fsanitize=address,undefined -fno-omit-frame-pointer -g

fon_tdm_test_san: fon_tdm_test.c ../fon_tdm.c ../fon_tdm.h
	$(CC) $(CFLAGS) $(SANFLAGS) ../fon_tdm.c fon_tdm_test.c -o $@

fon_dma_test_san: fon_dma_test.c ../fon_dma.c ../fon_dma.h
	$(CC) $(CFLAGS) $(SANFLAGS) ../fon_dma.c fon_dma_test.c -o $@

run-san: fon_tdm_test_san fon_dma_test_san
	./fon_tdm_test_san
	./fon_dma_test_san

run-all: run run32 run-san

clean:
	rm -f fon_tdm_test fon_dma_test fon_c2_test \
	      fon_tdm_test32 fon_tdm_test_san fon_dma_test_san

.PHONY: all run run32 run-san run-all clean
