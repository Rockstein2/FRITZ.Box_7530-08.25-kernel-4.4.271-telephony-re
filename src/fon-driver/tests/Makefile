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

clean:
	rm -f fon_tdm_test fon_dma_test fon_c2_test

.PHONY: all run clean
