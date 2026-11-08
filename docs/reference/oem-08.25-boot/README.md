# OEM FRITZ!OS 08.25 boot capture — primary reference

> **Status: primary captured data, not historical analysis and not an
> interpretation.** Keep these files; they are the raw OEM-side reference for
> the project. Do not replace them with summaries.

Captured by the owner on **2026-11-08** from the real FRITZ!Box 7530 after
flashing the OEM FRITZ!OS **08.25** image. The capture was made over the
board UART: `rx.log` is device → host, `tx.log` is host → device.

## Files

| File | Content |
|---|---|
| `rx.log` | Text RX capture: OpenWrt prelude, two OEM boot cycles and the OEM shell session. Binary/non-text shared-UART blocks are replaced by explicit markers. |
| `tx.log` | Exact TX command stream sent to the OEM shell; responses are in `rx.log`. |
| `SHA256SUMS` | Hashes of the two repository files above. |

The original unredacted files, including the binary shared-UART/DECT stream,
are kept **outside Git** in:

```text
/home/rck/Downloads/OpenWrt7530/.work/fon-oem-boot-2026-11-08/rx.log
/home/rck/Downloads/OpenWrt7530/.work/fon-oem-boot-2026-11-08/tx.log
```

Original hashes:

```text
rx.log  e854d392546b2013b2ff24a1193a5b0c3986cabce6ae4690d947b0bf5723bde0
tx.log  a218a8b401a08d9b6ce4c98e3476632fb1ea9722af58f6b275d6c841989bf7b9
```

`tx.log` is byte-identical in the repository because it contains no device
identifiers. `rx.log` is a text rendering of the same capture with MAC
addresses, IPv6 addresses and the DECT RFPI replaced.

**Why the raw RX file is not in Git:** the GitHub repository is public, and the
raw capture contains a binary shared-UART/DECT stream that may include
proprietary firmware data. Do not commit the unredacted captures, that binary
stream, AVM modules, firmware or extracted DTBs. If the repository is made
private, the raw file can be added separately; until then it stays in
`.work/`.

**Why the text copy is still useful:** the bootloader and kernel boot sequence
is text; only the shared-UART binary blocks are summarized. All technical lines
needed for the boot analysis are present.

## Capture structure (`rx.log`)

| Marker | Content |
|---|---|
| `OpenWrt 25.12.6` at the top | OpenWrt shell before the OEM flash/reboot |
| first `Format: Log Type` | OEM boot A; ends with `Flashing ram -> NAND` and a soft reboot |
| second `Format: Log Type` | OEM boot B, the complete DECT/telephony bring-up |
| `starting pid 262, tty '/dev/ttyMSM0'` | OEM shell on the shared UART |
| `__SERIAL_DONE_…` | command framing used by `tx.log` |

## Key OEM-side lines

These are direct excerpts from `rx.log`. They are evidence about
**FRITZ!OS 08.25 on this unit**, not about OpenWrt.

| Observation | Exact line |
|---|---|
| OEM kernel | `Linux version 4.4.271 (kbuild-team@core.avm.de) ... 2026-03-03` |
| Board | `Machine model: AVM FRITZ!Box 7530` |
| Boot image | `S - QC_IMAGE_VERSION_STRING=AVM_BOOT.BF.3.1.1` |
| Board revision | `avm_set_reset_status: ... FW(08.25)HW(236)HWS(2)BV(1.11581)BN(131719)FS(08.25)BT(1)` |
| DECT UART | `msm_dectuart_probe: set dectuart_port to ttyMSM0` |
| GPIO table at runtime | `use_hw_config_to_set_gpios: hw_config: gpio_avm_dect_reset 40` and `gpio_avm_dect_rd 16` |
| Piglet load | `Piglet_noemif: module license 'Proprietary...` then `[piglet]slow: dect_loader-bootmode` |
| Firmware upload | `[piglet]dect_file_process: upload of 'dectfw_secondlevel_441.hex' successfull` |
| Shared UART released | `msm_serial_dectuart_exit` |
| OEM TDM clock report | `[piglet]TDM: FS: 8000 Hz CLK: 1024355 Hz` |
| PCMLINK load | `[module-mem] ... to module 'pcmlink'` |
| MBOX DMA | `mbox_dma_init: irq=107 hwirq=191` |

`HWS(2)` confirms that **this board's hardware subrevision is 2**. That matches
the DTB at decompressed offset `0x98d038`, whose `avm-hw-revision/subrevision`
is `2`. It still does **not** prove which DTB the OEM bootloader selects.

## What this capture does not prove

- It does not establish GPIO40 electrical polarity or the SC14448 reset pin
  level (Q13/Q15/Q39).
- It does not prove the actual TLMM `FUNC_SEL` values or the physical PCM
  wiring (Q27/Q31/Q77).
- It does not prove that `Check_TDMInterface()` is side-effect free (Q81).
- It does not authorize any active OpenWrt operation. All previous NO-GO
  decisions remain.
- The raw binary shared-UART block is not in Git; it is captured data, not a
  firmware image to publish or flash.

## Related current facts

The capture is referenced from `../../fon-known-facts.md` (evidence class
`OEM-CAPTURE`) and from the DTB provenance section of
`../../fon-d06-summary.md`.
