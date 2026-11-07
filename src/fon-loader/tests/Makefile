# SPDX-License-Identifier: GPL-2.0-only
CC ?= cc
CFLAGS ?= -Wall -Wextra -Werror -O2 -I.. -I../../fon-firmware

all: fon_loader_test

fon_loader_test: fon_loader_test.c ../fon_loader.c ../fon_loader.h \
		../../fon-firmware/fon_dialog_fw.c ../../fon-firmware/fon_dialog_fw.h
	$(CC) $(CFLAGS) ../fon_loader.c ../../fon-firmware/fon_dialog_fw.c \
		fon_loader_test.c -o $@

run: fon_loader_test
	./fon_loader_test

clean:
	rm -f fon_loader_test

.PHONY: all run clean
