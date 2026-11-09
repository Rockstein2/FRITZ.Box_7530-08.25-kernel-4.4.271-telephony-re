# E3.2 history — proof-audit fixes and soundness results

E3.2.1 correction: a known field in an old use must be present and equal in
the new use, including `register_pair`. Reasons are `FIELD_MISSING_IN_NEW`,
`FIELD_VALUE_CHANGED`, `USE_NOT_FOUND` and `DUPLICATE_USE_MISSING`; absent
old fields are recorded in `old_unknown_fields`. Re-audit retained the counts
below (25/10 old uses; 43/22 new PROVEN and 58/69 CANDIDATE).

> **Status: offline audit.  No firmware execution or hardware.**

## 1. A1 — full memory-use matching

`tools/cr16_e3.py` now matches an old memory use on:

```text
instruction address
effective address
READ / WRITE / RMW
displacement, when the old record has one
register pair, when both records have one
```

A missing old field is not silently accepted as equal.  The result has three
separate lists: `matched`, `mismatched`, `missing`; `all_old_uses_matched` is
true only when both failure lists are empty.  Synthetic tests cover:

- READ → WRITE at the same address;
- displacement changed;
- effective address changed;
- instruction address changed;
- duplicate uses;
- old displacement unavailable.

The audit also filters bare pair-to-pair `movd` instructions out of
`_callee_uses()`.  `movd (r3,r2),(r8,r7)` is a register move, not a memory
read/write.  E2 had counted such forms as memory uses; removing them is a
soundness fix, not a cosmetic change.

### Results

| Image | E2 PROVEN audited | still PROVEN | CANDIDATE | INVALID |
|---|---:|---:|---:|---:|
| normal | 25 | 11 | 3 | 11 |
| p2test | 10 | 3 | 2 | 5 |

The corrected analyzer reports 43 normal / 22 p2test `PROVEN` argument
records, plus 58/69 `CANDIDATE`.  These are not the old values relabelled:
the old set contained false memory uses, and the new set is produced by the
corrected criterion.

## 2. A2 — fail-closed E2 baseline

`old_report()` now:

- tries the immutable git baseline;
- validates JSON structure and retains the firmware SHA256;
- accepts a local backup only if it has the same identity;
- raises `RuntimeError` if neither source is available or valid;
- never returns `{"argument_propagations": []}` as a substitute for a
  missing baseline.

`main()` catches the error, prints a diagnostic, returns exit code 1 and
writes no normal report.  Tests cover missing and corrupt baselines and show
that an empty-but-valid report is distinguishable from a missing file.

## 3. A3 — table def-use

`_find_table_consumer()` now states its real scope:

```text
LOCAL_BASIC_BLOCK_ONLY
```

The first write to the target register inside the block decides the value.
The unreachable `CLOBBERED_AFTER_LOAD` branch was removed.  Table candidates
still have zero proven targets; no table entry width, stride or endianness is
claimed.

## 4. Address-space correction impacts

The abs20 expansion changes several addresses in the corrected reports:
`0x000F6006` → `0x00FF6006`, `0x000F5402` → `0x00FF5402`, etc.  The old
reports are retained only as historical encoded-field values.  New reports
carry both `encoded_address` and `architectural_effective_address`.

This is not a reclassification of a proof: the instruction and memory-use
identity is unchanged.  It corrects the numeric address printed by the
analyzer.

## 5. Verification

Required local checks:

```text
python3 tools/tests/test_cr16_dataflow.py
python3 tools/tests/test_cr16_interproc.py
python3 tools/tests/test_cr16_e3.py
python3 tools/tests/test_cr16_address_spaces.py
python3 tools/tests/test_docs_consistency.py
make -C tools/fon-slot5-protocol test
sh tools/verify-workspace.sh
git diff --check
```

Report replay is covered by the tests for the address-space, interprocedural
and E3 reports.  The CR16 binutils oracle path is
`/tmp/opencode/cr16/build/binutils/objdump`; absence of the oracle is a
diagnostic SKIP, not a pass.
