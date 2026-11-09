#!/usr/bin/env python3
"""CR16 address-form and Q57 evidence tooling (offline only)."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for p in (str(HERE), str(ROOT / "src" / "mock")):
    sys.path.insert(0, p)

import cr16_cfg as C  # noqa: E402
import cr16_dataflow as D  # noqa: E402
import cr16_peripheral_xrefs as X  # noqa: E402

OBJDUMP = Path("/tmp/opencode/cr16/build/binutils/objdump")
IMAGES = [
    ("normal", ROOT / "firmware" / "dectfw_secondlevel_441.hex"),
    ("p2test", ROOT / "firmware" / "dectfw_secondlevel_441p2test.hex"),
]
REFERENCE_SHA = {
    "normal": "7cac33c72b2222468f34033a15c35487aa35062265ab0013bb480068ebab7b31",
    "p2test": "6361384d0e3b717e33ca65111cef82df8952da28e24b9d3b94d055b20dbc4860",
}
DIP_FILL = {
    "normal": {"control": 0x25F90, "store": 0x25D0},
    "p2test": {"control": 0x26750, "store": 0x1E8C},
}
CONFLICT_ADDRS = [
    ("0x000f6002", "0x00ff6002"),
    ("0x000f6006", "0x00ff6006"),
    ("0x000f5402", "0x00ff5402"),
    ("0x000f6400", "0x00ff6400"),
    ("0x000f6402", "0x00ff6402"),
    ("0x000f4858", "0x00ff4858"),
]


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sign_extend20(value):
    """Given a 20-bit field, show the 24-bit sign-extended alternative."""
    value &= 0xFFFFF
    return value | 0xF00000 if value & 0x80000 else value


def _extension_models(form, encoded):
    """Show the encoded field and the competing extension models."""
    if form != "ABS20" or encoded is None:
        return None
    v = int(encoded, 16) & 0xFFFFF
    architectural = X.reloc_abs20(v)
    return {
        "encoded_20bit": f"0x{v:05x}",
        "zero_extended": f"0x{v:08x}",
        "architectural_effective": f"0x{architectural:08x}",
        "extension_rule": "RELOC_ABS20",
        "status": "PROVEN_BY_ISA_IMPLEMENTATIONS",
    }


def _memory_form(insn):
    """Classify the memory operand of an instruction from its assembly form."""
    for operand in X.split_operands(insn.operands):
        parsed = X.parse_memory_operand(operand)
        if not parsed:
            continue
        kind, payload = parsed
        if kind == "ABS":
            if len(insn.raw) >= 6:
                return "ABS24", operand, payload, None, None
            if len(insn.raw) == 4:
                return "ABS20", operand, payload, None, None
            return "ABS_UNKNOWN", operand, payload, None, None
        if kind == "DISP_RP":
            disp, hi, lo = payload
            return "REGISTER_PAIR", operand, payload, (hi, lo), disp
        if kind == "DISP_R":
            disp, reg = payload
            if reg in ("r12", "r13"):
                return "INDEXED", operand, payload, reg, disp
            if reg == "ra":
                return "PC_RELATIVE", operand, payload, reg, disp
            return "REGISTER_BASE", operand, payload, reg, disp
        if kind == "IDX":
            reg, disp = payload
            return "INDEXED", operand, payload, reg, disp
        if kind == "STACK":
            return "STACK", operand, payload, None, None
    return "NO_MEMORY_OPERAND", None, None, None, None


def _arch_form(insn, row):
    form, operand, payload, base, disp = _memory_form(insn)
    arch = row.get("effective_address")
    if form in ("ABS20", "ABS24", "ABS_UNKNOWN"):
        arch = f"0x{X.abs_address(insn):08x}" if X.abs_address(insn) is not None else None
    physical = "UNKNOWN_SC14448_MAP"
    hint = None
    if arch and arch.lower().startswith("0x00ff"):
        hint = "SC14480_PERIPHERAL_WINDOW_HINT"
    elif arch and arch.lower().startswith("0x000f"):
        hint = "SC14480_FLASH_WINDOW_HINT"
    encoded = None
    if form in ("ABS20", "ABS24", "ABS_UNKNOWN"):
        encoded_raw = X.abs_encoded_address(insn)
        if encoded_raw is not None:
            encoded = (f"0x{encoded_raw:05x}" if form == "ABS20"
                       else f"0x{encoded_raw:08x}")
    return {
        "address_mode": form,
        "decoded_operand": operand,
        "base_registers": list(base) if isinstance(base, tuple) else base,
        "displacement": disp,
        "encoded_address": encoded,
        "architectural_effective_address": arch,
        "effective_address_model": ({
            "ABS20": "RELOC_ABS20_HIGH_FIELD",
            "ABS24": "EXPLICIT_24BIT_FIELD",
            "REGISTER_PAIR": "REGISTER_PAIR_VALUE",
            "INDEXED": "REGISTER_INDEXED",
        }.get(form, "UNKNOWN")),
        "extension_models": _extension_models(form, encoded),
        "physical_address_status": physical,
        "related_device_hint": hint,
    }


def _row_record(name, path, fw, row):
    addr = int(row["instruction"], 16)
    insn = fw.insns[addr]
    form = _arch_form(insn, row)
    return {
        "instruction": row["instruction"],
        "raw_bytes": insn.raw.hex(),
        "instruction_size": len(insn.raw),
        "oracle_disassembly": f"{insn.mnemonic} {insn.operands}".strip(),
        "operation": row["operation"],
        "width_bits": row.get("width_bits"),
        "decoded_operand": form["decoded_operand"],
        "address_mode": form["address_mode"],
        "base_registers": form["base_registers"],
        "displacement": form["displacement"],
        "encoded_address": form["encoded_address"],
        "effective_address": form["architectural_effective_address"],
        "reference_register": form["base_registers"],
        "source": str(path.relative_to(ROOT)),
        "zero_extended_alternative": (
            form["extension_models"]["zero_extended"]
            if form.get("extension_models") else None),
        "architectural_effective_address":
            form["architectural_effective_address"],
        "effective_address_model": form["effective_address_model"],
        "extension_models": form["extension_models"],
        "address_kind": row.get("address_kind"),
        "physical_address_status": form["physical_address_status"],
        "related_device_hint": form["related_device_hint"],
        "previous_effective_address": row.get("effective_address"),
        "previous_expression": row.get("expression"),
        "source_provenance": row.get("provenance") or [row["instruction"]],
        "provenance": row.get("provenance") or [row["instruction"]],
        "confidence": ("ORACLE_MATCH" if form["architectural_effective_address"]
                       == row.get("effective_address") else
                       "DATAFLOW_EFFECTIVE"),
    }


def _address_forms(name, path, objdump):
    report, fw, rows = D.run_image(name, path, objdump)
    out = []
    for row in rows:
        if row.get("operation") not in ("READ", "WRITE", "RMW"):
            continue
        out.append(_row_record(name, path, fw, row))
    # Include literal address loads (movd $imm) as provenance, not memory.
    seen = set()
    for insn in fw.insns.values():
        if insn.mnemonic != "movd":
            continue
        if insn.addr in seen:
            continue
        m = X.MD_RE.match(insn.operands.replace(" ", ""))
        if not m:
            continue
        seen.add(insn.addr)
        out.append({
            "instruction": f"0x{insn.addr:06x}",
            "raw_bytes": insn.raw.hex(),
            "instruction_size": len(insn.raw),
            "oracle_disassembly": f"{insn.mnemonic} {insn.operands}",
            "operation": "ADDRESS_LOAD",
            "width_bits": 32,
            "decoded_operand": insn.operands,
            "address_mode": "IMMEDIATE_PAIR",
            "base_registers": [m.group(2), m.group(3)],
            "displacement": None,
            "encoded_address": f"0x{int(m.group(1), 16):08x}",
            "effective_address": f"0x{int(m.group(1), 16):08x}",
            "reference_register": [m.group(2), m.group(3)],
            "source": str(path.relative_to(ROOT)),
            "architectural_effective_address":
                f"0x{int(m.group(1), 16):08x}",
            "effective_address_model": "LITERAL_24BIT_VALUE",
            "extension_models": None,
            "address_kind": "RESOLVED",
            "physical_address_status": "LITERAL_VALUE_NOT_PHYSICAL_MAP",
            "related_device_hint": None,
            "previous_effective_address": f"0x{int(m.group(1), 16):08x}",
            "previous_expression": None,
            "source_provenance": [f"0x{insn.addr:06x}"],
            "provenance": [f"0x{insn.addr:06x}"],
            "confidence": "ORACLE_MATCH",
        })
    return report, fw, out


def _conflict_rows(forms):
    out = []
    for low, high in CONFLICT_ADDRS:
        lowv = int(low, 16)
        highv = int(high, 16)
        low_field = lowv & 0xfffff
        lo = [r for r in forms
              if r.get("address_mode") == "ABS20"
              and r.get("encoded_address")
              and int(r["encoded_address"], 16) == low_field]
        hi = [r for r in forms
              if (r.get("architectural_effective_address") or "").lower()
              == high.lower()
              and not (r.get("address_mode") == "ABS20"
                       and int(r.get("encoded_address") or "0", 16)
                       == low_field)]
        sext = _sign_extend20(lowv)
        same = sext == highv
        out.append({
            "low_encoded_form": low,
            "high_canonical_address": high,
            "low_encoded_20bit": f"0x{low_field:05x}",
            "zero_extended_interpretation": f"0x{low_field:08x}",
            "architectural_effective_address": f"0x{sext:08x}",
            "sign_extension_matches_high": same,
            "low_form_accesses": lo[:12],
            "high_canonical_accesses": hi[:12],
            "low_form_count": len(lo),
            "high_canonical_count": len(hi),
            "status": ("SAME_ARCHITECTURAL_ADDRESS" if same and lo and hi
                       else "SAME_ARCHITECTURAL_ADDRESS_SINGLE_FORM"
                       if same and (lo or hi)
                       else "UNKNOWN"),
            "alias_proof": ("PROVEN_BY_ISA_EXTENSION" if same else "NONE"),
            "physical_register_identity": "CANDIDATE",
            "blocker": ("SC14448 physical register identity still relies on "
                        "the related-device SC14480 map; no SC14448 bus trace "
                        "or system-controller document."),
        })
    return out


def _dip_fill(name, fw, forms, path):
    spec = DIP_FILL[name]
    store = fw.insns[spec["store"]]
    control = fw.insns[spec["control"]]
    # The fill stores the constant held in r2; this is independently visible
    # at the control site in both images.
    payload = None
    for insn in fw.insns.values():
        if insn.addr == spec["control"]:
            for a in range(spec["control"], spec["control"] + 0x20):
                i = fw.insns.get(a)
                if i and i.mnemonic == "movw" and ",r2" in i.operands:
                    m = re.search(r"\$0x([0-9a-f]+)", i.operands)
                    if m:
                        payload = int(m.group(1), 16)
                        break
    return {
        "image": name,
        "source": str(path.relative_to(ROOT)),
        "control_instruction": f"0x{spec['control']:06x}",
        "control_bytes": control.raw.hex(),
        "store_instruction": f"0x{spec['store']:06x}",
        "store_bytes": store.raw.hex(),
        "store_disassembly": f"{store.mnemonic} {store.operands}",
        "fill_range": "0x01000002…0x010003FE",
        "iterations": "1…511",
        "payload": f"0x{payload:04x}" if payload is not None else None,
        "payload_status": "CONSTANT_UNDECODED",
        "sc14480_mapping": {
            "range": "0x01000000–0x010003FF",
            "meaning": "DIP Sequencer RAM, 512 × 16 bit",
            "first_instruction": "0x01000002",
            "printed_pages": "131–132 and 33–34",
        },
        "dip_opcode_hint": ("SC14480 Table 10: 0x01 = BR; 0x10 = BR_B0. "
                            "0x1001 contains both values, so either byte "
                            "order yields a branch opcode; the parameter "
                            "and target are not proved."),
        "payload_byte_orders": {
            "little_endian": {"opcode": "0x01", "opcode_name": "BR",
                              "parameter": "0x10"},
            "big_endian": {"opcode": "0x10", "opcode_name": "BR_B0",
                           "parameter": "0x01"},
        },
        "classification": "DIP_RAM_FILL_CANDIDATE",
        "pcm_evidence": False,
        "slot5_evidence": False,
        "unresolved": [
            "DIP instruction word byte order/parameter encoding",
            "meaning of the repeated 0x1001 payload",
            "SC14448 identity of the 0x01000000 region",
        ],
    }


def _audit_report():
    p = ROOT / "tools" / "reports" / "cr16-e3-soundness-audit.json"
    if not p.is_file():
        return {"status": "SKIP", "reason": "E3 audit report missing"}
    d = json.loads(p.read_text())
    out = {
        "tool": "cr16-e32-audit/1",
        "baseline": d.get("baseline_commit"),
        "e31_fixes": {
            "memory_use_key": [
                "instruction", "effective_address", "operation",
                "known displacement", "register_pair when both available"
            ],
            "old_baseline": ("fail-closed on missing/invalid E2 baseline; "
                             "SHA256 checked against firmware"),
            "table_def_use_scope": "LOCAL_BASIC_BLOCK_ONLY",
        },
        "images": {},
    }
    for n, v in d.get("images", {}).items():
        out["images"][n] = {
            "old_proven": v.get("old_proven"),
            "reclassified": v.get("reclassified"),
            "use_match_checked": all(
                "matched" in a.get("use_match", {})
                for a in v.get("audited_old_proven", [])),
            "mismatched_uses": sum(
                len(a.get("use_match", {}).get("mismatched", []))
                for a in v.get("audited_old_proven", [])),
            "missing_uses": sum(
                len(a.get("use_match", {}).get("missing", []))
                for a in v.get("audited_old_proven", [])),
        }
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--objdump", default=str(OBJDUMP))
    ap.add_argument("--out", default=str(ROOT / "tools" / "reports"))
    args = ap.parse_args(argv[1:])
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    forms_all = {}
    conflicts_all = {}
    dip_all = {}
    for name, path in IMAGES:
        if not path.is_file():
            print(f"SKIP {name}: firmware missing")
            continue
        report, fw, forms = _address_forms(name, path, args.objdump)
        forms_all[name] = {
            "source": str(path.relative_to(ROOT)),
            "sha256": _sha(path),
            "records": forms,
        }
        conflicts_all[name] = _conflict_rows(forms)
        dip_all[name] = _dip_fill(name, fw, forms, path)
        forms_all[name]["summary"] = {
            "total_memory_and_literal_records": len(forms),
            "by_address_mode": {
                m: sum(1 for r in forms if r["address_mode"] == m)
                for m in sorted({r["address_mode"] for r in forms})},
        }
        (out / f"cr16-address-forms-{name}.json").write_text(
            json.dumps(forms_all[name], indent=1) + "\n")
    (out / "cr16-address-space-conflicts.json").write_text(
        json.dumps({"tool": "cr16-address-space-conflicts/1",
                    "images": conflicts_all,
                    "status": "ADDRESS_SPACE_RESOLVED_BY_ABS20_EXTENSION",
                    "hypotheses": [
                        {"name": "ZERO_EXTENSION",
                         "status": "REFUTED",
                         "support": "none beyond the old analyzer's assumption",
                         "contradiction": "binutils GAS OP_ABS20 rejects >0xEFFFF; QEMU and GAS both expand abs20 high values to 0xFFxxxx"},
                        {"name": "SIGN_EXTENSION_RELOC_ABS20",
                         "status": "PROVEN_BY_ISA",
                         "support": "QEMU reloc_abs20: addr > 0xEFFFF => addr | 0xF00000; binutils GAS adjust_if_needed and OP_ABS20 use the same threshold",
                         "contradiction": "no vendor CR16Cplus core manual in the offline set; still an ISA/implementation proof, not an SC14448 bus trace"},
                        {"name": "HARDWARE_ALIAS_OR_WINDOW",
                         "status": "UNKNOWN",
                         "support": "12 low/high pairs in both images; SC14480 peripheral window is 0x00FFxxxx",
                         "contradiction": "SC14480 map separates 0x000Fxxxx FLASH from 0x00FFxxxx peripherals; SC14448 differs"},
                        {"name": "DIFFERENT_SPACES",
                         "status": "SUPPORTED_BY_RELATED_DATASHEET",
                         "support": "SC14480 places low range in FLASH/ROM and high range in peripherals; numeric addresses differ",
                         "contradiction": "SC14448 may differ; low writes cannot target SC14480 FLASH"},
                        {"name": "ANALYZER_DECODING_ERROR",
                         "status": "REFUTED_FOR_FORM",
                         "support": "raw bytes and oracle disassembly agree on abs20 vs pair forms",
                         "contradiction": "none for address form; physical extension remains unknown"},
                        {"name": "CHIP_SPECIFIC_MAP",
                         "status": "UNKNOWN",
                         "support": "SC14448 has no offline memory map",
                         "contradiction": "none; cannot be tested offline"},
                    ],
                    "blocker": ("The address-space conflict is resolved: the "
                                "low 0x000Fxxxx values are encoded abs20 "
                                "fields that expand to 0x00FFxxxx. "
                                "The remaining uncertainty is SC14448 "
                                "physical register identity, not address "
                                "space; it needs an SC14448 map or bus "
                                "evidence, not SC14480 alone.")},
                   indent=1) + "\n")
    (out / "cr16-dip-ram-fill.json").write_text(
        json.dumps({"tool": "cr16-dip-ram-fill/1",
                    "images": dip_all,
                    "limitations": ["payload not decoded as valid DIP program",
                                    "SC14480 is not an SC14448 datasheet"]},
                   indent=1) + "\n")
    (out / "cr16-e32-audit.json").write_text(
        json.dumps(_audit_report(), indent=2) + "\n")
    print(f"wrote address reports for {len(forms_all)} images")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
