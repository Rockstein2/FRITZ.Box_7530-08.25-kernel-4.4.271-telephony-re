# SPDX-License-Identifier: GPL-2.0-only
CC ?= cc
CFLAGS ?= -Wall -Wextra -Werror -O2 -I..

all: fon_tdm_test

fon_tdm_test: fon_tdm_test.c ../fon_tdm.c ../fon_tdm.h
	$(CC) $(CFLAGS) ../fon_tdm.c fon_tdm_test.c -o $@

run: fon_tdm_test
	./fon_tdm_test

clean:
	rm -f fon_tdm_test

.PHONY: all run clean
