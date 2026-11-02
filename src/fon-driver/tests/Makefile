# SPDX-License-Identifier: GPL-2.0-only
CC ?= cc
CFLAGS ?= -Wall -Wextra -Werror -O2 -I..

all: fon_tdm_test fon_dma_test

fon_tdm_test: fon_tdm_test.c ../fon_tdm.c ../fon_tdm.h
	$(CC) $(CFLAGS) ../fon_tdm.c fon_tdm_test.c -o $@

fon_dma_test: fon_dma_test.c ../fon_dma.c ../fon_dma.h
	$(CC) $(CFLAGS) ../fon_dma.c fon_dma_test.c -o $@

run: all
	./fon_tdm_test
	./fon_dma_test

clean:
	rm -f fon_tdm_test fon_dma_test

.PHONY: all run clean
