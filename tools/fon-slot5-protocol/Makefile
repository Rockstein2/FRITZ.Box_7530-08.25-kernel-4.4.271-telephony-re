# SPDX-License-Identifier: GPL-2.0-only
CC ?= cc
CFLAGS ?= -O2 -g -std=c11 -Wall -Wextra -Werror
CPPFLAGS ?=
LDFLAGS ?=
LDLIBS ?=

TEST := test_golden
SRC := fon_slot5.c
HDR := fon_slot5.h

.PHONY: all test clean

all: $(TEST)

$(TEST): tests/test_golden.c $(SRC) $(HDR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -I. -o $@ tests/test_golden.c $(SRC) \
		$(LDFLAGS) $(LDLIBS)

test: $(TEST)
	./$(TEST)
	python3 tests/check_offline.py .

clean:
	rm -f $(TEST)
