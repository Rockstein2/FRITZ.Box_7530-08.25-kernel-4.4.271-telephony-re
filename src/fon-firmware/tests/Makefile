# SPDX-License-Identifier: GPL-2.0-only
CC ?= cc
CFLAGS ?= -Wall -Wextra -Werror -O2 -I..

all: fon_dialog_test

fon_dialog_test: fon_dialog_test.c ../fon_dialog_fw.c ../fon_dialog_fw.h
	$(CC) $(CFLAGS) ../fon_dialog_fw.c fon_dialog_test.c -o $@

run: fon_dialog_test
	./fon_dialog_test

clean:
	rm -f fon_dialog_test

.PHONY: all run clean
