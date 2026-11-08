# SPDX-License-Identifier: GPL-2.0-only
#
# Host:   make
# Test:   make test
# Target: make CC=arm-openwrt-linux-muslgnueabi-gcc
#
# The default build is the userspace read-only probe.  The optional kernel
# skeleton under kernel/ is deliberately not built here.

CC ?= cc
CFLAGS ?= -O2 -g -std=c11 -Wall -Wextra -Werror
CPPFLAGS ?= -D_FILE_OFFSET_BITS=64
LDFLAGS ?=
LDLIBS ?=

TARGET := fon-tlmm-clock-probe
CORE := fon-tlmm-clock-probe-core.c
CORE_H := fon-tlmm-clock-probe-core.h
MAIN := fon-tlmm-clock-probe.c
TEST := test_core
KLOGIC := test_kernel_logic

.PHONY: all test clean

all: $(TARGET)

$(TARGET): $(MAIN) $(CORE) $(CORE_H)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ $(MAIN) $(CORE) $(LDFLAGS) $(LDLIBS)

$(TEST): tests/test_core.c $(CORE) $(CORE_H)
	$(CC) $(CPPFLAGS) $(CFLAGS) -I. -o $@ tests/test_core.c $(CORE) \
		$(LDFLAGS) $(LDLIBS)

$(KLOGIC): kernel/tests/test_logic.c kernel/fon_tlmm_probe_logic.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -I. -o $@ kernel/tests/test_logic.c \
		$(LDFLAGS) $(LDLIBS)

test: $(TEST) $(KLOGIC)
	./$(TEST)
	./$(KLOGIC)
	python3 tests/check_readonly.py .

clean:
	rm -f $(TARGET) $(TEST) $(KLOGIC)
