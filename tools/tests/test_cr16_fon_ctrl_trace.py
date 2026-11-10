#!/usr/bin/env python3
"""Verify Linux mapping and synthetic provenance boundaries."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cr16_pcm_ingress as P  # noqa: E402

fail = 0


def check(label, condition):
    global fail
    print(("PASS " if condition else "FAIL ") + label)
    fail += not condition


for bit, source in ((0, "reg48[4..7]"), (4, "reg2c[17]"),
                    (5, "reg48[8..11]"), (9, "reg2c[18]")):
    field = "0..3" if bit == 0 else "5..8" if bit == 5 else str(bit)
    check(f"normal bit {bit} source", P.LINUX["normal"]["bits"][field] == source)
check("RX bit4 unmapped", (P.rx_reg44(1 << 4) ^ P.rx_reg44(0)) == 0)
check("RX bit5 -> reg44 bit8", (P.rx_reg44(1 << 5) ^
      P.rx_reg44(0)) == 0x100)
check("stack-only source cannot prove FON consumer",
      P.classify_consumer(False, True, True, physical_mapping_proven=True)
      != "FON_SLOT5_CONSUMER_PROVEN")
check("indirect consumer without source remains candidate",
      P.classify_consumer(False, True, True) == "PCM_CONTROL_CANDIDATE")
check("unknown hardware source cannot prove FON consumer",
      P.classify_consumer(False, True, False) == "UNRESOLVED")
print(f"{fail} failure(s), 0 skip(s)")
raise SystemExit(bool(fail))
