#!/usr/bin/env python3
"""E5 audio-architecture tests: synthetic gates, fail-closed replay, rollback.

Run: python3 tools/tests/test_cr16_audio_architecture.py
The firmware/oracle parts SKIP when the two images or the CR16 objdump are
missing; everything else runs offline.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import cr16_address_spaces as A          # noqa: E402
import cr16_audio_architecture as E      # noqa: E402
import cr16_cfg as C                     # noqa: E402

fails = skips = 0


def ck(label, got, want):
    global fails
    if got == want:
        print("PASS " + label)
    else:
        print(f"FAIL {label}: got {str(got)[:120]!r} want {str(want)[:120]!r}")
        fails += 1


def skip(label, why):
    global skips
    print(f"SKIP {label}: {why}")
    skips += 1


def synfw():
    """Firmware with [0xD6] = 0x01027F80 and a DSP block at 0x17300."""
    fw = C.Firmware([(0x0, bytes(0x200)), (0x17300, bytes(0x40))])
    data = bytearray(fw.runs[0][1])
    data[0xD6:0xDA] = bytes.fromhex("807f0201")
    fw.runs[0] = (0x0, bytes(data))
    return fw


# ---------------------------------------------------------------------------
# pure functions
# ---------------------------------------------------------------------------
print("== transforms and classification")
ck("pc word normal", E.dsp_pc_word(0x17300), 0x7980)
ck("pc word base", E.dsp_pc_word(0x0), 0xC000)
ck("pc word wraps", E.dsp_pc_word(0x8000), 0x0000)
ck("data word", E.dsp_data_word(0x10000), 0x0000)
ck("data word flash", E.dsp_data_word(0x0), 0x8000)
ck("base cell from image", E.image_base(synfw()), 0x01027F80)
ck("compose pcm A/B", E.compose_pcm_ctrl(E.PCM_PATH_A, E.PCM_PATH_B),
   (0x0043, 0x0045))
ck("decode sync1 fields", E.decode_fields(0x0000,
   E.SC14480["main_sync1_fields"])[0]["value"], "0x000")
ck("decode dsp_ctrl 0xc", [f["field"] for f in E.decode_fields(
   0x000C, E.SC14480["dsp_ctrl_bits"])],
   ["DSP_EN", "DSP_CLK_EN", "DSP_CR16_INT", "DBG_EN"])

print("== program-source classification")
ck("not in image", E.classify_program_source(
    run_present=False, run_start=0, run_end=0, pc_value=0,
    copy_loop_found=False, rom_literal_sites=[])[0],
   "DSP_PROGRAM_NOT_IN_IMAGE")
ck("empty run", E.classify_program_source(
    run_present=True, run_start=0x100, run_end=0x100, pc_value=0,
    copy_loop_found=False, rom_literal_sites=[])[0],
   "DSP_PROGRAM_IMAGE_RUN_EMPTY")
ck("copy loop candidate", E.classify_program_source(
    run_present=True, run_start=0x100, run_end=0x140, pc_value=0,
    copy_loop_found=True, rom_literal_sites=[])[0].endswith(
        "COPY_LOOP_CANDIDATE"), True)
ck("even ROM-window literal", E.classify_program_source(
    run_present=True, run_start=0x100, run_end=0x140, pc_value=0,
    copy_loop_found=False, rom_literal_sites=["0x01044000"])[0].endswith(
        "ROM_WINDOW_CANDIDATE"), True)
ck("odd data pointer is not ROM", E.classify_program_source(
    run_present=True, run_start=0x100, run_end=0x140, pc_value=0,
    copy_loop_found=False, rom_literal_sites=["0x0104004d"])[0],
   "DSP_PROGRAM_EMBEDDED_IN_FIRMWARE_IMAGE")

print("== register-name discipline")
ck("0x01027FE4 unmapped", E.reg_reference(0x01027FE4)["reference_name"],
   "UNMAPPED_IN_SC14480_REFERENCE")
ck("0x00FF401C unmapped", E.reg_reference(0x00FF401C)["reference_name"],
   None)
for addr in (0x01027FD8, 0x00FF5800, 0x00FF6006):
    ref = E.reg_reference(addr)
    ck(f"0x{addr:08x} analogy only",
       ref["status"], "SC14480_ANALOGY_UNVERIFIED_SC14448")

REPORTS = ROOT / "tools" / "reports"
have_fw = A.OBJDUMP.is_file() and all(p.is_file() for _, p in A.IMAGES)
if not have_fw:
    skip("firmware/oracle", "images or CR16 objdump missing")
else:
    bundles = {}
    for fn in E.NAMES:
        path = REPORTS / fn
        if not path.is_file():
            skip("committed " + fn, "missing")
            continue
        bundles[fn] = json.loads(path.read_text())

    print("== committed report invariants")
    for fn, body in bundles.items():
        ck(f"{fn}: both images", set(body["images"]),
           {"normal", "p2test"})
        for name, img in body["images"].items():
            ck(f"{fn} {name}: sha", img["firmware_sha256"],
               A.REFERENCE_SHA[name])
            ck(f"{fn} {name}: converged", img["analysis_status"],
               "CONVERGED_BOUNDED_PATHS")
            ck(f"{fn} {name}: unresolved recorded",
               bool(img.get("unresolved_paths")), True)
            txt = json.dumps(img)
            ck(f"{fn} {name}: no HARDWARE level",
               "HARDWARE_CONFIRMED" in txt or
               "DOCUMENTED_ALIAS" in txt, False)
    regs = bundles["cr16-e5-dsp-registers.json"]["images"]
    for name, img in regs.items():
        helper = [a for a in img["instruction_provenance"]
                  if a["label"] == "helper_patch_call"]
        ck(f"{name}: indirect helper patch stays unresolved",
           bool(helper) and helper[0]["effective_address"] is None, True)
        pc = [a for a in img["instruction_provenance"]
              if a["label"] == "dsp_pc_store"]
        ck(f"{name}: pc start 0x7980",
           pc[0]["effective_address"], "0x01027fd4")
    pcm = bundles["cr16-e5-pcm-routing.json"]["images"]
    for name, img in pcm.items():
        ev = img["dataflow_evidence"]
        ck(f"{name}: pcm composed", ev["pcm_ctrl_path_a_composed"], "0x0043")
        ck(f"{name}: interface mismatch recorded",
           "1.024 MHz" in ev["interface_mismatch_with_linux"][0] and
           "4 PCM channels" in ev["interface_mismatch_with_linux"][1], True)
        ck(f"{name}: slot 5 not claimed as consumer",
           "slot 5" not in json.dumps(ev).lower(), True)
    codec = bundles["cr16-e5-codec-init.json"]["images"]
    for name, img in codec.items():
        ck(f"{name}: codec routing not over-claimed", any(
            "no proved audio routing" in u
            for u in img["unresolved_paths"]), True)
    clk = bundles["cr16-e5-clock-dependencies.json"]["images"]
    for name, img in clk.items():
        txt = json.dumps(img["dataflow_evidence"])
        ck(f"{name}: runtime verification required",
           "RUNTIME_VERIFICATION_REQUIRED" in txt, True)
        ck(f"{name}: DIP-sync analogy kept as analogy",
           "SC14480 analogy" in txt, True)
    prog = bundles["cr16-e5-dsp-program-source.json"]["images"]
    for name, img in prog.items():
        ev = img["dataflow_evidence"]
        ck(f"{name}: program source honest",
           ev["program_source_classification"].startswith(
               "DSP_PROGRAM_EMBEDDED_IN_FIRMWARE_IMAGE"), True)
        ck(f"{name}: execution mechanism unknown",
           "EXECUTION_MECHANISM_UNKNOWN" in img["confidence"], True)

    print("== fresh replay")
    with tempfile.TemporaryDirectory() as td:
        cmd = [sys.executable, str(ROOT / "tools" /
                                   "cr16_audio_architecture.py"),
               "--out", td]
        rc = subprocess.run(cmd, capture_output=True)
        ck("fresh run rc", rc.returncode, 0)
        for fn in E.NAMES:
            ck("complete " + fn, (Path(td) / fn).is_file(), True)
            if fn in bundles:
                ck("replay " + fn,
                   json.loads((Path(td) / fn).read_text()),
                   bundles[fn])

        sentinel = {fn: f"old {fn}\n".encode() for fn in E.NAMES}
        for fn, text in sentinel.items():
            (Path(td) / fn).write_bytes(text)
        # rollback: wrong SHA and NON_CONVERGED must fail without promoting
        with patch.object(A, "REFERENCE_SHA",
                          {"normal": "0" * 64, "p2test": "0" * 64}):
            rc = E.main(["--out", td])
        ck("SHA mismatch fails", rc, 1)
        ck("SHA mismatch preserves reports",
           {fn: (Path(td) / fn).read_bytes() for fn in E.NAMES}, sentinel)
        with patch.object(E.D, "run_image",
                          return_value=({"converged": False,
                                         "analysis_status": "NON_CONVERGED"},
                                        None, [])):
            rc = E.main(["--out", td])
        ck("NON_CONVERGED fails", rc, 1)
        ck("NON_CONVERGED preserves reports",
           {fn: (Path(td) / fn).read_bytes() for fn in E.NAMES}, sentinel)
        rc = E.main(["--out", td, "--objdump", td + "/absent-objdump"])
        ck("missing oracle fails", rc, 1)
        ck("missing oracle preserves reports",
           {fn: (Path(td) / fn).read_bytes() for fn in E.NAMES}, sentinel)
        ck("missing oracle diagnostic",
           bool(json.loads((Path(td) / "cr16-e5.incomplete.json")
                           .read_text())["reason"]), True)

print(f"\n{fails} failure(s), {skips} skip(s)")
raise SystemExit(bool(fails or skips))
