#!/usr/bin/env python3
"""Offline SC14448 PCM ingress candidate inventory; not a PCM detector.

Every firmware observation is read from the two SHA-checked images. Related
device names are annotations only. Unknown hardware transport cannot become
a slot-5 source just because an immediate matches the Linux control word.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import cr16_address_spaces as A
import cr16_cfg as C
import cr16_dataflow as D
import cr16_dip_program as P
import cr16_dip_trace as DIP

ROOT = Path(__file__).resolve().parent.parent
OEM_SHA = {
    "pcmlink.ko": (ROOT / "modules/ubik2/pcmlink.ko",
        "6620510bc1d4b0f4d670e1e93d3f308dc3002785d3129521156eb5e1bc4a363b"),
    "Piglet_noemif.ko": (ROOT / "modules/piglet_noemif/Piglet_noemif.ko",
        "24ef5a6ac42d43d1980631b43202f40c79a025a4d96337f45333a13a0d54567b"),
}
FILES = tuple(f"cr16-e35-{part}.json" for part in (
    "pcm-register-candidates", "pcm-ingress", "fon-control-consumers",
    "fon-status-producers", "dip-caller-classification",
    "targeted-indirect-paths", "proof-boundaries"))
REFERENCE_HINTS = {
    0x01027FAE: "SC14480 DSP_PCM_IN0_REG",
    0x01027FB0: "SC14480 DSP_PCM_IN1_REG",
    0x01027FB2: "SC14480 DSP_PCM_IN2_REG",
    0x01027FB4: "SC14480 DSP_PCM_IN3_REG",
    0x01027FB6: "SC14480 DSP_PCM_CTRL_REG",
    0x00FF4858: "SC14CVMDECT P2_MODE_REG (pinmux only)",
    0x00FF4868: "SC14CVMDECT P3_MODE_REG (pinmux only)",
    0x00FF6006: "SC14480 DIP_CTRL_REG (not PCM by address)",
}
GPIO_PATHS = {
    "normal": (0x2801e, 0x28024, 0x2802a, 0x2802e, 0x28032,
               0x28034, 0x28038, 0x2803c, 0x28044, 0x28048, 0x2804c),
    "p2test": (0x3cd8, 0x3cde, 0x3ce6, 0x3cea, 0x3cec,
               0x3cf4, 0x3cf8, 0x3cfc),
}
LINUX = {"normal": {"marker": "0x4000", "bits": {
    "0..3": "reg48[4..7]", "4": "reg2c[17]",
    "5..8": "reg48[8..11]", "9": "reg2c[18]", "14": "marker"}},
    "special": {"marker": "0x8000", "payload": "special_field (reg30 / TDMPriv+0x7f4)",
        "overlap_and_other_bits": "NOT_EXCLUDED: OR, no masking of special_field"},
    "rx": {"gate": "bit15 clear", "reg44":
           "0x00020008 | ((rx_status<<3)&0x0f00) | ((rx_status<<4)&0x00ff)",
           "mapped_bits": "rx[0..3]->reg44[4..7]; rx[5..8]->reg44[8..11]",
           "hook_poll": "reg44[7] <- rx_status[3] (Linux-side only)",
           "raw_dma_position": "logical slot != raw DMA index; physical wire order UNKNOWN"}}


def ctrl_word(reg48, reg2c, special=0):
    if special:
        return (special | 0x8000) & 0xffff
    return (0x4000 | ((reg48 >> 3) & 0x1e0) | ((reg48 >> 4) & 0xf)
            | (0x10 if reg2c & (1 << 17) else 0)
            | (0x200 if reg2c & (1 << 18) else 0))


def rx_reg44(status):
    if status & 0x8000:
        return None
    return 0x00020008 | ((status << 3) & 0xf00) | ((status << 4) & 0xff)


def classify_consumer(source_proven, control_bits_proven, effect_proven,
                      *, physical_mapping_proven=False):
    if not (source_proven and control_bits_proven and effect_proven):
        return "PCM_CONTROL_CANDIDATE" if control_bits_proven and effect_proven else "UNRESOLVED"
    return "FON_SLOT5_CONSUMER_PROVEN" if physical_mapping_proven else "PCM_CONTROL_CANDIDATE"


def base(name):
    return dict(image=name, firmware_sha256=A.REFERENCE_SHA[name],
        analysis_status="CONVERGED_BOUNDED_PATHS", instruction_provenance=[],
        cfg_evidence={}, dataflow_evidence={},
        related_device_evidence={"SC14480/SC14CVMDECT": "RELATED_DEVICE_HYPOTHESIS"},
        confidence="UNRESOLVED", unresolved_paths=[])


def cite(fw, addr):
    return DIP.cite(fw, addr)


def candidate_row(fw, row):
    address = int(row["effective_address"], 16)
    return dict(architectural_address=row["effective_address"],
        reference_device_name=REFERENCE_HINTS.get(address, "UNIDENTIFIED"),
        reference_status="RELATED_DEVICE_CANDIDATE" if address in REFERENCE_HINTS else "UNRESOLVED",
        operation=row["operation"], width_bits=row["width_bits"],
        instruction=cite(fw, int(row["instruction"], 16)),
        address_provenance=row["provenance"],
        value_expression="UNKNOWN_FOR_READ" if row["operation"] == "READ" else "UNRESOLVED",
        caller_or_irq_context="UNRESOLVED", confidence="ADDRESS_ONLY")


def immediate_sites(fw, value):
    # Disassembly is only a *candidate index*: a hit is never a source/sink.
    token = f"$0x{value:x}:"
    return [cite(fw, a) for a, i in sorted(fw.insns.items())
            if token in i.operands]


def direct_callers(edges, target):
    return sorted(e.src for e in edges if e.kind == "call" and
                  e.dst == target and e.category == C.DIRECT_RESOLVED)


def gpio_path(fw, name):
    """Bounded RAM-bit to GPIO-RMW chain; never label as analog FON."""
    sites = GPIO_PATHS[name]
    p = fw.insns
    first = p[sites[0]]
    base_insn = p[sites[1]] if name == "normal" else first
    if (first.mnemonic != "movd" or
        base_insn.operands != "$0xff4860:l," + (
            "(r3,r2)" if name == "normal" else "(r1,r0)")):
        raise ValueError(f"{name}: GPIO candidate base changed")
    if name == "normal":
        links = ((0x2802c, 0x28032), (0x28036, 0x2803c),
                 (0x28046, 0x2804c))
        inputs = ("0x00010e42[0,4]", "0x00ff4860[6]")
    else:
        links = ((0x3ce4, 0x3cea), (0x3cf6, 0x3cfc))
        inputs = ("0x00010e36[0]", "0x00ff4860[6]")
    if not all(DIP.edge(fw, src, dst) for src, dst in links):
        raise ValueError(f"{name}: GPIO conditional targets changed")
    if not all(p[a].mnemonic in ("sbitw", "cbitw") for a in sites
               if a in ((0x2802e, 0x28032, 0x28038, 0x2803c,
                         0x28048, 0x2804c) if name == "normal" else
                        (0x3ce6, 0x3cea, 0x3cec, 0x3cf8, 0x3cfc))):
        raise ValueError(f"{name}: GPIO output instructions changed")
    return {"function_candidate": f"0x{sites[0]:06x}",
        "input_provenance": inputs,
        "output_effects": "RMW bits 5/7 at architectural 0x00ff4860; RAM status bit3",
        "instruction_provenance": [cite(fw, a) for a in sites],
        "cfg_branch_edges": [[f"0x{a:06x}", f"0x{b:06x}"] for a, b in links],
        "linux_slot5_input": "UNPROVEN", "FON_meaning": "UNPROVEN",
        "reference_hint": "SC14CVMDECT P3_DATA_REG, RELATED_DEVICE_HYPOTHESIS",
        "confidence": "PROVEN_UNDER_CFG_MODEL for local RAM-bit/GPIO effects only"}


def analyze_image(name, fw, rows):
    edges = C.build(fw)
    resolved = [r for r in rows if r["address_kind"] == "RESOLVED" and
                r["effective_address"] and (
                    r["effective_address"].startswith("0x00ff") or
                    r["effective_address"].startswith("0x01027f"))]
    # These are architectural-address windows, NOT confirmed peripherals;
    # dataflow unknowns are counted rather than treated as absence.
    registers = defaultdict(list)
    for r in resolved:
        registers[r["effective_address"]].append(candidate_row(fw, r))
    inventory = base(name) | dict(
        instruction_provenance=[r["instruction"] for r in resolved
            if r["operation"] == "READ"],
        cfg_evidence={"caller_or_irq_context": "NOT_RESOLVED_GLOBAL"},
        dataflow_evidence={"resolved_address_operations": dict(sorted(registers.items())),
            "address_window_is_peripheral": "UNPROVEN_FOR_SC14448",
            "resolved_read_count": sum(r["operation"] == "READ" for r in resolved),
            "unresolved_memory_accesses": sum(r["address_kind"] in
                ("UNKNOWN", "INDEXED") for r in rows),
            "reference_pcm_in_addresses": [f"0x{x:08x}" for x in
                (0x01027FAE, 0x01027FB0, 0x01027FB2, 0x01027FB4)],
            "resolved_reads_of_reference_pcm_in": [r["effective_address"]
                for r in resolved if r["operation"] == "READ" and
                int(r["effective_address"], 16) in REFERENCE_HINTS and
                int(r["effective_address"], 16) in range(0x01027FAE, 0x01027FB6, 2)]},
        unresolved_paths=["register-pair indirect/DMA/FIFO ingress not exhausted",
            "reference-device register naming is not SC14448 identification",
            "caller/IRQ context and PCM physical transport unknown"])
    # Keep the exact operations around a small evidence-led set of addresses,
    # rather than claiming one register is a proven PCM source.
    shortlist = (0x00FF4858, 0x00FF4868, 0x00FF6006,
                 0x01027FAE, 0x01027FB0, 0x01027FB2, 0x01027FB4)
    short_rows = [candidate_row(fw, r) for r in resolved
                  if int(r["effective_address"], 16) in shortlist]
    ingress = base(name) | dict(
        instruction_provenance=[x["instruction"] for x in short_rows],
        cfg_evidence={"source_to_firmware_consumer": False,
            "physical_pcm_slot_to_SC14448_ingress": "UNKNOWN"},
        dataflow_evidence={"candidate_register_accesses": short_rows,
            "read_value_to_control_word_bits": "NOT_ESTABLISHED",
            "linux_side_logical_control": LINUX,
            "raw_dma_word_is_not_physical_slot": True},
        unresolved_paths=["no verified slot-5 hardware-to-peripheral mapping",
            "no read-to-control-consumer def-use chain",
            "indirect and hardware-populated memory sources not excluded"])
    mask_hits = {f"0x{x:04x}": immediate_sites(fw, x)
                 for x in (0x4000, 0x8000)}
    consumers = base(name) | dict(
        instruction_provenance=mask_hits["0x4000"] + mask_hits["0x8000"] +
            gpio_path(fw, name)["instruction_provenance"],
        cfg_evidence={"matched_immediate_is_not_consumer": True,
            "slot5_source_to_sink": False},
        dataflow_evidence={"literal_hits_only": mask_hits,
            "normal_control_formula": LINUX["normal"],
            "special_control_formula": LINUX["special"],
            "decoded_word_consumer": None,
            "bounded_gpio_state_path_not_proven_FON": gpio_path(fw, name)},
        unresolved_paths=["matched constants can be address arithmetic or unrelated flags",
            "no proven PCM input to decode/branch to analog side-effect chain"])
    status = base(name) | dict(instruction_provenance=[],
        cfg_evidence={"firmware_status_to_linux_rx": False},
        dataflow_evidence={"linux_RX": LINUX["rx"],
            "firmware_status_producer": None, "source_peripheral": None},
        unresolved_paths=["SC14448 status source and output peripheral unknown",
            "firmware status -> physical slot -> Linux rx_status not reconstructed"])
    dip_site = P.SITES[name]["word_begin"]
    dip_calls = []
    for addr in direct_callers(edges, dip_site):
        dip_calls.append({"instruction": cite(fw, addr),
            "callee": f"0x{dip_site:06x}",
            "classification": "UNKNOWN",
            "reason": "direct call proves only writer reachability; upstream DECT/DSP/PCM source unresolved"})
    dip = base(name) | dict(instruction_provenance=[c["instruction"] for c in dip_calls],
        cfg_evidence={"direct_caller_edges": dip_calls,
            "fill_writer": f"0x{DIP.SITES[name]['store']:06x}",
            "restore_writer": f"0x{P.SITES[name]['restore']:06x}"},
        dataflow_evidence={"known_selected_word_index_2": "0x12aa",
            "other_caller_bytes": "UNRESOLVED", "reason_for_index_2": "UNRESOLVED"},
        unresolved_paths=["most caller inputs and entry context unknown",
            "no DECT-only or PCM-linked classification established"])
    # Only indirect sites near a firmware register *read* are triaged;
    # proximity is not caller connectivity or target resolution.
    read_addrs = [int(r["instruction"], 16) for r in resolved
                  if r["operation"] == "READ" and int(r["instruction"], 16) < 0x30000]
    nearby = [cite(fw, a) for a, i in sorted(fw.insns.items())
              if (i.mnemonic == "jal" or
                  (i.mnemonic in ("jump", "jmp") and i.operands != "(ra)")) and
              any(abs(a - x) <= 32 for x in read_addrs)]
    indirect = base(name) | dict(instruction_provenance=nearby,
        cfg_evidence={"proximity_only_indirect_sites": nearby,
            "resolved_target_chains": []},
        dataflow_evidence={"distance_bytes": 32,
            "proximity_is_not_source_to_target_propagation": True},
        unresolved_paths=["target producer/table/stack/endianness unresolved",
            "nearby read not proven to feed indirect call"])
    boundaries = base(name) | dict(
        instruction_provenance=[c["instruction"] for c in short_rows],
        cfg_evidence={"linux_logical_slot5": "PROVEN_BY_LINUX_OEM",
            "physical_transport": "UNKNOWN", "SC14448_ingress": "UNKNOWN",
            "firmware_dataflow_to_analog_FON": "UNKNOWN",
            "FON_SLOT5_CONSUMER_PROVEN": False},
        dataflow_evidence={"closest_evidence": "resolved peripheral accesses only",
            "absence_claim_scope": "no source-to-sink proof among enumerated candidates",
            "primary_missing_transition": "Linux logical slot 5 -> SC14448 physical receiver/register"},
        unresolved_paths=["physical wiring/slot alignment unknown",
            "SC14448 PCM input register not identified",
            "indirect/DMA ingress and downstream FON state not traced"])
    return inventory, ingress, consumers, status, dip, indirect, boundaries


def build(objdump):
    A._validate_inputs(objdump)
    for label, (path, expected) in OEM_SHA.items():
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"missing or SHA256-mismatched Linux OEM source: {label}")
    outputs = [dict() for _ in FILES]
    for name, path in A.IMAGES:
        df, fw, rows = D.run_image(name, path, objdump)
        if df.get("converged") is not True or df.get("analysis_status") != "CONVERGED":
            raise ValueError(f"{name}: NON_CONVERGED")
        for out, record in zip(outputs, analyze_image(name, fw, rows)):
            out[name] = record
    if any(set(o) != set(A.REFERENCE_SHA) for o in outputs):
        raise ValueError("incomplete E3.5 report bundle")
    return {fn: {"tool": "cr16-pcm-ingress/1",
                 "linux_oem_sha256": {k: v[1] for k, v in OEM_SHA.items()},
                 "images": o}
            for fn, o in zip(FILES, outputs)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--objdump", default=str(A.OBJDUMP))
    ap.add_argument("--out", default=str(ROOT / "tools" / "reports"))
    args = ap.parse_args(argv)
    try:
        DIP.publish(Path(args.out), build(args.objdump))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        Path(args.out).mkdir(parents=True, exist_ok=True)
        (Path(args.out) / "cr16-e35.incomplete.json").write_text(json.dumps(
            {"analysis_status": "INCOMPLETE", "reason": str(exc)}, indent=1) + "\n")
        print(f"INCOMPLETE E3.5: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
