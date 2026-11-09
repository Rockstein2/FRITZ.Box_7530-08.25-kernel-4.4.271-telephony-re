#!/usr/bin/env python3
"""Bounded offline DIP/DSP IRQ paths; deliberately no SC14448 register names."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cr16_address_spaces as A
import cr16_dataflow as D
import cr16_dip_trace as DIP

ROOT = Path(__file__).resolve().parent.parent
SITES = {
    "normal": dict(dip=(0x28cd0, 0x28cf2), callee=(0x28732, 0x2879e),
                   dsp=(0x28a94, 0x28b08), helpers=(0x3b28, 0x3b38),
                   pointer=0x28aa8, vector=0x28ab2, ack=0x28ab4,
                   gate=0x28ad0, skip=0x28afa, synth=0x28ad8,
                   bit3=0x28aea, bit2=0x28af2,
                   dip_state=0x9b85, counter=0x2c4),
    "p2test": dict(dip=(0x27c88, 0x27caa), callee=(0x25d74, 0x25dde),
                   dsp=(0x27914, 0x27988), helpers=(0x27744, 0x27754),
                   pointer=0x27928, vector=0x27932, ack=0x27934,
                   gate=0x27950, skip=0x2797a, synth=0x27958,
                   bit3=0x2796a, bit2=0x27972,
                   dip_state=None, counter=0x224),
}
FILENAMES = ("cr16-e33-dip-events.json", "cr16-e33-dsp-events.json",
             "cr16-e33-fon-relevance.json")


def range_cites(fw, lo, hi):
    return [DIP.cite(fw, addr) for addr in sorted(fw.insns)
            if lo <= addr <= hi]


def pointer_uses(rows):
    direct, unknown = [], 0
    for row in rows:
        if row.get("operation") not in ("READ", "WRITE", "RMW"):
            continue
        address = row.get("effective_address")
        if address is None or not address.startswith("0x"):
            unknown += 1
            continue
        width = (row.get("width_bits") or 16) // 8
        start = int(address, 16)
        if start < 0xda and start + width > 0xd6:
            direct.append(row)
    return direct, unknown


def image(name, fw, rows):
    s = SITES[name]
    common = dict(image=name, firmware_sha256=A.REFERENCE_SHA[name],
        analysis_status="CONVERGED_BOUNDED_PATHS",
        related_device_evidence={"status": "RELATED_DEVICE_HYPOTHESIS",
          "source": "SC14480 Rev 1.0 pp.171-172,177,196-197",
          "0x00ff6006": "DIP_CTRL_REG candidate",
          "0x01027fd8": "DSP_INT_REG candidate; W1C is not proved on SC14448",
          "0x00ff5402": "RESET_INT_PENDING_REG candidate"},
        confidence="PARTIALLY_PROVEN")
    dip = dict(common,
        instruction_provenance=range_cites(fw, *s["dip"]) +
            range_cites(fw, *s["callee"]),
        control_flow_evidence={"irq_entry": f"0x{s['dip'][0]:06x}",
            "direct_callee": f"0x{s['callee'][0]:06x}",
            "callee_structure": ("normal compact bit/index state update" if
                                  name == "normal" else
                                  "p2test branches through further helpers")},
        dataflow_evidence={"read": "0x00ff6006 -> low byte r2",
            "ack": "0x0400 -> 0x00ff5402 before callee",
            "normal_visible_dispatch": ("event bits 1..3 index 0x9b85 and "
                "state around 0x93d0; bit0 selects bit0/bit1 clear on indexed state"
                if name == "normal" else None),
            "p2test_visible_dispatch": ("event 0x0e -> 0x25dbe; "
                "event 0x0f -> 0x25e2a; others -> 0x2658a; full downstream not traced"
                if name == "p2test" else None)},
        event_table=([{"input": "(r2 & 0x0e) == 0",
                       "branch": "0x28742 -> 0x2878e", "effect": "high-nibble processing",
                       "confidence": "LOCAL_BRANCH_ONLY"},
                      {"input": "(r2 & 0x0e) != 0",
                       "branch": "0x28744..0x2878a", "effect": "indexed byte/bit state",
                       "confidence": "PARTIALLY_PROVEN"}]
                     if name == "normal" else [
                      {"input": "[0x953e] == 0", "branch": "0x26514",
                       "effect": "alternate path unknown", "confidence": "LOCAL_BRANCH_ONLY"},
                      {"input": "[0x953e] != 0 and r9 == 0x0e",
                       "branch": "0x25dbe",
                       "effect": "further calls/unknown", "confidence": "LOCAL_BRANCH_ONLY"},
                      {"input": "[0x953e] != 0 and r9 == 0x0f",
                       "branch": "0x25e2a",
                       "effect": "unknown", "confidence": "LOCAL_BRANCH_ONLY"},
                      {"input": "[0x953e] != 0 and other r9",
                       "branch": "0x2658a",
                       "effect": "unknown", "confidence": "LOCAL_BRANCH_ONLY"}]),
        unresolved_paths=["SC14448 physical register identity/bit meaning",
            "callee downstream calls and unknown indirect targets",
            "no source-to-sink FON/slot-5 path"])
    direct, unknown = pointer_uses(rows)
    pointer_value = int.from_bytes(next((data[0xd6 - base:0xda - base]
        for base, data in fw.runs if base <= 0xd6 and 0xda <= base + len(data)),
        b""), "little")
    if pointer_value != 0x01027f80:
        raise ValueError(f"{name}: static pointer differs: {pointer_value:#x}")
    if not DIP.edge(fw, s["gate"], s["skip"]):
        raise ValueError(f"{name}: DSP event skip edge differs")
    if fw.insns[s["synth"]].operands != "$0xc:s,r10":
        raise ValueError(f"{name}: DSP synthetic bit update differs")
    dsp = dict(common, instruction_provenance=range_cites(fw, *s["dsp"]) +
        sum((range_cites(fw, h, h + 0x18) for h in s["helpers"]), []),
        control_flow_evidence={"irq_entry": f"0x{s['dsp'][0]:06x}",
            "nonzero_low_bits_1_to_3_skip_helpers": [
                f"0x{s['gate']:06x}", f"0x{s['skip']:06x}"],
            "zero_low_bits_path_sets_bits_2_and_3": f"0x{s['synth']:06x}",
            "bit3_true_target": f"0x{s['helpers'][0]:06x}",
            "bit2_true_target": f"0x{s['helpers'][1]:06x}"},
        dataflow_evidence={"static_pointer_cell": "0x000000d6",
            "static_pointer_value": "0x01027f80",
            "base_plus_0x58": "0x01027fd8 (32-bit register-pair arithmetic)",
            "read_instruction": f"0x{s['vector']:06x}",
            "write_same_word": f"0x{s['ack']:06x}",
            "bit3_test": f"0x{s['bit3']:06x}",
            "bit2_test": f"0x{s['bit2']:06x}",
            "helper_input_bits_status": ("NOT_RAW_VECTOR_BITS: on the zero "
                "low-0x0e path, firmware ORs 0x0c into r10 before testing "
                "bit3 and bit2; the nonzero path skips both calls"),
            "counter_fields": [f"0x{s['counter']+14:04x}",
                               f"0x{s['counter']+16:04x}"],
            "direct_overlapping_0xd6_0xd9": direct,
            "direct_writers": [r for r in direct if r["operation"] != "READ"],
            "unknown_address_uses": unknown,
            "runtime_writer_absence_proven": False},
        unresolved_paths=["runtime/indirect writers or copy ranges crossing 0xD6",
            "DSP event vector bit2/3 semantics and helper downstream effects",
            "W1C semantics on SC14448 unproved",
            "unknown indexed memory/call paths", "slot-5 source-to-sink path"])
    fon = dict(common, instruction_provenance=[DIP.cite(fw, a) for a in
                 (s["dip"][0], s["dsp"][0], s["vector"])],
        control_flow_evidence={"checked_paths": [
            f"dip_int 0x{s['dip'][0]:06x} -> 0x{s['callee'][0]:06x}",
            f"dsp_int 0x{s['dsp'][0]:06x} -> " +
              ", ".join(f"0x{h:06x}" for h in s["helpers"])],
            "complete_downstream_coverage": False},
        dataflow_evidence={"pcm_slot5_consumer_proven": False,
            "link_from_linux_tx_to_these_paths": "NOT_FOUND_IN_BOUNDED_PATHS",
            "dip_ram_other_writers": "see cr16-e33-dip-fill-proof.json"},
        unresolved_paths=["Linux slot-5 control word -> firmware read",
            "indirect calls and unmodelled cross-domain buffers",
            "SC14448 peripheral register identity"], confidence="UNRESOLVED")
    return dip, dsp, fon


def build(objdump):
    A._validate_inputs(objdump)
    result = ({}, {}, {})
    for name, path in A.IMAGES:
        df, fw, rows = D.run_image(name, path, objdump)
        if df.get("converged") is not True or df.get("analysis_status") != "CONVERGED":
            raise ValueError(f"{name}: NON_CONVERGED")
        for dest, entry in zip(result, image(name, fw, rows)):
            dest[name] = entry
    return {fn: {"tool": fn.removesuffix(".json") + "/1", "images": images}
            for fn, images in zip(FILENAMES, result)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--objdump", default=str(A.OBJDUMP))
    ap.add_argument("--out", default=str(ROOT / "tools" / "reports"))
    args = ap.parse_args(argv)
    try:
        DIP.publish(Path(args.out), build(args.objdump))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "cr16-e33-irq.incomplete.json").write_text(json.dumps(
            {"analysis_status": "INCOMPLETE", "reason": str(exc)}, indent=1) + "\n")
        print(f"INCOMPLETE IRQ trace: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
