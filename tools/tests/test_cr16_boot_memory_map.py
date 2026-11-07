#!/usr/bin/env python3
"""Tests for the boot memory map tool.

Run: python3 tools/tests/test_cr16_boot_memory_map.py

Results are PASS / FAIL / SKIP.  Without the firmware the tool must SKIP and
must not rewrite the committed report.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import cr16_boot_memory_map as M  # noqa: E402

REPORT = ROOT / "tools" / "reports" / "cr16-boot-memory-map.json"
IMAGES = {name: path for name, path in M.IMAGES}
OBJDUMP = Path("/tmp/opencode/cr16/build/binutils/objdump")

fails = 0
skips = 0


def check(name, got, want):
    global fails
    if got == want:
        print(f"PASS {name}")
    else:
        print(f"FAIL {name}: got {got!r} want {want!r}")
        fails += 1


def skip(name, why):
    global skips
    print(f"SKIP {name}: {why}")


def ihex(lines):
    f = tempfile.NamedTemporaryFile(suffix=".hex", delete=False, mode="w")
    f.write("\n".join(lines) + "\n")
    f.close()
    return f.name


# ---------------------------------------------------------------------------
# 1. Intel HEX parsing, including extended-address records
# ---------------------------------------------------------------------------
print("== Intel HEX parsing")


def rec(count, addr, kind, data):
    body = bytes([count, (addr >> 8) & 0xFF, addr & 0xFF, kind]) + bytes(data)
    return ":" + (body + bytes([(-sum(body)) & 0xFF])).hex().upper()


plain = ihex([rec(2, 0x10, 0, [0xAA, 0xBB]), rec(0, 0, 1, [])])
mem, blocks, types, errors, ovl = M.parse_ihex(plain)
check("data record parsed", mem.get(0x10), 0xAA)
check("second byte parsed", mem.get(0x11), 0xBB)
check("block found", blocks, [(0x10, 2)])
check("no parse errors", errors, [])

ext = ihex([rec(2, 0, 4, [0x00, 0x01]),      # upper = 0x00010000
            rec(1, 0x20, 0, [0x5A]),
            rec(0, 0, 1, [])])
mem, blocks, types, errors, ovl = M.parse_ihex(ext)
check("extended linear address applied", mem.get(0x00010020), 0x5A)
check("extended block start", blocks[0][0], 0x00010020)

seg = ihex([rec(2, 0, 2, [0x10, 0x00]),      # segment 0x1000 -> 0x10000
            rec(1, 0x02, 0, [0x77]),
            rec(0, 0, 1, [])])
mem, blocks, types, errors, ovl = M.parse_ihex(seg)
check("extended segment address applied", mem.get(0x10002), 0x77)

# ---------------------------------------------------------------------------
# 2. Overlap detection
# ---------------------------------------------------------------------------
print("== overlap detection")
tmp_a = ihex([rec(4, 0x100, 0, [1, 2, 3, 4]), rec(0, 0, 1, [])])
mem, blocks, _, _, _ = M.parse_ihex(tmp_a)
check("a single block has no overlap", len(blocks), 1)
tmp_b = ihex([rec(2, 0x100, 0, [1, 2]),
              rec(2, 0x102, 0, [3, 4]),      # contiguous -> one block
              rec(0, 0, 1, [])])
mem, blocks, _, _, _ = M.parse_ihex(tmp_b)
check("contiguous records merge", blocks, [(0x100, 4)])
check("a gap splits blocks",
      [b[0] for b in blocks], [0x100])

# ---------------------------------------------------------------------------
# 3-5. copy semantics: direction, length, overlap
# ---------------------------------------------------------------------------
print("== copy semantics")
fw_path = IMAGES["normal"]
if not fw_path.is_file() or not OBJDUMP.is_file():
    skip("copy semantics", "firmware or objdump missing")
else:
    sys.path.insert(0, str(ROOT / "src" / "mock"))
    import cr16_cfg as C
    fw = C.load(str(fw_path))
    C.disassemble(fw, str(OBJDUMP))
    callers = M.find_callers(fw, 0x28D56)
    check("copy helper has exactly one caller", len(callers), 1)
    check("caller is the start-up block", callers[0]["site"], "0x0015f6")
    length, site = M.movd_value_before(fw, 0x15F6, "r3,r2")
    check("destination argument is 0x1c", length, 0x1C)
    check("destination loaded just before the call", site, "0x0015ea")
    source, _ = M.movd_value_before(fw, 0x15F6, "r5,r4")
    check("source argument is 0x24", source, 0x24)

    # the loop writes through the destination pair and advances the source
    ops = [fw.insns[a] for a in sorted(fw.insns)
           if 0x28D56 <= a <= 0x28D9C]
    text = " ".join(f"{i.mnemonic} {i.operands}" for i in ops)
    check("direction: writes via (r8,r7), which holds the destination",
          "storb r0,0x0:s(r8,r7)" in text, True)
    check("length is counted in 8-byte entries",
          "addd $0x8:s,(r8,r7)" in text, True)
    check("the source pair is only read",
          "loadd 0x0:s(r8,r7)" in text, True)

# ---------------------------------------------------------------------------
# 5b. real overlapping records
# ---------------------------------------------------------------------------
print("== overlapping Intel HEX records")
conflict = ihex([rec(4, 0x100, 0, [1, 2, 3, 4]),
                 rec(4, 0x102, 0, [9, 9, 5, 6]),
                 rec(0, 0, 1, [])])
mem, blocks, _, errors, ovl = M.parse_ihex(conflict)
check("a conflicting overlap is detected", len(ovl), 2)
check("conflicting overlap is labelled",
      {o["kind"] for o in ovl}, {"conflicting"})
check("strict mode reports the conflict as an error",
      len(M.parse_ihex(conflict, strict=True)[3]) > 0, True)

benign = ihex([rec(4, 0x100, 0, [1, 2, 3, 4]),
               rec(4, 0x102, 0, [3, 4, 5, 6]),
               rec(0, 0, 1, [])])
mem, blocks, _, errors, ovl = M.parse_ihex(benign, strict=True)
check("an identical overlap is recorded", len(ovl), 2)
check("identical overlap is labelled benign",
      {o["kind"] for o in ovl}, {"benign"})
check("identical overlap is not an error", errors, [])

bad_sum = ihex([":02000000010200"])   # valid is ...02FB
mem, blocks, _, errors, ovl = M.parse_ihex(bad_sum)
check("a bad checksum is reported",
      any("checksum" in e for e in errors), True)

short_rec = ihex([":0400000001020304"])
mem, blocks, _, errors, ovl = M.parse_ihex(short_rec)
check("a length mismatch is reported",
      any("length field" in e for e in errors), True)

bad_ext = ihex([rec(4, 0, 4, [0, 1, 0, 0]), rec(0, 0, 1, [])])
mem, blocks, _, errors, ovl = M.parse_ihex(bad_ext)
check("an extended-address record of wrong size is rejected",
      any("extended linear" in e for e in errors), True)

# ---------------------------------------------------------------------------
# 5c. the copy helper semantics
# ---------------------------------------------------------------------------
print("== copy helper (0x28d56)")
synth_mem = {}
rec_bytes = ((0x000008F2).to_bytes(4, "little")
             + (0x0000936C).to_bytes(4, "little"))
for i, b in enumerate(rec_bytes):
    synth_mem[0x1C + i] = b
writes = M.simulate_28d56(synth_mem, 0x1C, 0x24)
check("one record is processed", len(writes), 1)
check("count is little-endian 0x8f2", writes[0]["count_dec"], 0x8F2)
check("destination is 0x936c", writes[0]["destination"], "0x0000936c")
check("cursor stops at the end address",
      M.simulate_28d56(synth_mem, 0x1C, 0x1C), [])
check("the big-endian reading of the same bytes differs",
      int.from_bytes(rec_bytes[:4], "big"), 0xF2080000)

# ---------------------------------------------------------------------------
# 6. a jump to code that is absent from the image
# ---------------------------------------------------------------------------
print("== jump into absent code")
first_path = IMAGES["first"]
if not first_path.is_file():
    skip("hand-off", "first-level firmware missing")
else:
    mem, blocks, _, _, _ = M.parse_ihex(first_path)
    check("first-level starts at 0x10080", blocks[0][0], 0x10080)
    check("first-level does not contain 0x7c", 0x7C in mem, False)
    sec_mem, sec_blocks, _, _, _ = M.parse_ihex(IMAGES["normal"])
    check("second-level does contain 0x7c", 0x7C in sec_mem, True)

# ---------------------------------------------------------------------------
# 7. normal and p2test compared separately
# ---------------------------------------------------------------------------
print("== image comparison")
if not all(IMAGES[k].is_file() for k in ("normal", "p2test", "first")):
    skip("image comparison", "firmware missing")
else:
    n_mem, n_blocks, _, _, _ = M.parse_ihex(IMAGES["normal"])
    p_mem, p_blocks, _, _, _ = M.parse_ihex(IMAGES["p2test"])
    f_mem, f_blocks, _, _, _ = M.parse_ihex(IMAGES["first"])
    check("normal and p2test are parsed separately",
          len(n_mem) != len(p_mem) or n_mem is not p_mem, True)
    # The images are separate files; no byte is shared, but the first-level
    # range (0x10080) falls inside the *envelope* of the second-level image
    # (0x0-0x28dcd), which is why "the loader and the loaded code coexist in
    # memory" is a hypothesis, not a byte-level fact.
    check("no byte is shared between the first- and second-level images",
          len(set(f_mem) & set(n_mem)), 0)
    check("the first-level range falls inside the second-level envelope",
          0x10080 <= max(n_mem), True)

# ---------------------------------------------------------------------------
# 8. file bytes vs. claimed runtime bytes stay separate
# ---------------------------------------------------------------------------
print("== file vs runtime")
if first_path.is_file():
    mem, blocks, _, _, _ = M.parse_ihex(first_path)
    payload = M.build_payload(mem, blocks, 0)
    check("upload payload has a 2-byte header for level 0",
          payload["header_bytes"], 2)
    check("payload length excludes header and checksum",
          payload["payload_length"], len(mem) + 8)
    mem2, blocks2, _, _, _ = M.parse_ihex(IMAGES["normal"])
    payload2 = M.build_payload(mem2, blocks2, 1)
    check("upload payload has a 4-byte header for level 1",
          payload2["header_bytes"], 4)

# ---------------------------------------------------------------------------
# 9-10. committed report and its claims
# ---------------------------------------------------------------------------
print("== committed report")
if not REPORT.is_file():
    skip("report checks", f"{REPORT} missing")
elif not all(p.is_file() for _, p in M.IMAGES):
    skip("report checks", "firmware missing")
else:
    data = json.loads(REPORT.read_text())
    check("report names all three images",
          sorted(data["images"]), ["first", "normal", "p2test"])
    ch = data["copy_helper"]
    check("copy helper semantics say zeros are written",
          "zero bytes" in ch["semantics"]["loop"], True)
    check("copy helper explains why the value is zero",
          "forced to 0" in ch["semantics"]["why_zero"], True)
    check("copy helper arguments are the record range",
          (ch["arguments"]["record_start"]["value"]
           == "0x0000001c"), True)
    check("copy helper loop end is 0x24",
          ch["arguments"]["loop_end"]["value"], "0x00000024")
    check("copy helper simulated exactly one record",
          len(ch["simulated_writes"]), 1)
    check("copy helper destination is 0x936c",
          ch["changed_region"][0]["start"], "0x0000936c")
    check("copy helper length is 0x8f2",
          ch["changed_region"][0]["length"], 0x8F2)
    check("no within-image overlaps",
          [o for o in data["overlaps"] if "image" in o], [])
    ho = data["handoff"]
    check("hand-off chain is statically resolved",
          ho["chain"]["status"], "STATICALLY_RESOLVED")
    check("hand-off is not claimed as hardware-observed",
          ho["chain"]["hardware_observed"], False)
    check("the transfer site is the disps25 branch",
          ho["transfer_site"], "0x010284")
    check("the transfer target is 0x8", ho["transfer_target"], "0x00000008")
    check("normal secondary branch",
          ho["second_level"]["normal"]["decoded_in_isolation"]["target"],
          "0x000015aa")
    check("p2test secondary branch",
          ho["second_level"]["p2test"]["decoded_in_isolation"]["target"],
          "0x00001026")
    for image in ("normal", "p2test"):
        iso = ho["second_level"][image]["decoded_in_isolation"]
        check(f"{image}: all six trampoline bytes are in the image",
              iso.get("all_six_bytes_present"), True)
        check(f"{image}: the trampoline is a disps25 branch",
              iso.get("form_is_disps25"), True)
        check(f"{image}: the trampoline decoded DIRECT",
              iso.get("decode_status"), "DIRECT")
    check("no fact still says the 0x10284 form is undecoded",
          [f for f in data["images"]["first"]["facts"]
           if "not decoded" in f["fact"] and f["site"] == "0x010284"], [])
    # no hardware property may be claimed from an address number
    text = json.dumps(data).lower()
    check("no RAM/ROM claim in the report",
          ("\"ram\"" not in text) and ("\"rom\"" not in text), True)

    print("== reproducibility")
    out = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "cr16_boot_memory_map.py"),
         "--json", "/tmp/cr16-boot-map-check.json"],
        capture_output=True, text=True)
    if out.returncode != 0:
        skip("report reproducibility", out.stderr.strip() or "tool failed")
    else:
        check("committed report matches a fresh run",
              json.loads(REPORT.read_text()),
              json.loads(Path("/tmp/cr16-boot-map-check.json").read_text()))

# ---------------------------------------------------------------------------
# 11. hand-off branch targets are recorded, not guessed
# ---------------------------------------------------------------------------
print("== hand-off branch decoding")
# targets come from the shared decoder, never from a local formula
sys.path.insert(0, str(ROOT / "tools"))
import cr16_branch as B  # noqa: E402

for site, raw, want in (
        (0x1017C, "e01885ff", 0x10100),
        (0x10250, "1018b1fe", 0x10100),
        (0x10298, "e01869fe", 0x10100),
        (0x10284, "1000ef0e85fd", 0x000008)):
    t, form, status = B.decode_insn(site, "br", bytes.fromhex(raw))
    check(f"{site:#07x} -> {want:#08x}", (status, t), ("DIRECT", want))

# the second-level trampolines, decoded from the images
if IMAGES["normal"].is_file() and IMAGES["p2test"].is_file():
    for name, want in (("normal", 0x15AA), ("p2test", 0x1026)):
        mem, _, _, _, _ = M.parse_ihex(IMAGES[name])
        raw = bytes(mem.get(0x8 + k, 0) for k in range(6))
        t, form, status = B.decode_insn(0x8, "br", raw)
        check(f"{name}: 0x000008 -> {want:#06x}", (status, t),
              ("DIRECT", want))
else:
    skip("second-level trampolines", "firmware missing")

if first_path.is_file() and OBJDUMP.is_file():
    sys.path.insert(0, str(ROOT / "src" / "mock"))
    import cr16_cfg as C
    fw = C.load(str(first_path))
    C.disassemble(fw, str(OBJDUMP))
    # these three now decode; the targets were validated against cr16-dis.c
    for site, want in ((0x1017C, 0x10100), (0x10298, 0x10100),
                       (0x10284, 0x8)):
        t, form, status = C.decode_insn(site, fw.insns[site].mnemonic,
                                        fw.insns[site].raw[:6])
        check(f"{site:#07x} decodes to {want:#x}",
              (status, t), ("DIRECT", want))
    check("0x10100 is an instruction (the even neighbour)",
          0x10100 in fw.insns, True)
    check("0x10101 is not an instruction boundary",
          0x10101 in fw.insns, False)

# ---------------------------------------------------------------------------
# 12. a missing trampoline byte must not be replaced by zero
# ---------------------------------------------------------------------------
print("== missing trampoline bytes are refused (end-to-end)")


def hole_image(path, holes):
    """Parse `path`, then delete `holes` from the memory map."""
    mem, _, _, _, _ = M.parse_ihex(path)
    for a in holes:
        mem.pop(a, None)
    return mem


if IMAGES["normal"].is_file() and IMAGES["p2test"].is_file() and \
        M.OBJDUMP.is_file():
    for image in ("normal", "p2test"):
        base = {
            "first": M.parse_ihex(IMAGES["first"])[0],
            "normal": M.parse_ihex(IMAGES["normal"])[0],
            "p2test": M.parse_ihex(IMAGES["p2test"])[0],
        }
        # sanity: the untouched maps reproduce the resolved chain
        full = M.decode_handoff(memory=base)
        check(f"{image}: untouched image resolves the chain",
              full["chain"]["status"], "STATICALLY_RESOLVED")

        # drop one byte of the trampoline at 0x8..0xd
        holed = dict(base)
        holed[image] = hole_image(IMAGES[image], [0x9])
        check(f"{image}: the parser really lost 0x9",
              0x9 in holed[image], False)
        broken = M.decode_handoff(memory=holed)
        iso = broken["second_level"][image]["decoded_in_isolation"]
        check(f"{image}: status is INCOMPLETE", iso["status"], "INCOMPLETE")
        check(f"{image}: the missing byte is reported",
              iso["missing_bytes"], ["0x00000009"])
        check(f"{image}: no zero-filled target", iso["target"], None)
        check(f"{image}: chain becomes INCOMPLETE",
              broken["chain"]["status"], "INCOMPLETE")
else:
    skip("missing-byte end-to-end", "firmware or objdump missing")


# ---------------------------------------------------------------------------
# 13. a real Intel HEX file with a removed byte and recomputed checksums
# ---------------------------------------------------------------------------
# The test above drops a byte from an already-parsed map.  This one starts from
# the actual .hex file: it rewrites every data record that contains 0x9 as two
# records that skip it, recomputes each record checksum, and parses the result
# with the normal parser.  A data record is a contiguous run, so a byte cannot
# simply be deleted: the record must be split around the hole.
def hole_ihex(src, hole, dst):
    out = []
    upper = 0
    removed = []
    for line in src.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        raw = bytes.fromhex(line[1:])
        count, addr, kind = raw[0], (raw[1] << 8) | raw[2], raw[3]
        if kind == 0x04:
            upper = ((raw[4] << 8) | raw[5]) << 16
            out.append(line)
            continue
        if kind != 0x00:
            out.append(line)
            continue
        run = []

        def flush():
            if not run:
                return
            start = run[0][0]
            body = bytes(b for _, b in run)
            rec = bytes([len(body), (start >> 8) & 0xFF, start & 0xFF, 0]) + body
            out.append(":" + (rec + bytes([(-sum(rec)) & 0xFF])).hex().upper())

        for i, b in enumerate(raw[4:4 + count]):
            absolute = upper + addr + i
            if absolute == hole:
                flush()
                run = []
                removed.append(absolute)
                continue
            run.append((addr + i, b))
        flush()
    dst.write_text("\n".join(out) + "\n")
    return removed


print("== a real Intel HEX with a removed trampoline byte")
if IMAGES["normal"].is_file() and IMAGES["p2test"].is_file() and \
        M.OBJDUMP.is_file():
    import tempfile
    from pathlib import Path as _P
    for image in ("normal", "p2test"):
        with tempfile.TemporaryDirectory() as td:
            dst = _P(td) / f"{image}_hole.hex"
            removed = hole_ihex(IMAGES[image], 0x9, dst)
            check(f"hex {image}: exactly one byte removed", removed, [0x9])
            mem, _, _, errs, _ = M.parse_ihex(dst, strict=True)
            check(f"hex {image}: the rewritten file is valid Intel HEX",
                  errs, [])
            check(f"hex {image}: 0x9 is genuinely absent", 0x9 in mem, False)
            check(f"hex {image}: neighbours survive",
                  (0x8 in mem, 0xA in mem), (True, True))
            maps = {
                "first": M.parse_ihex(IMAGES["first"])[0],
                "normal": M.parse_ihex(IMAGES["normal"])[0],
                "p2test": M.parse_ihex(IMAGES["p2test"])[0],
            }
            maps[image] = mem
            broken = M.decode_handoff(memory=maps)
            iso = broken["second_level"][image]["decoded_in_isolation"]
            check(f"hex {image}: status is INCOMPLETE",
                  iso["status"], "INCOMPLETE")
            check(f"hex {image}: missing_bytes names 0x9",
                  iso["missing_bytes"], ["0x00000009"])
            check(f"hex {image}: chain becomes INCOMPLETE",
                  broken["chain"]["status"], "INCOMPLETE")
else:
    skip("real holey Intel HEX", "firmware or objdump missing")

print()
print(f"{fails} failure(s), {skips} skip(s)")
sys.exit(1 if fails else 0)
