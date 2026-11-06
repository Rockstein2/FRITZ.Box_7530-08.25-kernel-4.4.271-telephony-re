# FON documentation — three layers

> **Status: historical analysis.**
> This document records the reasoning and evidence as of the date it was
> written.  Some of its `UNKNOWN` / `UNVERIFIED` markers have since been
> answered.
> - Current confirmed facts: `fon-known-facts.md`
> - Current open questions: `fon-open-questions.md`
> - This file is kept for the reasoning trail, not as a status report.

Current state lives in three small files.  Everything else is either a
procedure you run or a record of how we got here.

## Layer 1 — current truth

| File | What it is |
|---|---|
| `fon-known-facts.md` | Every confirmed fact with its evidence class (GPL / DT / OEM / CODE / OFFLINE). **Start here.** |
| `fon-open-questions.md` | Every unresolved item (Q1–Q26) and the stage that closes it. The only open-questions list. |
| `fon-go-no-go.md` | Which questions must be closed before each hardware stage. |

If these three disagree with any other document, **these three win**.

## Layer 2 — runbooks (`runbook/`)

Procedures and build records.  Executable, dated, not arguments.

| File | What it is |
|---|---|
| `runbook/fon-first-hardware-test.md` | Stage A/B probe-only procedure |
| `runbook/fon-recovery-plan.md` | Recovery policy and stop conditions |
| `runbook/fon-recovery-ram-boot.md` | RAM-only TFTP boot (no NAND writes) |
| `runbook/fon-test-image-safety.md` | Rules for a test image |
| `runbook/fon-test-image-build.md` | Preparing the probe-only DTB/image |
| `runbook/fon-build-validation.md` | Build, test and artifact results |

## Layer 3 — history (`history/`)

The reasoning trail.  Many files still say `UNKNOWN` about questions that have
since been answered; each carries a *Status: historical analysis* banner.
Read them for provenance, never as status.

| File | Subject |
|---|---|
| `history/fon-avm-analysis.md` | AVM kernel modules and call chains |
| `history/fon-feasibility.md` | Original standalone-driver feasibility study |
| `history/fon-hardware.md` | Hardware architecture, SLIC/PHY identification |
| `history/fon-control-path.md` | Dialog SC14448 control-path hypothesis |
| `history/fon-pcmlink-register-path.md` | Recovered register path (slot 5, `TxDMA`/`PutRxDMA`) |
| `history/fon-tdm-hardware.md` | TDM/ADSS frame parameters and register map |
| `history/fon-dialog-boot.md` | Dialog firmware boot protocol |
| `history/fon-dialog-dependency.md` | Dialog dependency assessment |
| `history/fon-dialog-hardware-test-plan.md` | SC14448 bench plan |
| `history/fon-linux612-port.md` | Porting notes for Linux 6.12 |
| `history/fon-resource-audit.md` | Probe-safety audit |
| `history/fon-oem-bootlog-crosscheck.md` | What the OEM boot log proves |
| `history/wiki-fritzos-oem-bootlog-reference.txt` | **Reference only**: OEM FRITZ!OS boot log |

### About the OEM boot log

`history/wiki-fritzos-oem-bootlog-reference.txt` is a boot log from **the
original AVM FRITZ!OS firmware**, published on the OpenWrt Wiki page for the
7530 (it is not from OpenWrt and not from this project's hardware).  It is
kept purely as a reference for comparison: driver names, TDM clocks, GPIO
assignments and boot order.

Limits when using it:

- the log is from kernel **4.4.60**, not 4.4.271 and not 6.12;
- its FRITZ!OS build could not be confirmed as 08.25;
- it describes FRITZ!OS behaviour, not our driver;
- it must not be treated as evidence about our build;
- it contains the original reporter's MAC addresses, which are not ours.

Where it settles a question, the answer is copied into `fon-known-facts.md`
with the evidence class **OEM**.  Nothing else in this repository should cite
the log directly.

## Regenerating structure and links

```sh
sh tools/docs-restructure.sh       # move files into layers (git mv), idempotent
sh tools/docs-rewrite-links.sh     # fix cross-document links, idempotent
sh tools/docs-add-historical-banner.sh   # refresh layer banners, idempotent
```
