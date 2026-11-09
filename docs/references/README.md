# External Dialog / CR16 / DECT references

> **Status: bibliography and evidence-index layer.**
> Last source check: **2026-11-09**.
> No hardware was accessed for this page.

This directory records external material relevant to the SC14448 analog-FON
work.  It is not a substitute for the device-specific evidence in
`docs/fon-known-facts.md`.

## Documents

| Document | Purpose |
|---|---|
| `dialog-external-sources.md` | Source registry: URL, revision, license, verified facts and limitations |
| `dialog-register-cross-reference.md` | SC14CVMDECT PDF registers vs SC14448 firmware accesses |
| `dialog-pcm-comparison.md` | PCM timing/mode comparison; no direct settings transfer |
| `sc14480-memory-map.md` | SC14480 DIP RAM, DSP_INT_REG, interrupt and address-space cross-check; E3.2/Q57 resolution |
| `fon-e3-reference-opportunities.md` | How the new references can help E3, ranked |

## Rules

- A fact about **SC14CVMDECT**, **SC1442x**, **CR16C Linux**, **QEMU** or
  **Phoenix API** is not automatically a fact about the AVM SC14448 firmware.
- Use the confidence labels in the register cross-reference, not a shared
  address alone.
- Do not add the SC14CVMDECT or SC14480 PDFs, third-party source trees or
  firmware images to Git.  Record hashes, URLs and page excerpts instead.
- Printed datasheet page numbers are used in the reference documents; the
  SC14480 physical PDF page is normally one greater.
- Do not merge DECT RF slot numbers (0…23) with PCM/TDM slots (0…7).
- Do not treat a related-chip PCM pinmux, BCLK or electrical limit as the
  FRITZ!Box 7530 schematic.
- Keep `docs/reference/` (primary OEM capture) distinct from
  `docs/references/` (this external bibliography).
