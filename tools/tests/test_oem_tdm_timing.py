#!/usr/bin/env python3
"""Numerical tests for the OEM TDM clock-check arithmetic.

Run: python3 tools/tests/test_oem_tdm_timing.py

These tests emulate the ARMv7 integer operations recovered from
Piglet_noemif.ko and pcmlink.ko.  They do not touch hardware.
"""
import sys

MASK32 = (1 << 32) - 1

PIGLET_MAGIC = 0x10624DD3
PCMLINK_CONST = 0x82DE1B43DB34B6D7

failures = 0


def check(name, condition):
    global failures
    if condition:
        print(f"PASS {name}")
    else:
        print(f"FAIL {name}")
        failures += 1


def check_close(name, got, want, tolerance):
    if abs(got - want) <= tolerance:
        print(f"PASS {name} ({got:.12g})")
    else:
        print(f"FAIL {name}: got {got:.12g} want {want:.12g} "
              f"+/- {tolerance:.12g}")
        failures += 1


def umull(a, b):
    product = (a & MASK32) * (b & MASK32)
    return product & MASK32, (product >> 32) & MASK32


def umlal(lo, hi, a, b):
    product = (a & MASK32) * (b & MASK32)
    low = (lo + (product & MASK32)) & MASK32
    carry = 1 if low < (lo & MASK32) else 0
    high = (hi + (product >> 32) + carry) & MASK32
    return low, high


def piglet_window_cycles(cyclefreq):
    """Check_TDMInterface: umull, high >> 6, * 100."""
    _, high = umull(cyclefreq, PIGLET_MAGIC)
    cycles_per_ms = high >> 6
    return (cycles_per_ms * 100) & MASK32


def piglet_window_seconds(cyclefreq):
    return piglet_window_cycles(cyclefreq) / float(cyclefreq)


def pcmlink_window_cycles(cyclefreq):
    """ipq40xxtdm_checkhw 0xa500..0xa538.

    r0:r1 = cyclefreq * 100000
    multiply by the 64-bit constant 0x82de1b43db34b6d7,
    keep the high 64-bit product, then shift right by 18.
    """
    c_low = PCMLINK_CONST & MASK32
    c_high = (PCMLINK_CONST >> 32) & MASK32
    r0, r1 = umull(cyclefreq, 100000)

    r2, r3 = umull(c_low, r0)
    r2 = 0
    r3, r2 = umlal(r3, r2, c_high, r0)
    ip = 0
    r3, ip = umlal(r3, ip, c_low, r1)
    r3 = 0
    total = ip + r2
    r2 = total & MASK32
    r3 = (total >> 32) & MASK32
    r2, r3 = umlal(r2, r3, c_high, r1)

    return ((r2 >> 18) | ((r3 << 14) & MASK32)) & MASK32


def pcmlink_window_seconds(cyclefreq):
    return pcmlink_window_cycles(cyclefreq) / float(cyclefreq)


def main():
    # Piglet: 0x10624dd3 is 2^38/1e6 scaled by 2^?; the high-word
    # shift by 6 produces cyclefreq/1000, and *100 is 100 ms.
    for cyclefreq in (1_000_000, 24_000_000, 25_000_000, 50_000_000,
                      1_000_000_000):
        check_close(f"Piglet window at {cyclefreq} Hz is 100 ms",
                    piglet_window_seconds(cyclefreq), 0.1, 0.0001)

    check("Piglet magic is the 100 ms constant",
          piglet_window_cycles(25_000_000) == 2_500_000)

    # 8 kHz over 100 ms: 800 periods, 1600 transitions, 5*1600 = 8000.
    edges_100ms = int(2 * 8000 * 0.1)
    check("Piglet 8 kHz/100 ms edge count", edges_100ms == 1600)
    check("Piglet 8 kHz formula", 5 * edges_100ms == 8000)

    # A 100 us window cannot produce the OEM 8 kHz/1.024 MHz report:
    # it has fewer than one period at 8 kHz and cannot reach 100 edges.
    edges_100us = 2 * 8000 * 0.0001
    check("100 us has less than one 8 kHz period", edges_100us < 2.0)
    check("100 us cannot reach the 100-edge threshold",
          edges_100us * 5 < 100)

    # 1.024 MHz: 100 ms gives 204800 transitions and 5*edges = 1.024 MHz;
    # 100 us gives 204.8 transitions and 5*edges = 1024 Hz.
    edges_100ms = int(2 * 1_024_000 * 0.1)
    check("Piglet 1.024 MHz/100 ms edge count", edges_100ms == 204800)
    check("Piglet 1.024 MHz formula", 5 * edges_100ms == 1_024_000)
    edges_100us = 2 * 1_024_000 * 0.0001
    check("100 us would report only ~1 kHz at 1.024 MHz",
          abs(5 * edges_100us - 1024.0) < 1.0)

    # PCMLINK: independent fixed-arithmetic emulation.
    for cyclefreq in (1_000_000, 24_000_000, 25_000_000, 50_000_000):
        window = pcmlink_window_seconds(cyclefreq)
        check_close(f"PCMLINK window at {cyclefreq} Hz is 195 ms",
                    window, 0.19500792, 0.00001)

    check("PCMLINK 25 MHz window cycles",
          pcmlink_window_cycles(25_000_000) == 4_875_198)

    # The same 5*edges expression over the 195 ms window is ~1.95x the
    # actual 8 kHz value.  This is why it is not the Piglet boot result.
    window = pcmlink_window_seconds(25_000_000)
    edges_8k = 2 * 8000 * window
    reported_8k = 5 * edges_8k
    check_close("PCMLINK 8 kHz diagnostic is ~1.95x high",
                reported_8k / 8000.0, 1.9500792, 0.0001)

    check("Piglet and PCMLINK windows differ",
          abs(piglet_window_seconds(25_000_000) -
              pcmlink_window_seconds(25_000_000)) > 0.09)

    print()
    print(f"{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
