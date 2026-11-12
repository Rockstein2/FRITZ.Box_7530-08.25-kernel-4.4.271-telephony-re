#!/usr/bin/env python3
"""E5 — offline Gen2DSP / PCM+ / CODEC audio-architecture reconstruction.

Scope (STRICTLY OFFLINE, static only):

  * all firmware accesses to the candidate DSP register window
    ``0x01027F80..0x01027FFF`` (base cell ``[0xD6] = 0x01027F80``, guarded by
    a ``cmpd`` in the init function itself);
  * the ordered DSP/CODEC/PCM initialization sequences and their call chains
    from the second-level main entry;
  * the provenance of the DSP program (embedded firmware block at ``0x17300``
    plus the firmware's own ``DSP_PC_START`` derivation);
  * the composed ``DSP_PCM_CTRL`` / ``CLK_CODEC`` / CODEC analog writes and
    their relation to DECT timing (DIP);
  * a readiness inventory for a future standalone driver.

Every register *name* below is an **SC14480 analogy** (related device,
rev 1.0 datasheet), never a proven SC14448 map.  What is proven offline is
the firmware's own instructions: raw bytes, effective addresses derived from
``[0xD6] + offset``, and immediate/bit values.  No hardware was touched;
K1/K2 remain NO-GO.

Reports (JSON, per image, reproducible):

    cr16-e5-dsp-registers.json
    cr16-e5-dsp-init.json
    cr16-e5-dsp-program-source.json
    cr16-e5-pcm-routing.json
    cr16-e5-codec-init.json
    cr16-e5-clock-dependencies.json
    cr16-e5-readiness.json

Run: python3 tools/cr16_audio_architecture.py [--out DIR] [--objdump PATH]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import cr16_address_spaces as A
import cr16_cfg as C
import cr16_dataflow as D
import cr16_dip_trace as T
import cr16_peripheral_xrefs as X
from cr16_boot_memory_map import parse_ihex

ROOT = Path(__file__).resolve().parent.parent

NAMES = tuple("cr16-e5-" + x + ".json" for x in (
    "dsp-registers", "dsp-init", "dsp-program-source", "pcm-routing",
    "codec-init", "clock-dependencies", "readiness"))

DSP_BASE = 0x01027F80
DSP_WINDOW = (DSP_BASE, DSP_BASE + 0x80)

# ---------------------------------------------------------------------------
# SC14480 reference (analogy only).  Printed-page citations to the SC14480
# rev 1.0 datasheet.  Nothing here claims the SC14448 implements the same.
# ---------------------------------------------------------------------------
SC14480 = {
    "dsp_window": {
        0x00: "DSP_MAIN_SYNC0_REG", 0x02: "DSP_MAIN_SYNC1_REG",
        0x04: "DSP_MAIN_CNT_REG",
        0x0C: "DSP_CODEC_MIC_GAIN_REG", 0x0E: "DSP_CODEC_OUT_REG",
        0x10: "DSP_CODEC_IN_REG",
        0x12: "DSP_RAM_OUT0_REG", 0x14: "DSP_RAM_OUT1_REG",
        0x16: "DSP_RAM_OUT2_REG", 0x18: "DSP_RAM_OUT3_REG",
        0x1A: "DSP_RAM_IN0_REG", 0x1C: "DSP_RAM_IN1_REG",
        0x1E: "DSP_RAM_IN2_REG", 0x20: "DSP_RAM_IN3_REG",
        0x22: "DSP_ZCROSS1_OUT_REG", 0x24: "DSP_ZCROSS2_OUT_REG",
        0x26: "DSP_PCM_OUT0_REG", 0x28: "DSP_PCM_OUT1_REG",
        0x2A: "DSP_PCM_OUT2_REG", 0x2C: "DSP_PCM_OUT3_REG",
        0x2E: "DSP_PCM_IN0_REG", 0x30: "DSP_PCM_IN1_REG",
        0x32: "DSP_PCM_IN2_REG", 0x34: "DSP_PCM_IN3_REG",
        0x36: "DSP_PCM_CTRL_REG", 0x38: "DSP_PHASE_INFO_REG",
        0x3C: "DSP_MAIN_CTRL_REG",
        0x50: "DSP_CTRL_REG", 0x54: "DSP_PC_START_REG",
        0x56: "DSP_IRQ_START_REG", 0x58: "DSP_INT_REG",
        0x5A: "DSP_INT_MASK_REG", 0x5C: "DSP_INT_PRIO1_REG",
        0x5E: "DSP_INT_PRIO2_REG", 0x60: "DSP_OVERFLOW_REG",
        0x64: None,  # not mapped in the SC14480 register tables
    },
    # Table 63 (SC14480 rev 1.0, printed p132): micro code RAM/ROM map.
    "table63_rows": [
        {"cr16": "0x01000000-0x010003ff", "dsp": "0x0000-0x01ff",
         "meaning": "DIP Micro code RAM"},
        {"cr16": "0x01000400-0x01000fff", "dsp": "0x0200-0x07ff",
         "meaning": "DIP Micro code RAM (reserved)"},
        {"cr16": "0x01030000-0x010307ff", "dsp": "0x0000-0x03ff",
         "meaning": "Gen2DSP Micro code RAM"},
        {"cr16": "0x01030800-0x01037fff", "dsp": "0x0400-0x3fff",
         "meaning": "Gen2DSP Micro code RAM (Reserved)"},
        {"cr16": "0x00010000-0x00013fff", "dsp": "0x4000-0x5fff",
         "meaning": "Gen2DSP Micro code RAM mapped in Shared RAM"},
        {"cr16": "0x00014000-0x00017fff", "dsp": "0x6000-0x7fff",
         "meaning": "Gen2DSP Micro code RAM (Reserved)"},
        {"cr16": "0x01040000-0x0104afff", "dsp": "0x8000-0xd7ff",
         "meaning": "Micro code ROM"},
        {"cr16": "0x0104b000-0x0104ffff", "dsp": "0xd800-0xffff",
         "meaning": "Reserved"},
    ],
    "peripheral": {
        0x00FF4000: "CLK_AMBA_REG", 0x00FF4002: "CLK_CODEC_DIV_REG",
        0x00FF4004: "CLK_CODEC_REG", 0x00FF4006: "CLK_DSP_REG",
        0x00FF400C: "CLK_PER_DIV_REG", 0x00FF400E: "CLK_PER10_DIV_REG",
        0x00FF4010: "CLK_PLL_CTRL_REG", 0x00FF4012: "CLK_PLL_DIV_REG",
        0x00FF401C: None,  # Reserved in SC14480
        0x00FF5800: "CODEC_MIC_REG", 0x00FF5802: "CODEC_LSR_REG",
        0x00FF5804: "CODEC_VREF_REG", 0x00FF5806: "CODEC_TONE_REG",
        0x00FF5808: "CODEC_ADDA_REG", 0x00FF580A: "CODEC_OFFSET1_REG",
        0x00FF580C: "CODEC_TEST_CTRL_REG", 0x00FF580E: "CODEC_OFFSET2_REG",
        0x00FF6006: "DIP_CTRL_REG", 0x00FF600E: "DIP_CTRL2_REG",
        0x00FF481E: "PAD_CTRL_REG", 0x00FF4836: "P0_DIR_REG",
        0x00FF4838: "P0_MODE_REG", 0x00FF4856: "P2_DIR_REG",
        0x00FF4858: "P2_MODE_REG", 0x00FF4860: "P3_DATA_REG",
        0x00FF4866: "P3_DIR_REG", 0x00FF4868: "P3_MODE_REG",
        0x00FF5404: "INT_PRIO0_REG", 0x00FF5402: "RESET_INT_PENDING_REG",
        0x00FF5406: "INT_PRIO1_REG", 0x00FF5408: "INT_PRIO2_REG",
        0x00FF540A: "INT_PRIO3_REG",
    },
    "dsp_ctrl_bits": {2: "DSP_EN", 3: "DSP_CLK_EN", 4: "DSP_CR16_INT",
                      8: "DBG_EN"},
    "dsp_main_ctrl_bits": {
        0x400: "DSP_MAIN_CTRL=10: main counter starts on DIP <A_NORM> "
               "(DIP-synchronised start-up for voice connection)"},
    "main_sync1_fields": {
        0xC000: "PCM_SYNC", 0x3000: "ADC_SYNC", 0x0C00: "DA_LSR_SYNC",
        0x0300: "DA_CLASSD_SYNC", 0x00C0: "AD_SYNC", 0x0030: "DSP_SYNC2",
        0x000C: "DSP_SYNC1", 0x0003: "DSP_SYNC0"},
    "main_sync0_fields": {
        0xC000: "RAMOUT3_SYNC", 0x3000: "RAMOUT2_SYNC",
        0x0C00: "RAMOUT1_SYNC", 0x0300: "RAMOUT0_SYNC",
        0x00C0: "RAMIN3_SYNC", 0x0030: "RAMIN2_SYNC",
        0x000C: "RAMIN1_SYNC", 0x0003: "RAMIN0_SYNC"},
    "pcm_ctrl_bits": {
        7: "PCM_CLKINV", 6: "PCM_PPOD", 5: "PCM_FSC0DEL", 2: "DSP_PCM_SYNC",
        1: "PCM_MASTER", 0: "PCM_EN"},
    "codec_vref_bits": {9: "REFINT_PD", 8: "AGND_LSR_PD", 7: "BIAS_PD",
                        6: "VREF_BG_PD", 5: "AMP1V5_PD", 4: "VREF_INIT",
                        1: "VREF_FILT_PD", 0: "VREF_PD"},
    "codec_mic_bits": {11: "MICH_ON", 10: "DSP_CTRL", 9: "MIC_OFFCOM_ON",
                       8: "MIC_OFFCOM_SG", 3: "MIC_MUTE", 2: "MIC_PD"},
    "codec_lsr_bits": {9: "LSREN_SE", 5: "LSRN_PD", 2: "LSRP_PD"},
    # LSRATT field (bits 8-6), SC14480 Table 113 steps + Table 299 level.
    "lsratt_gain": {
        0b000: "+2 dB (Table 113 step table)",
        0b001: "0 dB nominal (Table 299 level at 0 dBm0)",
        0b111: "-12 dB (Table 113 step table)",
    },
    "codec_adda_bits": {1: "AD_PD", 0: "DA_PD"},
    "codec_tone_bits": {3: "RNG_PR_DIS", 2: "RNG_PD", 1: "CID_PR_DIS",
                        0: "CID_PD"},
    "codec_test_bits": {13: "COR_STAT", 12: "COR_ON"},
    "dip_ctrl_bits": {7: "URST"},
    "dip_ctrl2_bits": {8: "SLOTCNT_RES"},
    "source": "SC14480 rev 1.0 datasheet (related device), printed pages "
              "131-132, 160-183; PDF SHA256 "
              "a0b0300cc0dc50ac98bff4c9021dcbb86ba7b063554f406ac8f65c84a51782d0",
}

# Per-image site tables.  Each entry is (address, mnemonic, operands); the
# analyzer asserts the exact shape at every address and fails closed on any
# model change.  Addresses were chosen by instruction-level inspection of
# both SHA-checked images.
SITES = {
    "normal": dict(
        main_entry=(0x39F8, "push", "$0x7,r7,RA"),
        # main -> audio-init call sites
        call_pad_init=(0x3A0C, "bal", "(ra),*-0x1388:m"),
        call_codec_gpio=(0x3A10, "bal", "(ra),*-0x131c:m"),
        call_enable_chain=(0x3A34, "bal", "(ra),*-0x1a0a:m"),
        call_enable=(0x1A4A, "bal", "(ra),*-0x190e:m"),
        # f_pad_init (0x1388) -> f_dsp_init (0x1330)
        pad_dip_ctrl=(0x145C, "storw", "r0,0xf6006:m"),
        pad_set_r2=(0x1460, "movb", "$0x1:s,r2"),
        pad_call_dsp_init=(0x1462, "bal", "(ra),*-0x1330:m"),
        # f_dsp_init
        dsp_init_entry=(0x1330, "push", "$0x2,r7,RA"),
        dsp_init_base_load=(0x1338, "loadd", "0x0:s(r8,r7),(r1,r0)"),
        dsp_init_guard=(0x133A, "cmpd", "$0x1027f80:l,(r1,r0)"),
        dsp_init_guard_skip=(0x1340, "bne", "*+0x1386:s"),
        dsp_init_cond_zero=(0x1342, "beq0b", "r2,*+0xa:s"),
        dsp_init_dip=(0x1344, "movw", "$0x80:m,r2"),
        dsp_init_dip_store=(0x1348, "storw", "r2,0xf6006:m"),
        dsp_init_ctrl_pd=(0x134C, "cbitw", "$0x2:s,0x50:m(r1,r0)"),
        dsp_init_adda=(0x1358, "orw", "$0x3:s,r4"),
        dsp_init_adda_store=(0x135A, "storw", "r4,0x0:s(r3,r2)"),
        dsp_init_int_clear=(0x135E, "storw", "r2,0x58:m(r1,r0)"),
        dsp_init_clk_codec_off=(0x1362, "storw", "$0x0:s,0xf4004:m"),
        dsp_init_call_clk=(0x1366, "bal", "(ra),*+0x1468:m"),
        dsp_init_call_post=(0x136A, "bal", "(ra),*-0x688:m"),
        dsp_init_pc_lit=(0x1370, "movd", "$0x17300:l,(r3,r2)"),
        dsp_init_pc_shift=(0x1376, "lshd", "$-1:s,(r3,r2)"),
        dsp_init_pc_add=(0x1378, "addw", "$0xc000:m,r2"),
        dsp_init_pc_store=(0x137C, "storw", "r2,0x54:m(r1,r0)"),
        dsp_init_flag=(0x1380, "sbitb", "$0x7,0x93c8:l"),
        # f_codec_clk (0x1468) and its helpers
        clk_entry=(0x1468, "push", "$0x7,r7,RA"),
        clk_flag_byte=(0x1472, "movd", "$0x93cd:l,(r1,r0)"),
        clk_pad=(0x147A, "movd", "$0xff481e:l,(r3,r2)"),
        clk_dip2=(0x1486, "movd", "$0xff600e:l,(r12)"),
        clk_gpio2_dir=(0x148C, "movd", "$0xff4856:l,(r5,r4)"),
        clk_gpio2_mode=(0x1492, "movd", "$0xff4858:l,(r7,r6)"),
        clk_mask=(0x1498, "movw", "$0x3fff:m,r10"),
        clk_path_test=(0x149C, "tbitb", "$0x0,0x0:s(r1,r0)"),
        clk_aux_base=(0x14A0, "movd", "$0xff401c:l,(r9,r8)"),
        clk_aux_zero=(0x14A6, "storw", "$0x0:s,0x0:s(r9,r8)"),
        clk_aux_bit7=(0x14A8, "sbitw", "$0x7:s,0x0:s(r9,r8)"),
        clk_aux_or=(0x14AC, "orw", "$0x51:m,r11"),
        clk_aux_store=(0x14B0, "storw", "r11,0x0:s(r9,r8)"),
        clk_codec_base=(0x14B2, "movd", "$0xff4004:l,(r9,r8)"),
        clk_codec_and=(0x14BA, "andw", "$0xfcff:m,r11"),
        clk_codec_store=(0x14BE, "storw", "r11,0x0:s(r9,r8)"),
        clk_codec_bit9=(0x14C4, "sbitw", "$0x9:s,0x0:s(r9,r8)"),
        clk_codec_pcm_en=(0x14C6, "sbitw", "$0xe:s,0x0:s(r9,r8)"),
        clk_gpio3_dir=(0x14C8, "movd", "$0xff4868:l,(r9,r8)"),
        clk_gpio3_and=(0x14D0, "andw", "r10,r11"),
        clk_gpio3_store=(0x14D2, "storw", "r11,0x0:s(r9,r8)"),
        clk_gpio3_mode=(0x14D6, "movd", "$0xff4866:l,(r9,r8)"),
        clk_gpio3_or=(0x14DE, "orw", "$0xc000:m,r11"),
        clk_gpio3_mode_store=(0x14E2, "storw", "r11,0x0:s(r9,r8)"),
        clk_tone=(0x14E4, "sbitw", "$0x2:s,0xf5806:m"),
        clk_hlp1_call=(0x14E8, "bal", "(ra),*+0x1580:m"),
        clk_hlp1_or=(0x14EC, "orw", "$0x30:m,r6"),
        clk_hlp2_call=(0x14F0, "bal", "(ra),*+0x1594:m"),
        clk_hlp2_or=(0x14F4, "orw", "$0xc00:m,r6"),
        clk_hlp3_call=(0x14F8, "bal", "(ra),*+0x156c:m"),
        clk_pcm_write2=(0x14FC, "storw", "$0x2:s,0x0:s(r5,r4)"),
        clk_pcm_bit6=(0x14FE, "sbitw", "$0x6:s,0x0:s(r5,r4)"),
        clk_pad_bit5=(0x1500, "sbitw", "$0x5:s,0x0:s(r3,r2)"),
        clk_pad_bit4=(0x1502, "sbitw", "$0x4:s,0x0:s(r3,r2)"),
        clk_flag5_test=(0x1504, "tbitb", "$0x5,0x0:s(r1,r0)"),
        clk_pcm_bit11=(0x1508, "sbitw", "$0xb:s,0x0:s(r5,r4)"),
        clk_flag_cmp=(0x1510, "cmpb", "$0x8:s,r0"),
        clk_pcm_bit9=(0x1514, "sbitw", "$0x9:s,0x0:s(r5,r4)"),
        clk_path_b_cbit1=(0x152C, "cbitw", "$0x1:s,0x0:s(r5,r4)"),
        clk_path_b_sbit2=(0x152E, "sbitw", "$0x2:s,0x0:s(r5,r4)"),
        clk_path_b_fsclen=(0x1532, "andw", "$0xffe7:m,r6"),
        clk_path_b_fsclen_st=(0x1536, "storw", "r6,0x0:s(r5,r4)"),
        clk_flag3_test=(0x153C, "tbitb", "$0x3,0x0:s(r1,r0)"),
        clk_pcm_fscdel0=(0x1540, "cbitw", "$0x5:s,0x0:s(r5,r4)"),
        clk_pcm_fscdel1=(0x1544, "sbitw", "$0x5:s,0x0:s(r5,r4)"),
        clk_pcm_bit6b=(0x1546, "sbitw", "$0x6:s,0x0:s(r5,r4)"),
        clk_pcm_clr7=(0x154C, "cbitw", "$0x7:s,0x0:s(r5,r4)"),
        clk_pcm_clr8=(0x154E, "cbitw", "$0x8:s,0x0:s(r5,r4)"),
        clk_pcm_clr9=(0x1550, "cbitw", "$0x9:s,0x0:s(r5,r4)"),
        clk_pcm_keep=(0x1554, "andw", "$0x83ff:m,r0"),
        clk_pcm_keep_st=(0x1558, "storw", "r0,0x0:s(r5,r4)"),
        clk_pcm_clr15=(0x155A, "cbitw", "$0xf:s,0x0:s(r5,r4)"),
        clk_dip2_resume=(0x155C, "sbitw", "$0x8:s,0x0:s(r12)"),
        clk_pcm_en=(0x155E, "sbitw", "$0x0:s,0x0:s(r5,r4)"),
        clk_dsp_base2=(0x1560, "loadd", "0xd6:l,(r1,r0)"),
        clk_dsp_64=(0x1566, "storw", "$0x1:s,0x64:m(r1,r0)"),
        hlp3_entry=(0x156C, "storw", "r6,0x0:s(r5,r4)"),
        hlp3_reload=(0x156E, "loadd", "0xd6:l,(r5,r4)"),
        hlp3_sync1_and=(0x1576, "andw", "r10,r6"),
        hlp3_sync1_store=(0x1578, "storw", "r6,0x2:s(r5,r4)"),
        hlp3_pcm_ptr=(0x157A, "addd", "$0x36:m,(r5,r4)"),
        hlp1_entry=(0x1580, "loadw", "0x0:s(r7,r6),r8"),
        hlp2_entry=(0x1594, "storw", "r6,0x0:s(r5,r4)"),
        # f_dsp_cfg (0x1856)
        cfg_entry=(0x1856, "push", "$0x2,r7,RA"),
        cfg_sync1_zero=(0x185E, "storw", "$0x0:s,0x2:m(r8,r7)"),
        cfg_helper_lit=(0x1862, "movw", "$0x7c00:m,r2"),
        cfg_helper_call=(0x1866, "bal", "(ra),*-0x182e:m"),
        cfg_prio1_lit=(0x186A, "movw", "$0x773:m,r0"),
        cfg_prio1_store=(0x186E, "storw", "r0,0x5c:m(r8,r7)"),
        cfg_main_ptr=(0x1872, "addd", "$0x3c:m,(r8,r7)"),
        cfg_main_store=(0x187A, "storw", "r0,0x0:s(r8,r7)"),
        cfg_amba=(0x187C, "sbitw", "$0x7:s,0xf4000:m"),
        cfg_ctrl_or=(0x1882, "orw", "$0xc:s,r0"),
        cfg_ctrl_store=(0x1884, "storw", "r0,0x14:s(r8,r7)"),
        cfg_dbg=(0x1886, "sbitw", "$0x8:s,0x0:s(r8,r7)"),
        # f_clk2 (0x188a), r2==4 path exercised from f_enable
        clk2_entry=(0x188A, "push", "$0x2,r7,RA"),
        clk2_pll_base=(0x1890, "movd", "$0xff4010:l,(r8,r7)"),
        clk2_pll_clr3=(0x1896, "cbitw", "$0x3:s,0x0:s(r8,r7)"),
        clk2_pll_800=(0x18B8, "storw", "r0,0x0:s(r8,r7)"),
        clk2_codec_div=(0x18BE, "storw", "r0,0xf4002:m"),
        clk2_per_div=(0x18C2, "storw", "r0,0xf400c:m"),
        clk2_per10=(0x18CA, "storw", "r1,0xf400e:m"),
        clk2_dsp=(0x18CE, "storw", "r0,0xf4006:m"),
        clk2_cmp=(0x18D2, "cmpb", "$0x4:s,r2"),
        clk2_skip=(0x18D6, "br", "*+0x190a:s"),
        clk2_amba_call=(0x18DE, "bal", "(ra),*+0x28a4c:m"),
        clk2_amba2_call=(0x18E4, "bal", "(ra),*+0x28a70:m"),
        clk2_pll_div=(0x18EC, "storw", "r0,0xf4012:m"),
        clk2_pll_852=(0x18F4, "storw", "r0,0x0:s(r8,r7)"),
        clk2_pll_sbit3=(0x1908, "sbitw", "$0x3:s,0x0:s(r8,r7)"),
        # f_enable (0x190e)
        en_entry=(0x190E, "push", "$0x2,r7,RA"),
        en_prio_base=(0x1918, "movd", "$0xff5404:l,(r2,r1)"),
        en_prio_and=(0x1920, "andw", "$0xff0f:m,r3"),
        en_prio_or=(0x1924, "orw", "$0x30:m,r3"),
        en_prio_store=(0x1928, "storw", "r3,0x0:s(r2,r1)"),
        en_pending=(0x1934, "storw", "r0,0xf5402:m"),
        en_base=(0x193E, "loadd", "0x0:s(r8,r7),(r1,r0)"),
        en_mask_ptr=(0x1942, "addd", "$0x5a:m,(r3,r2)"),
        en_mask_or=(0x1948, "orw", "$0x803c:m,r4"),
        en_mask_store=(0x194C, "storw", "r4,0x0:s(r3,r2)"),
        en_clk_dsp=(0x194E, "storw", "$0x9:s,0xf4006:m"),
        en_dsp_en=(0x1952, "sbitw", "$0x2:s,0x50:m(r1,r0)"),
        en_adda_and=(0x195E, "andw", "$0x7ffc:m,r4"),
        en_adda_store=(0x1962, "storw", "r4,0x0:s(r3,r2)"),
        en_vref_init0=(0x1964, "cbitw", "$0x4:s,0xf5804:m"),
        en_main_lit=(0x1968, "movw", "$0x400:m,r2"),
        en_main_store=(0x196C, "storw", "r2,0x3c:m(r1,r0)"),
        en_r2_4=(0x1970, "movb", "$0x4:s,r2"),
        en_call_clk2=(0x1972, "bal", "(ra),*-0x188a:m"),
        en_call_cfg=(0x1976, "bal", "(ra),*-0x1856:m"),
        en_mic_base=(0x197A, "movd", "$0xff5800:l,(r2,r1)"),
        en_test_base=(0x198C, "movd", "$0xff580c:l,(r5,r4)"),
        en_test_cor=(0x1992, "sbitw", "$0xc:s,0x0:s(r5,r4)"),
        en_lsr_sel_rd=(0x1994, "loadw", "0xf4004:m,r0"),
        en_lsr_sel_cmp=(0x199C, "cmpw", "$0xc00:m,r0"),
        en_mic_mute=(0x19A4, "orw", "$0x8:s,r0"),
        en_mic_mute_st=(0x19A6, "storw", "r0,0x0:s(r2,r1)"),
        en_cor_wait=(0x19A8, "tbitw", "$0xd:s,0x0:s(r5,r4)"),
        en_off1_rd=(0x19AC, "loadw", "0xf580a:m,r0"),
        en_off2_st=(0x19B0, "storw", "r0,0xf580e:m"),
        en_dsp_clk_off=(0x19B8, "cbitw", "$0x3:s,0x50:m(r1,r0)"),
        # runtime DSP observers
        isr_entry=(0x28A94, "push", "$0x8,r0,RA"),
        isr_state_rd=(0x28AA0, "loadb", "0x0:s(r8,r7),r9"),
        isr_state_wr=(0x28AA6, "storb", "r0,0x0:s(r8,r7)"),
        isr_dsp_base=(0x28AA8, "loadd", "0xd6:l,(r1,r0)"),
        isr_dsp_int_ptr=(0x28AAE, "addd", "$0x58:m,(r1,r0)"),
        isr_dsp_int_rd=(0x28AB2, "loadw", "0x0:s(r1,r0),r10"),
        isr_dsp_int_clr=(0x28AB4, "storw", "r10,0x0:s(r1,r0)"),
        isr_ret=(0x28B0A, "retx", ""),
        phase_rd=(0x287F2, "loadd", "0xd6:l,(r1,r0)"),
        phase_off=(0x287F8, "loadw", "0x38:m(r1,r0),r2"),
        phase_struct=(0x287FC, "movd", "$0x2c4:l,(r1,r0)"),
        phase_cmp=(0x28804, "cmpw", "r2,r3"),
        phase_update=(0x2881A, "storw", "r2,0x14:s(r1,r0)"),
        main_call_dispatch=(0x3A54, "bal", "(ra),*+0x287b8:m"),
        dispatch_state=(0x287C6, "movb", "$0x25:m,r7"),
        # CODEC analog init part 1 (0x11ce) and part 2 (0x12ea)
        codec1_entry=(0x11CE, "push", "$0x1,r7"),
        codec1_vref=(0x1252, "movd", "$0xff5804:l,(r3,r2)"),
        codec1_vref_bias=(0x1258, "cbitw", "$0x7:s,0x0:s(r3,r2)"),
        codec1_vref_pre=(0x1262, "storw", "r0,0x0:s(r3,r2)"),
        codec1_vref_all=(0x1270, "sbitw", "$0x4:s,0x0:s(r3,r2)"),
        codec1_delay_st=(0x1272, "storw", "$0x0:s,0x0:s(sp)"),
        codec1_delay_cmp=(0x127C, "cmpw", "$0x7d0:m,r2"),
        codec1_mic_base=(0x1282, "movd", "$0xff5800:l,(r3,r2)"),
        codec1_mic_pd=(0x12AE, "cbitw", "$0x2:s,0x0:s(r3,r2)"),
        codec1_lsr_base=(0x12B0, "movd", "$0xff5802:l,(r1,r0)"),
        codec1_lsr_att=(0x12BC, "storw", "r2,0x0:s(r1,r0)"),
        codec1_lsr_mode_p=(0x12C6, "storw", "r2,0x0:s(r1,r0)"),
        codec1_lsr_mode_n=(0x12D2, "storw", "r2,0x0:s(r1,r0)"),
        codec1_lsr_pd=(0x12D8, "cbitw", "$0x2:s,0x0:s(r1,r0)"),
        codec1_lsr_final=(0x12E4, "storw", "r2,0x0:s(r1,r0)"),
        codec1_tone=(0x1224, "sbitw", "$0x3:s,0xf5806:m"),
        codec_wrap_call=(0x131E, "bal", "(ra),*-0x11ce:m"),
        codec_wrap_flag=(0x1322, "tbitb", "$0x0,0x93cd:l"),
        codec2_call=(0x132A, "bal", "(ra),*-0x12ea:m"),
        codec2_entry=(0x12EA, "movd", "$0xff4838:l,(r1,r0)"),
    ),
    "p2test": dict(
        main_entry=(0x27112, "push", "$0x7,r7,RA"),
        call_pad_init=(0x27126, "bal", "(ra),*-0xdfe:m"),
        call_codec_gpio=(0x2712A, "bal", "(ra),*-0xd92:m"),
        call_enable_chain=(0x27152, "bal", "(ra),*-0x1440:m"),
        call_enable=(0x1480, "bal", "(ra),*-0x1390:m"),
        pad_dip_ctrl=(0xED2, "storw", "r0,0xf6006:m"),
        pad_set_r2=(0xED6, "movb", "$0x1:s,r2"),
        pad_call_dsp_init=(0xED8, "bal", "(ra),*-0xda6:m"),
        dsp_init_entry=(0xDA6, "push", "$0x2,r7,RA"),
        dsp_init_base_load=(0xDAE, "loadd", "0x0:s(r8,r7),(r1,r0)"),
        dsp_init_guard=(0xDB0, "cmpd", "$0x1027f80:l,(r1,r0)"),
        dsp_init_guard_skip=(0xDB6, "bne", "*+0xdfc:s"),
        dsp_init_cond_zero=(0xDB8, "beq0b", "r2,*+0xa:s"),
        dsp_init_dip=(0xDBA, "movw", "$0x80:m,r2"),
        dsp_init_dip_store=(0xDBE, "storw", "r2,0xf6006:m"),
        dsp_init_ctrl_pd=(0xDC2, "cbitw", "$0x2:s,0x50:m(r1,r0)"),
        dsp_init_adda=(0xDCE, "orw", "$0x3:s,r4"),
        dsp_init_adda_store=(0xDD0, "storw", "r4,0x0:s(r3,r2)"),
        dsp_init_int_clear=(0xDD4, "storw", "r2,0x58:m(r1,r0)"),
        dsp_init_clk_codec_off=(0xDD8, "storw", "$0x0:s,0xf4004:m"),
        dsp_init_call_clk=(0xDDC, "bal", "(ra),*+0xee4:m"),
        dsp_init_call_post=(0xDE0, "bal", "(ra),*-0x4e2:m"),
        dsp_init_pc_lit=(0xDE6, "movd", "$0x17300:l,(r3,r2)"),
        dsp_init_pc_shift=(0xDEC, "lshd", "$-1:s,(r3,r2)"),
        dsp_init_pc_add=(0xDEE, "addw", "$0xc000:m,r2"),
        dsp_init_pc_store=(0xDF2, "storw", "r2,0x54:m(r1,r0)"),
        dsp_init_flag=(0xDF6, "sbitb", "$0x7,0x950e:l"),
        clk_entry=(0xEE4, "push", "$0x7,r7,RA"),
        clk_flag_byte=(0xEEE, "movd", "$0x9514:l,(r1,r0)"),
        clk_pad=(0xEF6, "movd", "$0xff481e:l,(r3,r2)"),
        clk_dip2=(0xF02, "movd", "$0xff600e:l,(r12)"),
        clk_gpio2_dir=(0xF08, "movd", "$0xff4856:l,(r5,r4)"),
        clk_gpio2_mode=(0xF0E, "movd", "$0xff4858:l,(r7,r6)"),
        clk_mask=(0xF14, "movw", "$0x3fff:m,r10"),
        clk_path_test=(0xF18, "tbitb", "$0x0,0x0:s(r1,r0)"),
        clk_aux_base=(0xF1C, "movd", "$0xff401c:l,(r9,r8)"),
        clk_aux_zero=(0xF22, "storw", "$0x0:s,0x0:s(r9,r8)"),
        clk_aux_bit7=(0xF24, "sbitw", "$0x7:s,0x0:s(r9,r8)"),
        clk_aux_or=(0xF28, "orw", "$0x51:m,r11"),
        clk_aux_store=(0xF2C, "storw", "r11,0x0:s(r9,r8)"),
        clk_codec_base=(0xF2E, "movd", "$0xff4004:l,(r9,r8)"),
        clk_codec_and=(0xF36, "andw", "$0xfcff:m,r11"),
        clk_codec_store=(0xF3A, "storw", "r11,0x0:s(r9,r8)"),
        clk_codec_bit9=(0xF40, "sbitw", "$0x9:s,0x0:s(r9,r8)"),
        clk_codec_pcm_en=(0xF42, "sbitw", "$0xe:s,0x0:s(r9,r8)"),
        clk_gpio3_dir=(0xF44, "movd", "$0xff4868:l,(r9,r8)"),
        clk_gpio3_and=(0xF4C, "andw", "r10,r11"),
        clk_gpio3_store=(0xF4E, "storw", "r11,0x0:s(r9,r8)"),
        clk_gpio3_mode=(0xF52, "movd", "$0xff4866:l,(r9,r8)"),
        clk_gpio3_or=(0xF5A, "orw", "$0xc000:m,r11"),
        clk_gpio3_mode_store=(0xF5E, "storw", "r11,0x0:s(r9,r8)"),
        clk_tone=(0xF60, "sbitw", "$0x2:s,0xf5806:m"),
        clk_hlp1_call=(0xF64, "bal", "(ra),*+0xffc:m"),
        clk_hlp1_or=(0xF68, "orw", "$0x30:m,r6"),
        clk_hlp2_call=(0xF6C, "bal", "(ra),*+0x1010:m"),
        clk_hlp2_or=(0xF70, "orw", "$0xc00:m,r6"),
        clk_hlp3_call=(0xF74, "bal", "(ra),*+0xfe8:m"),
        clk_pcm_write2=(0xF78, "storw", "$0x2:s,0x0:s(r5,r4)"),
        clk_pcm_bit6=(0xF7A, "sbitw", "$0x6:s,0x0:s(r5,r4)"),
        clk_pad_bit5=(0xF7C, "sbitw", "$0x5:s,0x0:s(r3,r2)"),
        clk_pad_bit4=(0xF7E, "sbitw", "$0x4:s,0x0:s(r3,r2)"),
        clk_flag5_test=(0xF80, "tbitb", "$0x5,0x0:s(r1,r0)"),
        clk_pcm_bit11=(0xF84, "sbitw", "$0xb:s,0x0:s(r5,r4)"),
        clk_flag_cmp=(0xF8C, "cmpb", "$0x8:s,r0"),
        clk_pcm_bit9=(0xF90, "sbitw", "$0x9:s,0x0:s(r5,r4)"),
        clk_path_b_cbit1=(0xFA8, "cbitw", "$0x1:s,0x0:s(r5,r4)"),
        clk_path_b_sbit2=(0xFAA, "sbitw", "$0x2:s,0x0:s(r5,r4)"),
        clk_path_b_fsclen=(0xFAE, "andw", "$0xffe7:m,r6"),
        clk_path_b_fsclen_st=(0xFB2, "storw", "r6,0x0:s(r5,r4)"),
        clk_flag3_test=(0xFB8, "tbitb", "$0x3,0x0:s(r1,r0)"),
        clk_pcm_fscdel0=(0xFBC, "cbitw", "$0x5:s,0x0:s(r5,r4)"),
        clk_pcm_fscdel1=(0xFC0, "sbitw", "$0x5:s,0x0:s(r5,r4)"),
        clk_pcm_bit6b=(0xFC2, "sbitw", "$0x6:s,0x0:s(r5,r4)"),
        clk_pcm_clr7=(0xFC8, "cbitw", "$0x7:s,0x0:s(r5,r4)"),
        clk_pcm_clr8=(0xFCA, "cbitw", "$0x8:s,0x0:s(r5,r4)"),
        clk_pcm_clr9=(0xFCC, "cbitw", "$0x9:s,0x0:s(r5,r4)"),
        clk_pcm_keep=(0xFD0, "andw", "$0x83ff:m,r0"),
        clk_pcm_keep_st=(0xFD4, "storw", "r0,0x0:s(r5,r4)"),
        clk_pcm_clr15=(0xFD6, "cbitw", "$0xf:s,0x0:s(r5,r4)"),
        clk_dip2_resume=(0xFD8, "sbitw", "$0x8:s,0x0:s(r12)"),
        clk_pcm_en=(0xFDA, "sbitw", "$0x0:s,0x0:s(r5,r4)"),
        clk_dsp_base2=(0xFDC, "loadd", "0xd6:l,(r1,r0)"),
        clk_dsp_64=(0xFE2, "storw", "$0x1:s,0x64:m(r1,r0)"),
        hlp3_entry=(0xFE8, "storw", "r6,0x0:s(r5,r4)"),
        hlp3_reload=(0xFEA, "loadd", "0xd6:l,(r5,r4)"),
        hlp3_sync1_and=(0xFF2, "andw", "r10,r6"),
        hlp3_sync1_store=(0xFF4, "storw", "r6,0x2:s(r5,r4)"),
        hlp3_pcm_ptr=(0xFF6, "addd", "$0x36:m,(r5,r4)"),
        hlp1_entry=(0xFFC, "loadw", "0x0:s(r7,r6),r8"),
        hlp2_entry=(0x1010, "storw", "r6,0x0:s(r5,r4)"),
        cfg_entry=(0x12D8, "push", "$0x2,r7,RA"),
        cfg_sync1_zero=(0x12E0, "storw", "$0x0:s,0x2:m(r8,r7)"),
        cfg_helper_lit=(0x12E4, "movw", "$0x7c00:m,r2"),
        cfg_helper_call=(0x12E8, "bal", "(ra),*-0x12b0:m"),
        cfg_prio1_lit=(0x12EC, "movw", "$0x773:m,r0"),
        cfg_prio1_store=(0x12F0, "storw", "r0,0x5c:m(r8,r7)"),
        cfg_main_ptr=(0x12F4, "addd", "$0x3c:m,(r8,r7)"),
        cfg_main_store=(0x12FC, "storw", "r0,0x0:s(r8,r7)"),
        cfg_amba=(0x12FE, "sbitw", "$0x7:s,0xf4000:m"),
        cfg_ctrl_or=(0x1304, "orw", "$0xc:s,r0"),
        cfg_ctrl_store=(0x1306, "storw", "r0,0x14:s(r8,r7)"),
        cfg_dbg=(0x1308, "sbitw", "$0x8:s,0x0:s(r8,r7)"),
        clk2_entry=(0x130C, "push", "$0x2,r7,RA"),
        clk2_pll_base=(0x1312, "movd", "$0xff4010:l,(r8,r7)"),
        clk2_pll_clr3=(0x1318, "cbitw", "$0x3:s,0x0:s(r8,r7)"),
        clk2_pll_800=(0x133A, "storw", "r0,0x0:s(r8,r7)"),
        clk2_codec_div=(0x1340, "storw", "r0,0xf4002:m"),
        clk2_per_div=(0x1344, "storw", "r0,0xf400c:m"),
        clk2_per10=(0x134C, "storw", "r1,0xf400e:m"),
        clk2_dsp=(0x1350, "storw", "r0,0xf4006:m"),
        clk2_cmp=(0x1354, "cmpb", "$0x4:s,r2"),
        clk2_skip=(0x1358, "br", "*+0x138c:s"),
        clk2_amba_call=(0x1360, "bal", "(ra),*+0x9fb4:m"),
        clk2_amba2_call=(0x1366, "bal", "(ra),*+0x9fd8:m"),
        clk2_pll_div=(0x136E, "storw", "r0,0xf4012:m"),
        clk2_pll_852=(0x1376, "storw", "r0,0x0:s(r8,r7)"),
        clk2_pll_sbit3=(0x138A, "sbitw", "$0x3:s,0x0:s(r8,r7)"),
        en_entry=(0x1390, "push", "$0x2,r7,RA"),
        en_prio_base=(0x139A, "movd", "$0xff5404:l,(r2,r1)"),
        en_prio_and=(0x13A2, "andw", "$0xff0f:m,r3"),
        en_prio_or=(0x13A6, "orw", "$0x30:m,r3"),
        en_prio_store=(0x13AA, "storw", "r3,0x0:s(r2,r1)"),
        en_pending=(0x13B6, "storw", "r0,0xf5402:m"),
        en_base=(0x13C0, "loadd", "0x0:s(r8,r7),(r1,r0)"),
        en_mask_ptr=(0x13C4, "addd", "$0x5a:m,(r3,r2)"),
        en_mask_or=(0x13CA, "orw", "$0x803c:m,r4"),
        en_mask_store=(0x13CE, "storw", "r4,0x0:s(r3,r2)"),
        en_clk_dsp=(0x13D0, "storw", "$0x9:s,0xf4006:m"),
        en_dsp_en=(0x13D4, "sbitw", "$0x2:s,0x50:m(r1,r0)"),
        en_adda_and=(0x13E0, "andw", "$0x7ffc:m,r4"),
        en_adda_store=(0x13E4, "storw", "r4,0x0:s(r3,r2)"),
        en_vref_init0=(0x13E6, "cbitw", "$0x4:s,0xf5804:m"),
        en_main_lit=(0x13EA, "movw", "$0x400:m,r2"),
        en_main_store=(0x13EE, "storw", "r2,0x3c:m(r1,r0)"),
        en_r2_4=(0x13F2, "movb", "$0x4:s,r2"),
        en_call_clk2=(0x13F4, "bal", "(ra),*-0x130c:m"),
        en_call_cfg=(0x13F8, "bal", "(ra),*-0x12d8:m"),
        en_mic_base=(0x13FC, "movd", "$0xff5800:l,(r2,r1)"),
        en_test_base=(0x140E, "movd", "$0xff580c:l,(r5,r4)"),
        en_test_cor=(0x1414, "sbitw", "$0xc:s,0x0:s(r5,r4)"),
        en_lsr_sel_rd=(0x1416, "loadw", "0xf4004:m,r0"),
        en_lsr_sel_cmp=(0x141E, "cmpw", "$0xc00:m,r0"),
        en_mic_mute=(0x1426, "orw", "$0x8:s,r0"),
        en_mic_mute_st=(0x1428, "storw", "r0,0x0:s(r2,r1)"),
        en_cor_wait=(0x142A, "tbitw", "$0xd:s,0x0:s(r5,r4)"),
        en_off1_rd=(0x142E, "loadw", "0xf580a:m,r0"),
        en_off2_st=(0x1432, "storw", "r0,0xf580e:m"),
        en_dsp_clk_off=(0x143A, "cbitw", "$0x3:s,0x50:m(r1,r0)"),
        isr_entry=(0x27914, "push", "$0x8,r0,RA"),
        isr_ret=(0x2798A, "retx", ""),
        phase_rd=(0x2753C, "loadd", "0xd6:l,(r1,r0)"),
        phase_off=(0x27542, "loadw", "0x38:m(r1,r0),r2"),
        phase_struct=(0x27546, "movd", "$0x224:l,(r1,r0)"),
        phase_cmp=(0x2754E, "cmpw", "r2,r3"),
        phase_update=(0x27564, "storw", "r2,0x14:s(r1,r0)"),
        main_call_dispatch=(0x27172, "bal", "(ra),*+0x27502:m"),
        dispatch_state=(0x27510, "movb", "$0x25:m,r7"),
        codec1_entry=(0xC44, "push", "$0x1,r7"),
        isr_state_rd=(0x27920, "loadb", "0x0:s(r8,r7),r9"),
        isr_state_wr=(0x27926, "storb", "r0,0x0:s(r8,r7)"),
        isr_dsp_base=(0x27928, "loadd", "0xd6:l,(r1,r0)"),
        isr_dsp_int_ptr=(0x2792E, "addd", "$0x58:m,(r1,r0)"),
        isr_dsp_int_rd=(0x27932, "loadw", "0x0:s(r1,r0),r10"),
        isr_dsp_int_clr=(0x27934, "storw", "r10,0x0:s(r1,r0)"),
        codec1_vref=(0xCC8, "movd", "$0xff5804:l,(r3,r2)"),
        codec1_vref_bias=(0xCCE, "cbitw", "$0x7:s,0x0:s(r3,r2)"),
        codec1_vref_pre=(0xCD8, "storw", "r0,0x0:s(r3,r2)"),
        codec1_vref_all=(0xCE6, "sbitw", "$0x4:s,0x0:s(r3,r2)"),
        codec1_delay_st=(0xCE8, "storw", "$0x0:s,0x0:s(sp)"),
        codec1_delay_cmp=(0xCF2, "cmpw", "$0x7d0:m,r2"),
        codec1_mic_base=(0xCF8, "movd", "$0xff5800:l,(r3,r2)"),
        codec1_mic_pd=(0xD24, "cbitw", "$0x2:s,0x0:s(r3,r2)"),
        codec1_lsr_base=(0xD26, "movd", "$0xff5802:l,(r1,r0)"),
        codec1_lsr_att=(0xD32, "storw", "r2,0x0:s(r1,r0)"),
        codec1_lsr_mode_p=(0xD3C, "storw", "r2,0x0:s(r1,r0)"),
        codec1_lsr_mode_n=(0xD48, "storw", "r2,0x0:s(r1,r0)"),
        codec1_lsr_pd=(0xD4E, "cbitw", "$0x2:s,0x0:s(r1,r0)"),
        codec1_lsr_final=(0xD5A, "storw", "r2,0x0:s(r1,r0)"),
        codec1_tone=(0xC9A, "sbitw", "$0x3:s,0xf5806:m"),
        codec_wrap_call=(0xD94, "bal", "(ra),*-0xc44:m"),
        codec_wrap_flag=(0xD98, "tbitb", "$0x0,0x9514:l"),
        codec2_call=(0xDA0, "bal", "(ra),*-0xd60:m"),
        codec2_entry=(0xD60, "movd", "$0xff4838:l,(r1,r0)"),
    ),
}

FLAG_BYTE = {"normal": 0x93CD, "p2test": 0x9514}
STATE_BYTE = {"normal": 0x93CB, "p2test": 0x9512}
FLAG_REG = {"normal": 0x93C8, "p2test": 0x950E}
VECTOR_DSP = {"normal": 29, "p2test": 29}


# ---------------------------------------------------------------------------
# pure helpers (unit-tested)
# ---------------------------------------------------------------------------
def dsp_pc_word(flash_addr):
    """Firmware's own transform for the DSP program counter value."""
    return ((flash_addr >> 1) + 0xC000) & 0xFFFF


def dsp_data_word(cr16_addr):
    """Firmware's own transform for a DSP data-space address (candidate)."""
    return ((cr16_addr >> 1) + 0x8000) & 0xFFFF


def lsratt_gain(value):
    """LSRATT (bits 8-6) gain label under the SC14480 analogy; unknown
    step codes are reported as such, never invented."""
    code = (value >> 6) & 0b111
    return SC14480["lsratt_gain"].get(
        code, f"LSRATT=0b{code:03b} (not in the quoted reference rows)")


def classify_program_source(*, run_present, run_start, run_end, pc_value,
                            copy_loop_found, rom_literal_sites):
    """Classification gate; never silently promotes a guess.

    The only firmware-proven link between the embedded block and the DSP
    is the DSP_PC_START derivation.  That makes the block a *candidate*
    program referenced by the start address — not a proven program and
    not a proven execution mechanism.
    """
    if not run_present:
        return ("DSP_PROGRAM_NOT_IN_IMAGE", "no firmware block at the "
                "derived address")
    if run_end <= run_start:
        return ("DSP_PROGRAM_IMAGE_RUN_EMPTY", "zero-length block")
    base = "DSP_PROGRAM_CANDIDATE_REFERENCED_BY_PC_START"
    if pc_value is None:
        return (base, "no DSP_PC_START value was derived")
    if copy_loop_found:
        return (base + "_COPY_LOOP_CANDIDATE",
                "a copy loop into a microcode window was detected")
    window_like = [a for a in rom_literal_sites
                   if 0x01040000 <= int(a, 16) <= 0x0104FFFF and
                   int(a, 16) % 2 == 0]
    if window_like:
        return (base + "_ROM_WINDOW_CANDIDATE",
                "an even literal inside the SC14480 microcode-ROM window "
                "was detected")
    return (base, "the firmware derives DSP_PC_START from this block "
            "address; the block content, its executability and the "
            "execution mechanism (flash alias vs copy vs ROM) are "
            "unproven")


def find_microcode_copy_candidates(fw):
    """Factual search for CR16 stores/reads touching the SC14480 microcode
    windows.  Returns evidence, not proof: absence only means no resolved
    direct store was found by this scan."""
    ram_window = (0x01030000, 0x01033FFF)
    rom_window = (0x01040000, 0x0104FFFF)
    stores, loads = [], []
    for a, i in fw.insns.items():
        if i.mnemonic not in ("storw", "stord", "storb",
                              "loadw", "loadd", "loadb"):
            continue
        _, parsed = X.address_operand(i)
        if not parsed or parsed[0] != "ABS":
            continue
        addr = X.abs_address(i)
        if addr is None:
            continue
        if ram_window[0] <= addr < ram_window[1] or \
                rom_window[0] <= addr < rom_window[1]:
            (stores if i.mnemonic.startswith("stor") else loads).append(
                f"0x{a:06x}")
    return {"ram_window": [f"0x{ram_window[0]:08x}",
                           f"0x{ram_window[1]:08x}"],
            "rom_window": [f"0x{rom_window[0]:08x}",
                           f"0x{rom_window[1]:08x}"],
            "resolved_direct_stores": sorted(set(stores)),
            "resolved_direct_loads": sorted(set(loads)),
            "status": "NONE_FOUND_BY_THIS_SCAN"}


def decode_fields(value, table, width=16):
    """Return per-field (mask, name) view of a value under an analogy table."""
    return [{"mask": f"0x{mask:04x}", "field": name,
             "value": f"0x{(value & mask) >> (mask & -mask).bit_length() - 1:03x}"}
            for mask, name in sorted(table.items())]


def compose_pcm_ctrl(path_a_bit_ops, path_b_bit_ops):
    """Compose the documented PCM_CTRL bit-op sequence onto a zero reset
    value.  Path A: master; path B: slave synced to external PCM_FSC."""
    a = 0
    for op in path_a_bit_ops:
        kind, bit = op
        a = (a | (1 << bit)) if kind == "s" else (a & ~(1 << bit))
    b = 0
    for op in path_b_bit_ops:
        kind, bit = op
        b = (b | (1 << bit)) if kind == "s" else (b & ~(1 << bit))
    return a, b


# PCM_CTRL bit-op sequences, in firmware order (tail ops common to both paths
# are applied by the caller after the path-specific ops).
PCM_PATH_A = [("c", 1), ("s", 1), ("s", 6), ("c", 7), ("c", 8), ("c", 9),
              ("c", 15), ("s", 0)]
PCM_PATH_B = [("c", 1), ("s", 2), ("c", 4), ("c", 3), ("s", 6),
              ("c", 7), ("c", 8), ("c", 9), ("c", 15), ("s", 0)]


# ---------------------------------------------------------------------------
# shape validation
# ---------------------------------------------------------------------------
def check_shape(fw, name):
    for key, (addr, mnemonic, operands) in SITES[name].items():
        insn = fw.insns.get(addr)
        if insn is None:
            raise ValueError(f"{name}: site {key} @0x{addr:06x} missing")
        if insn.mnemonic != mnemonic or insn.operands != operands:
            raise ValueError(
                f"{name}: site {key} @0x{addr:06x} changed: "
                f"{insn.mnemonic} {insn.operands!r} != {mnemonic} "
                f"{operands!r}")


def cite(fw, addr):
    return T.cite(fw, addr)


def edge(fw, src, dst):
    return any(e.dst == dst and e.category == C.DIRECT_RESOLVED
               for e in C.classify_insn(fw.insns[src], fw))


def call_chain(fw, name, chain):
    """Verify a direct-resolved call chain; returns evidence or problem."""
    ok, steps = True, []
    for src, dst in chain:
        insn = fw.insns[src]
        edges = C.classify_insn(insn, fw)
        hit = [e for e in edges if e.dst == dst and
               e.category == C.DIRECT_RESOLVED and e.kind == "call"]
        steps.append({"from": f"0x{src:06x}", "via": cite(fw, src),
                      "to": f"0x{dst:06x}", "status":
                      "DIRECT_RESOLVED_CALL" if hit else "NOT_RESOLVED"})
        ok = ok and bool(hit)
    return ok, steps


def image_base(fw):
    """Value of [0xD6] in the image (little-endian register pair at 0xD6:
    bytes 80 7f 02 01 -> pair 0x01027F80)."""
    run = fw.run_of(0xD6)
    if run is None:
        raise ValueError("RAM cell 0xD6 not in image")
    lo, data = run
    b = data[0xD6 - lo: 0xD6 - lo + 4]
    low = b[0] | (b[1] << 8)
    high = b[2] | (b[3] << 8)
    return low | (high << 16)


def reg_reference(address):
    """Return SC14480 analogy metadata for a firmware architectural address."""
    name = SC14480["peripheral"].get(address)
    if name is not None:
        return {"reference_name": name,
                "status": "SC14480_ANALOGY_UNVERIFIED_SC14448"}
    if DSP_WINDOW[0] <= address < DSP_WINDOW[1]:
        off = address - DSP_WINDOW[0]
        ref = SC14480["dsp_window"].get(off)
        return {"reference_name": ref if ref else
                "UNMAPPED_IN_SC14480_REFERENCE",
                "status": "SC14480_ANALOGY_UNVERIFIED_SC14448"}
    return {"reference_name": None, "status": "NO_REFERENCE_ENTRY"}


# ---------------------------------------------------------------------------
# per-image analysis
# ---------------------------------------------------------------------------
def analyze(name, fw, mem, df):
    check_shape(fw, name)
    s = SITES[name]
    base = image_base(fw)
    if base != DSP_BASE:
        raise ValueError(f"{name}: [0xD6] = 0x{base:08x}, expected "
                         f"0x{DSP_BASE:08x}")
    flag_byte = FLAG_BYTE[name]
    state_byte = STATE_BYTE[name]
    flag_image_value = (f"0x{mem[flag_byte]:02x}"
                        if flag_byte in mem else "NOT_IN_IMAGE")

    common = dict(image=name, firmware_sha256=A.REFERENCE_SHA[name],
                  analysis_status="CONVERGED_BOUNDED_PATHS",
                  base_cell="0x00d6",
                  base_cell_image_value=f"0x{DSP_BASE:08x}",
                  base_cell_guard=f"cmpd $0x1027f80 at "
                                  f"0x{s['dsp_init_guard'][0]:06x} "
                                  f"({name})")

    def unresolved(extra):
        return [
            "SC14448 register identity is not proven; every register name is "
            "an SC14480 related-device analogy",
            "external/indirect writers of the [0xD6] base cell are not "
            "excluded; the init guard re-reads it after calls",
            f"call {name} 0x{s['cfg_helper_call'][0]:06x} targets "
            "0x182e/0x12b0, which is not on a decoded instruction boundary "
            "(helper body only locally consistent)",
            "the DSP executes microcode whose internal data flow cannot be "
            "verified offline (no DSP disassembler, no documented SC14448 "
            "map)",
            "no all-path proof that no other code writes the DSP window",
        ] + extra

    # ---- E5-A: DSP register window accesses -------------------------------
    # dsp_init: [0xD6] guard, DSP_CTRL pd, DSP_INT clear, DSP_PC_START store
    dsp_init_seq = [
        ("guard_compare", s["dsp_init_guard"],
         "DSP_BASE == [0xD6] else skip whole function", None, None),
        ("dip_ctrl_write", s["dsp_init_dip_store"],
         "value = 0x80 when caller passes r2!=0 (proven: movb $1,r2 at "
         "0x%06x)" % s["pad_set_r2"][0], 0x00FF6006, "0x80"),
        ("dsp_ctrl_powerdown", s["dsp_init_ctrl_pd"],
         "clear DSP_CTRL bit2 (DSP_EN=0 under analogy)", DSP_BASE + 0x50,
         "bit2=0"),
        ("codec_adda_powerdown", s["dsp_init_adda_store"],
         "CODEC_ADDA |= 3 (AD_PD=1, DA_PD=1 under analogy)", 0x00FF5808,
         "or 0x3"),
        ("dsp_int_clear", s["dsp_init_int_clear"],
         "DSP_INT = 0xFFFF (write-1-to-clear semantics under analogy)",
         DSP_BASE + 0x58, "0xffff"),
        ("clk_codec_off", s["dsp_init_clk_codec_off"],
         "CLK_CODEC = 0 (all codec/PCM/main clocks off under analogy)",
         0x00FF4004, "0x0000"),
        ("call_codec_clock_init", s["dsp_init_call_clk"],
         "direct call to the codec-clock init", None, None),
        ("call_post_init", s["dsp_init_call_post"],
         "direct call to the post-init helper (data region/status)",
         None, None),
        ("dsp_pc_literal", s["dsp_init_pc_lit"],
         "flash address of the embedded DSP program block", None, "0x17300"),
        ("dsp_pc_shift_add", s["dsp_init_pc_add"],
         "DSP_PC = ((0x17300 >> 1) + 0xC000) & 0xFFFF = 0x7980",
         DSP_BASE + 0x54, "0x7980"),
        ("dsp_pc_store", s["dsp_init_pc_store"],
         "DSP_PC_START = 0x7980", DSP_BASE + 0x54, "0x7980"),
    ]
    dsp_accesses = []
    for label, site, why, addr, value in dsp_init_seq:
        dsp_accesses.append(dict(label=label, why=why, **cite(fw, site[0]),
                                 effective_address=(
                                     f"0x{addr:08x}" if addr is not None
                                     else None),
                                 value_or_bitop=value,
                                 register_analogy=(reg_reference(addr)
                                                   if addr is not None
                                                   else None),
                                 function=f"0x{s['dsp_init_entry'][0]:06x}"))

    # f_dsp_cfg (0x1856 / 0x12d8)
    cfg_sites = [
        ("main_sync1_zero", s["cfg_sync1_zero"], DSP_BASE + 0x02, "0x0000"),
        ("helper_patch_call", s["cfg_helper_call"], None, "r2=0x7c00, "
         "target address unresolved"),
        ("dsp_int_prio1", s["cfg_prio1_store"], DSP_BASE + 0x5C, "0x0773"),
        ("main_ctrl_400", s["cfg_main_store"], DSP_BASE + 0x3C, "0x0400"),
        ("clk_amba_bit7", s["cfg_amba"], 0x00FF4000, "bit7=1"),
        ("dsp_ctrl_enable", s["cfg_ctrl_store"], DSP_BASE + 0x50,
         "or 0xC (DSP_CLK_EN|DSP_EN under analogy)"),
        ("dsp_ctrl_dbg", s["cfg_dbg"], DSP_BASE + 0x50, "bit8=1 (DBG_EN)"),
    ]
    for label, site, addr, value in cfg_sites:
        dsp_accesses.append(dict(label=label, **cite(fw, site[0]),
                                 effective_address=(
                                     f"0x{addr:08x}" if addr is not None
                                     else None),
                                 value_or_bitop=value,
                                 register_analogy=(reg_reference(addr)
                                                   if addr is not None
                                                   else None),
                                 function=f"0x{s['cfg_entry'][0]:06x}"))

    # f_enable (0x190e / 0x1390)
    en_sites = [
        ("int_prio_or30", s["en_prio_store"], 0x00FF5404, "or 0x30"),
        ("pending_2000", s["en_pending"], 0x00FF5402, "0x2000"),
        ("dsp_int_mask", s["en_mask_store"], DSP_BASE + 0x5A,
         "or 0x803c"),
        ("clk_dsp_9", s["en_clk_dsp"], 0x00FF4006, "0x0009"),
        ("dsp_en", s["en_dsp_en"], DSP_BASE + 0x50, "bit2=1 (DSP_EN)"),
        ("adda_on", s["en_adda_store"], 0x00FF5808, "and 0x7ffc "
         "(AD_PD=0, DA_PD=0)"),
        ("vref_init_0", s["en_vref_init0"], 0x00FF5804, "bit4=0 "
         "(VREF_INIT off after precharge)"),
        ("main_ctrl_400b", s["en_main_store"], DSP_BASE + 0x3C, "0x0400"),
        ("call_clk2", s["en_call_clk2"], None, "r2=4"),
        ("call_cfg", s["en_call_cfg"], None, None),
        ("codec_test_cor", s["en_test_cor"], 0x00FF580C, "bit12=1 (COR_ON)"),
        ("mic_mute_cond", s["en_mic_mute_st"], 0x00FF5800,
         "conditional or 0x8 (MIC_MUTE) when CLK_DA_LSR_SEL==11"),
        ("offset_copy", s["en_off2_st"], 0x00FF580E,
         "value read from CODEC_OFFSET1"),
        ("dsp_clk_off", s["en_dsp_clk_off"], DSP_BASE + 0x50,
         "bit3=0 (DSP_CLK_EN gated after bring-up)"),
    ]
    for label, site, addr, value in en_sites:
        dsp_accesses.append(dict(label=label, **cite(fw, site[0]),
                                 effective_address=(
                                     f"0x{addr:08x}" if addr is not None
                                     else None),
                                 value_or_bitop=value,
                                 register_analogy=(reg_reference(addr)
                                                   if addr is not None
                                                   else None),
                                 function=f"0x{s['en_entry'][0]:06x}"))

    # runtime observers
    runtime = {
        "dsp_isr": {
            "vector_index": VECTOR_DSP[name],
            "vector_reference_name": "dsp_int (reference numbering)",
            "state_byte": f"0x{state_byte:04x}",
            "state_byte_written_value": "0x28",
            "dsp_int_read_clear": cite(fw, s["isr_dsp_int_clr"][0]),
            "vector_bit3_call": "0x3b28" if name == "normal" else "0x27744",
            "vector_bit2_call": "0x3b38" if name == "normal" else "0x27754",
            "end_instruction": cite(fw, s["isr_ret"][0]),
            "status": "PROVEN_FIRMWARE_HANDLER",
        },
        "phase_info_monitor": {
            "read_site": cite(fw, s["phase_off"][0]),
            "effective_address": f"0x{DSP_BASE + 0x38:08x}",
            "structure": s["phase_struct"][0],
            "status": "PROVEN_FIRMWARE_READ; main -> dispatcher (direct "
                      "call) -> monitor block (direct fallthrough) edges "
                      "verified",
        },
    }
    ok_chain, en_chain = call_chain(fw, name, [
        (s["call_enable_chain"][0], 0x1A0A if name == "normal" else 0x1440),
        (s["call_enable"][0], s["en_entry"][0])])
    ok_pad, pad_chain = call_chain(fw, name, [
        (s["call_pad_init"][0], 0x1388 if name == "normal" else 0x0DFE),
        (s["pad_call_dsp_init"][0], s["dsp_init_entry"][0])])
    ok_codec, codec_chain = call_chain(fw, name, [
        (s["call_codec_gpio"][0], 0x131C if name == "normal" else 0x0D92),
        (s["codec_wrap_call"][0], s["codec1_entry"][0])])
    dsp_regs = dict(common, instruction_provenance=dsp_accesses,
        control_flow_evidence={
            "main_to_dsp_init_chain": pad_chain,
            "main_to_dsp_init_chain_status":
            "PROVEN" if ok_pad else "NOT_RESOLVED",
            "main_to_enable_chain": en_chain,
            "main_to_enable_chain_status":
            "PROVEN" if ok_chain else "NOT_RESOLVED",
            "main_to_codec_chain": codec_chain,
            "main_to_codec_chain_status":
            "PROVEN" if ok_codec else "NOT_RESOLVED",
            "base_guard_instruction": cite(fw, s["dsp_init_guard"][0]),
            "runtime_dsp_observers": runtime},
        dataflow_evidence={
            "base_cell_address_expression": "[0xD6]+offset",
            "base_cell_guard_check": "cmpd $0x1027f80,([0xD6])",
            "dsp_pc_start_value": "0x7980",
            "dsp_pc_formula": "((0x17300>>1)+0xC000)&0xffff"},
        related_device_evidence={"status": "SC14480_ANALOGY_ONLY",
                                 "source": SC14480["source"]},
        unresolved_paths=unresolved([
            "the 0x7c00 helper patch target (r4,r3) is not resolved from "
            "any caller of the DSP config function",
            "no CR16-side DSP_CR16_INT (bit4) write site was found in "
            "either image; under the SC14480 analogy the main counter "
            "(started on DIP <A_NORM> via DSP_MAIN_CTRL=0x0400) supplies "
            "the periodic 8 kHz DSP_SYNC0-2 start sources; other trigger "
            "sources (a CR16 bit4 write elsewhere, DIP interrupts) are "
            "not excluded",
            "SC14448 meaning of [0xD6]+0x64 (written 0x0001) is not in the "
            "SC14480 reference tables"]),
        confidence="PROVEN_FIRMWARE_ACCESSES_WITH_REFERENCE_ANALOGIES")

    # ---- E5-B: DSP program source -----------------------------------------
    runs = fw.runs
    prog_runs = [(lo, data) for lo, data in runs
                 if lo == 0x17300 or (0x17300 <= lo < 0x18000)]
    prog_run = next(((lo, d) for lo, d in prog_runs if lo == 0x17300),
                    None)
    block = {
        "run_present": prog_run is not None,
        "run_start": f"0x{prog_run[0]:06x}" if prog_run else None,
        "run_end_exclusive": (f"0x{prog_run[0] + len(prog_run[1]):06x}"
                              if prog_run else None),
        "byte_length": len(prog_run[1]) if prog_run else 0,
        "word_length": len(prog_run[1]) // 2 if prog_run else 0,
        "first_bytes": prog_run[1][:16].hex() if prog_run else None,
        "block_sha256": (hashlib.sha256(
            prog_run[1]).hexdigest() if prog_run else None),
        "trailer_run": [(f"0x{lo:06x}", f"0x{lo + len(d):06x}")
                        for lo, d in prog_runs if lo != 0x17300],
    }
    pc_value = dsp_pc_word(0x17300)
    if pc_value != 0x7980:
        raise ValueError(f"{name}: DSP_PC transform changed")
    # factual searches: copy candidates into the microcode windows, ROM
    # literals, and the transform sites (absence is recorded, not proof)
    copy_search = find_microcode_copy_candidates(fw)
    copy_literals = [f"0x{a:06x}" for a, i in fw.insns.items()
                     if i.mnemonic == "movd" and
                     ("$0x103" in i.operands or "$0x104" in i.operands)]
    data_transform_sites = [f"0x{a:06x}" for a, i in fw.insns.items()
                            if i.mnemonic == "addw" and
                            "$0x8000" in i.operands]
    program_transform_sites = [f"0x{a:06x}" for a, i in fw.insns.items()
                               if i.mnemonic == "addw" and
                               "$0xc000" in i.operands]
    # Table 63 (SC14480) comparison: the firmware transform is identical to
    # the table's linear rule DSP = (CR16>>1) - 0x4000 (mod 2^16), and the
    # block's CR16 range lies in the table's *Reserved* microcode row.
    table63_rows = SC14480["table63_rows"]
    cr16_word = 0x17300
    region_row = [r for r in table63_rows
                  if int(r["cr16"].split("-")[0], 16) <= cr16_word <=
                  int(r["cr16"].split("-")[1], 16)]
    table63 = {
        "rows": table63_rows,
        "linear_rule": "DSP = (CR16 >> 1) - 0x4000 (mod 2^16)",
        "firmware_transform_identical_to_linear_rule": True,
        "block_cr16_address": f"0x{cr16_word:06x}",
        "block_table63_region": (region_row[0]["meaning"] + " ("
                                  + region_row[0]["cr16"] + " -> "
                                  + region_row[0]["dsp"] + ")")
        if region_row else "OUTSIDE_ALL_SC14480_TABLE63_ROWS",
        "table63_conflict": "under the SC14480 map the block lies in a "
                            "microcode region marked Reserved, not in the "
                            "active shared-RAM row; the SC14448 memory "
                            "organisation is unknown and the whole "
                            "second-level image (code at 0x0+) does not "
                            "fit the SC14480 program-flash map either",
    }
    kind, why = classify_program_source(
        run_present=block["run_present"],
        run_start=0x17300, run_end=0x17300 + block["byte_length"],
        pc_value=pc_value,
        copy_loop_found=bool(copy_search["resolved_direct_stores"]),
        rom_literal_sites=copy_literals)
    dsp_prog = dict(common, instruction_provenance=[
        cite(fw, a) for a in (s["dsp_init_pc_lit"][0],
                              s["dsp_init_pc_shift"][0],
                              s["dsp_init_pc_add"][0],
                              s["dsp_init_pc_store"][0])],
        dataflow_evidence={
            "embedded_block": block,
            "dsp_pc_start_value": f"0x{pc_value:04x}",
            "transform": "DSP_PC = ((flash_addr >> 1) + 0xC000) & 0xFFFF "
                         "(firmware arithmetic, verified in both images; "
                         "identical to the SC14480 Table 63 linear rule "
                         "DSP = (CR16>>1) - 0x4000 mod 2^16)",
            "program_source_classification": kind,
            "program_source_why": why,
            "block_content_validation": "NONE: the block is not decoded "
                                        "as DSP instructions; no opcode/"
                                        "structure check exists",
            "microcode_ram_literal_sites": copy_literals,
            "microcode_rom_literal_sites": copy_literals,
            "microcode_window_copy_search": copy_search,
            "dsp_data_space_transform_sites": data_transform_sites,
            "dsp_program_space_transform_sites": program_transform_sites,
            "dsp_data_space_transform": "DSP_ADDR = ((cr16_addr >> 1) + "
                                        "0x8000) & 0xFFFF (candidate)",
            "sc14480_table63": table63},
        unresolved_paths=unresolved([
            "whether the Gen2DSP executes the 0x17300 block in place "
            "(flash alias), from a copy, or from internal ROM is unproven; "
            "the PC derivation only proves the start address arithmetic",
            "the DSP microcode itself is not disassembled and its "
            "PCM/CODEC data flow cannot be verified offline",
            "normal and p2test embed different-sized blocks "
            "(0xB7A vs 0x6FA bytes); the difference is not explained",
            "under the SC14480 Table 63 the block's CR16 range is a "
            "Reserved microcode region, not the active shared-RAM row; "
            "the SC14448 organisation is unknown"]),
        confidence="FIRMWARE_DERIVATION_PROVEN_EXECUTION_MECHANISM_UNKNOWN")

    # ---- E5-C: PCM routing -------------------------------------------------
    pcm_a, pcm_b = compose_pcm_ctrl(PCM_PATH_A, PCM_PATH_B)
    pcm_routing = dict(common, instruction_provenance=[
        cite(fw, s[k][0]) for k in (
            "clk_hlp3_call", "clk_pcm_write2", "clk_pcm_bit6",
            "clk_path_b_cbit1", "clk_path_b_sbit2", "clk_pcm_en",
            "clk_dip2_resume", "clk_codec_pcm_en", "clk_codec_bit9",
            "phase_off")],
        dataflow_evidence={
            "pcm_ctrl_effective_address": f"0x{DSP_BASE + 0x36:08x}",
            "pcm_ctrl_path_a_ops": [dict(op=o, bit=b)
                                    for o, b in PCM_PATH_A],
            "pcm_ctrl_path_a_composed": f"0x{pcm_a:04x}",
            "pcm_ctrl_path_a_mode":
            "PCM_MASTER=1, PCM_PPOD=1, PCM_EN=1 (SC14480 analogy)",
            "pcm_ctrl_path_b_ops": [dict(op=o, bit=b)
                                    for o, b in PCM_PATH_B],
            "pcm_ctrl_path_b_composed": f"0x{pcm_b:04x}",
            "pcm_ctrl_path_b_mode":
            "PCM_MASTER=0, DSP_PCM_SYNC=1, PCM_PPOD=1, PCM_EN=1 "
            "(slave synced to external PCM_FSC; SC14480 analogy)",
            "pcm_ctrl_fscdel_conditional":
            "PCM_FSC0DEL = not flag_byte bit3 (runtime-selected)",
            "path_select": "flag_byte bit0 (0 = path A master, 1 = path B "
                           "slave)",
            "flag_byte": f"0x{flag_byte:04x}",
            "flag_byte_image_value": flag_image_value,
            "flag_byte_producer": "return value of helper call "
                                   "(0x3cbe/0x278da wrapper, r2=7) stored "
                                   "by the clock init",
            "clk_codec_pcm_en": "bit14=1 (CLK_PCM_EN under analogy)",
            "clk_codec_pcm_sel": "bit8=0; bit9 = flag_byte bit3 -> "
                                 "1.152 MHz or 2.304 MHz PCM_CLK under "
                                 "the SC14480 divider analogy",
            "main_sync1_pcm_sync": "0x3fff mask leaves PCM_SYNC=00 -> "
                                   "8 kHz frame (SC14480 analogy)",
            "dip_ctrl2_slotcnt_res": "bit8=1 (DIP slot counter resumes "
                                     "with the DSP main counter)",
            "phase_info_monitor": runtime["phase_info_monitor"],
            "interface_mismatch_with_linux": [
                "Linux OEM side: 8 x 16-bit slots, nominal BCLK 1.024 MHz",
                "SC14448 firmware (SC14480 analogy): 4 PCM channels, "
                "PCM_CLK 1.152/2.304 MHz, 8 kHz frame",
                "these are different interfaces; no slot mapping is proven"]},
        related_device_evidence={"status": "SC14480_ANALOGY_ONLY",
                                 "source": SC14480["source"]},
        unresolved_paths=unresolved([
            "no instruction-level PCM_INx/CODEC_IN data flow is provable: "
            "the DSP microcode performs the PCM<->CODEC conversion",
            "the IPQ4019 TDM slot-to-SC14448 channel mapping is unknown",
            "slot 5 is not claimed as any consumer; the FON control-word "
            "question stays open (Q46/Q55)"]),
        confidence="CONFIGURATION_PROVEN_DATA_PATH_UNVERIFIED")

    # ---- E5-D: CODEC init --------------------------------------------------
    codec1 = [dict(label=k, **cite(fw, s[k][0]),
                   effective_address=addr, value_or_bitop=v)
              for k, addr, v in (
                  ("codec1_tone", 0x00FF5806, "bit3=1 (RNG_PR_DIS)"),
                  ("codec1_vref_bias", 0x00FF5804, "bit7=0 (BIAS_PD off)"),
                  ("codec1_vref_pre", 0x00FF5804,
                   "or 0x4 (VREF_INIT=1 precharge)"),
                  ("codec1_vref_all", 0x00FF5804,
                   "bits 8,9,6,5,1,0 cleared, bit4 set"),
                  ("codec1_mic_pd", 0x00FF5800, "bit2=0 (MIC_PD off)"),
                  ("codec1_lsr_att", 0x00FF5802,
                   "or 0x1c0 (LSRATT=111 -> -12 dB, Table 113)"),
                  ("codec1_lsr_mode_p", 0x00FF5802,
                   "LSRP_MODE=10 differential DA+"),
                  ("codec1_lsr_mode_n", 0x00FF5802,
                   "LSRN_MODE=10 differential DA-"),
                  ("codec1_lsr_pd", 0x00FF5802, "bit2=0 (LSRP_PD off)"),
                  ("codec1_lsr_final", 0x00FF5802,
                   lsratt_gain(0x40) + " (LSRATT=001)"),
              )]
    en_codec = [dict(label=k, **cite(fw, s[k][0]), effective_address=addr,
                     value_or_bitop=v)
                for k, addr, v in (
                    ("dsp_init_adda_store", 0x00FF5808,
                     "or 3 (AD_PD=1, DA_PD=1: converters powered down)"),
                    ("en_adda_store", 0x00FF5808,
                     "and 0x7ffc (AD_PD=0, DA_PD=0: converters on)"),
                    ("en_vref_init0", 0x00FF5804,
                     "bit4=0 (VREF_INIT off after precharge)"),
                    ("en_test_cor", 0x00FF580C, "bit12=1 (COR_ON)"),
                    ("en_mic_mute_st", 0x00FF5800,
                     "conditional or 0x8 (MIC_MUTE) during offset "
                     "measurement"),
                    ("en_off2_st", 0x00FF580E,
                     "OFFSET1 value copied to OFFSET2") )]
    codec_init = dict(common, instruction_provenance=codec1 + en_codec,
        dataflow_evidence={
            "part1_function": f"0x{s['codec1_entry'][0]:06x}",
            "part1_chain_status": "PROVEN" if ok_codec else "NOT_RESOLVED",
            "vref_sequence_matches_reference_order":
            "bias on -> VREF_INIT=1 precharge -> delay loop (0x7d0 "
            "iterations) -> MIC/LSR amplifiers on; the reference "
            "SC14480 note 57 recommends the same order with >=100us wait",
            "powerdown_then_powerup_pair": "init or 3 on CODEC_ADDA; "
            "runtime enable and 0x7ffc on CODEC_ADDA",
            "mic_config": "single-ended MICp (MIC_MODE=01), gain 0 dB "
                          "(MIC_GAIN=0000), controlled by MIC_GAIN "
                          "(DSP_CTRL bit10=0)",
            "lsr_config": "differential DA to LSR+/LSR-, amplifiers on, "
                          "final LSRATT=001 -> 0 dB nominal (SC14480 "
                          "Table 299), after an intermediate LSRATT=111 "
                          "(-12 dB) step",
            "tone_config": "RNG_PR_DIS=1 (RING protection diodes "
                           "disabled), CID_PR_DIS=1 (set in pad init)",
            "pad_gpio_sites": [cite(fw, s[k][0]) for k in
                               ("clk_pad", "clk_gpio2_dir",
                                "clk_gpio2_mode", "clk_gpio3_dir",
                                "clk_gpio3_mode")],
            "delay_loop_site": cite(fw, s["codec1_delay_st"][0])},
        related_device_evidence={"status": "SC14480_ANALOGY_ONLY",
                                 "source": SC14480["source"]},
        unresolved_paths=unresolved([
            "no proved audio routing from PCM through DSP to the codec "
            "DAC: the CODEC register writes only prove converter/amplifier "
            "configuration",
            "analog line control (FON) is not reachable from any proved "
            "command path; the TONE/RING bits are only reference analogies"]),
        confidence="REGISTER_SEQUENCE_PROVEN_PHYSICAL_AUDIO_UNOBSERVED")

    # ---- E5-E: clock dependencies ------------------------------------------
    clk = dict(common, instruction_provenance=[
        cite(fw, s[k][0]) for k in (
            "dsp_init_ctrl_pd", "clk2_pll_clr3", "clk2_pll_800",
            "clk2_pll_852", "clk2_pll_sbit3", "clk2_codec_div",
            "clk2_per_div", "clk2_per10", "clk2_dsp", "clk2_pll_div",
            "cfg_main_store", "en_main_store", "cfg_amba",
            "dsp_init_dip_store", "clk_dip2_resume", "en_dsp_clk_off")],
        dataflow_evidence={
            "dsp_main_ctrl_value": "0x0400",
            "dsp_main_ctrl_analogy": SC14480["dsp_main_ctrl_bits"][0x400],
            "dsp_main_ctrl_dependency_class":
            "MAIN_COUNTER_DIP_DEPENDENT_START (the *main counter*, not the "
            "DSP itself, is configured to start on DIP <A_NORM> under the "
            "SC14480 analogy; the counter generates the 8 kHz audio syncs)",
            "main_sync1_value": "0x0000 -> all audio interfaces at 8 kHz "
                                "under the SC14480 analogy; DSP_SYNC0-2 = "
                                "8 kHz periodic DSP start/interrupt "
                                "(one of several DSP start sources in the "
                                "reference: DSP_SYNC, CR16 trigger, DIP "
                                "interrupt)",
            "dsp_trigger_sources_not_excluded": [
                "CR16 DSP_CR16_INT (bit4) writes elsewhere or via "
                "indirect paths",
                "DIP interrupt triggers",
                "main-counter DSP_SYNC0-2 once the counter runs",
            ],
            "pll_sequence": ["0x0000 -> 0x0800 -> 0x0852 -> 0x085A "
                             "(CLK_PLL_CTRL with delays)"],
            "clk_dsp": "0x0009 (CLK_DSP_EN=1, divider 1 under analogy)",
            "clk_codec_div": "0x0009", "clk_per_div": "0x0009",
            "clk_per10_div": "0x0021", "clk_pll_div": "0x001c",
            "dip_ctrl_ur_stop": "0x80 written twice (DIP stopped before "
                                "clock/DSP reconfiguration under analogy)",
            "dip_ctrl2_slotcnt_res": "bit8=1 (slot counter follows the "
                                     "main counter)",
            "dsp_clk_gated_after_bringup": "DSP_CTRL bit3 cleared at the "
                                           "end of the enable sequence",
            "dependency_analysis": [
                {"aspect": "shared clock source",
                 "status": "PROVEN_FIRMWARE_CONFIG: PLL/codec/peripheral/"
                           "DSP dividers programmed in the audio path"},
                {"aspect": "shared initialization",
                 "status": "PROVEN_FIRMWARE_CONFIG: DSP init stops the DIP "
                           "and sets SLOTCNT_RES"},
                {"aspect": "audio timing vs DECT runtime",
                 "status": "RUNTIME_VERIFICATION_REQUIRED: DSP_MAIN_CTRL="
                           "0x400 selects DIP-synchronised start in the "
                           "SC14480 analogy; whether the DIP must be "
                           "radio-active or only issue <A_NORM> is not "
                           "decidable offline"},
            ]},
        related_device_evidence={"status": "SC14480_ANALOGY_ONLY",
                                 "source": SC14480["source"]},
        unresolved_paths=unresolved([
            "SC14448 register identity unproven; DIP/A_NORM behaviour is "
            "an SC14480 analogy",
            "the DIP sequencer program (E3.3 fill loop) is not decoded, "
            "so whether <A_NORM> is ever issued is unknown"]),
        confidence="FIRMWARE_CONFIG_PROVEN_DECT_RUNTIME_DEPENDENCE_UNRESOLVED")

    # ---- E5-F: readiness ---------------------------------------------------
    def ready(kind, seq, vals, hw, offline, rt, blocker):
        return {"component": kind,
                "oem_sequence_known": seq,
                "register_values_known": vals,
                "hardware_dependencies_known": hw,
                "offline_implementation_possible": offline,
                "runtime_confirmation_required": rt,
                "blocker": blocker}

    readiness = dict(common,
        dataflow_evidence={"components": [
            ready("SC14448 reset/boot", "PARTIALLY (bootloader handshake "
                  "separate)", "NO", "NO", "LIMITED",
                  "YES", "first-level loader and reset vector semantics"),
            ready("firmware loading", "PARTIALLY (second-level image "
                  "loads at fixed addresses including the 0x17300 DSP "
                  "block)", "NO", "NO", "LIMITED", "YES",
                  "loader protocol not fully recovered"),
            ready("clock initialization",
                  "PROVEN_FIRMWARE_CONFIG (PLL sequence, CODEC/PER/DSP "
                  "dividers, CLK_AMBA)", "PROVEN (values above)",
                  "SC14480_ANALOGY", "YES (values known)",
                  "YES (SC14448 divider semantics)",
                  "register identity analogy"),
            ready("PCM+ configuration",
                  "PROVEN_FIRMWARE_CONFIG (master/slave paths, 8 kHz "
                  "frame, PCM_CLK select)", "PROVEN (PCM_CTRL 0x43/0x45)",
                  "SC14480_ANALOGY", "PARTIALLY", "YES",
                  "IPQ4019 slot/clock mismatch unproven"),
            ready("DSP initialization",
                  "PROVEN_FIRMWARE_CONFIG (powerdown->program->enable, "
                  "PC_START=0x7980)", "PROVEN", "SC14480_ANALOGY",
                  "YES", "YES",
                  "DSP execution mechanism (flash alias vs copy vs ROM)"),
            ready("CODEC initialization",
                  "PROVEN_FIRMWARE_CONFIG (VREF->MIC->LSR->ADDA powerup "
                  "order)", "PROVEN (bit sequences)", "SC14480_ANALOGY",
                  "YES", "YES", "register identity analogy"),
            ready("audio routing",
                  "UNRESOLVED (inside DSP microcode)",
                  "NO", "NO", "NO", "YES",
                  "DSP program not disassembled; no SC14448 DSP doc"),
            ready("analog line control",
                  "NOT_REACHED (no proved command path)",
                  "NO", "NO", "NO", "YES",
                  "no producer-backed FON command path (E4.2)"),
        ]},
        unresolved_paths=unresolved([
            "the OEM firmware can be used as a closed DSP/CODEC engine "
            "only if the recovered register values hold on the SC14448 "
            "and the DSP program start is valid; neither is proven",
            "no runtime audio test may be designed from register writes "
            "alone (K1/K2 NO-GO unchanged)"]),
        confidence="INVENTORY")

    return (dsp_regs, dsp_init_report(name, fw, s, common, unresolved,
                                       ok_pad, ok_chain, ok_codec, df),
            dsp_prog, pcm_routing, codec_init, clk, readiness)


def dsp_init_report(name, fw, s, common, unresolved, ok_pad, ok_chain,
                    ok_codec, df):
    stages = [
        ("clock/reset stop", [s["dsp_init_ctrl_pd"], s["dsp_init_dip_store"]],
         "DSP powered down, DIP sequencer stopped"),
        ("interrupt/state clear", [s["dsp_init_int_clear"],
                                   s["dsp_init_adda_store"]],
         "DSP_INT cleared (0xFFFF), CODEC converters powered down"),
        ("clock source off", [s["dsp_init_clk_codec_off"]],
         "CLK_CODEC=0 before reconfiguration"),
        ("codec clock init", [s["dsp_init_call_clk"], s["clk_entry"]],
         "direct call into the PLL/codec-clock configuration"),
        ("post init", [s["dsp_init_call_post"]],
         "direct call to the post-init helper"),
        ("DSP program selection", [s["dsp_init_pc_lit"],
                                   s["dsp_init_pc_add"],
                                   s["dsp_init_pc_store"]],
         "DSP_PC_START = ((0x17300>>1)+0xC000)&0xffff = 0x7980"),
        ("runtime enable", [s["en_entry"], s["en_dsp_en"],
                            s["en_call_clk2"], s["en_call_cfg"],
                            s["en_adda_store"], s["en_vref_init0"],
                            s["en_dsp_clk_off"]],
         "DSP_EN=1, INT_MASK|=0x803c, CLK_DSP=9, MAIN_CTRL=0x400, "
         "CODEC AD/DA on, VREF_INIT=0, final DSP_CLK gate off"),
    ]
    seq = []
    for label, sites, why in stages:
        seq.append({"stage": label, "evidence": [cite(fw, a[0])
                                                 for a in sites],
                    "why": why})
    return dict(common,
        instruction_provenance=[cite(fw, a[0]) for _, sites, _ in stages
                                for a in sites],
        control_flow_evidence={
            "main_to_dsp_init": "PROVEN" if ok_pad else "NOT_RESOLVED",
            "main_to_enable": "PROVEN" if ok_chain else "NOT_RESOLVED",
            "main_to_codec": "PROVEN" if ok_codec else "NOT_RESOLVED",
            "enable_calls_clk2_with_r2_4": cite(fw, s["en_r2_4"][0]),
            "clk2_r2_4_path_is_taken": "PROVEN_FROM_THIS_CALLER",
            "unknown_callers_of_clk2": "other callers may exercise the "
                                       "r2!=4 skip path",
            "convergence": df.get("converged") is True},
        dataflow_evidence={"stages": seq},
        related_device_evidence={"status": "SC14480_ANALOGY_ONLY",
                                 "source": SC14480["source"]},
        unresolved_paths=unresolved([
            "the post-init call (0x688/0x4e2) semantics are not analysed "
            "(data-region helper)",
            "ordering across interrupts is not modelled; the init "
            "functions run with interrupts disabled only in parts"]),
        confidence="SEQUENCE_PROVEN_PER_STAGE_VALUES_PROVEN")


# ---------------------------------------------------------------------------
# build / publish
# ---------------------------------------------------------------------------
def build(objdump):
    A._validate_inputs(objdump)
    data = [{} for _ in NAMES]
    for name, path in A.IMAGES:
        df, fw, rows = D.run_image(name, path, objdump)
        if df.get("converged") is not True or \
                df.get("analysis_status") != "CONVERGED":
            raise ValueError(f"{name}: NON_CONVERGED")
        mem, *_ = parse_ihex(path, strict=True)
        for d, v in zip(data, analyze(name, fw, mem, df)):
            d[name] = v
    if any(set(d) != set(A.REFERENCE_SHA) for d in data):
        raise ValueError("incomplete E5 bundle")
    return {fn: {"tool": "cr16-audio-architecture/1", "images": d}
            for fn, d in zip(NAMES, data)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--objdump", default=str(A.OBJDUMP))
    ap.add_argument("--out", default=str(ROOT / "tools" / "reports"))
    args = ap.parse_args(argv)
    try:
        T.publish(Path(args.out), build(args.objdump))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "cr16-e5.incomplete.json").write_text(json.dumps(
            {"analysis_status": "INCOMPLETE", "reason": str(exc)},
            indent=2) + "\n")
        print(f"INCOMPLETE E5: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
