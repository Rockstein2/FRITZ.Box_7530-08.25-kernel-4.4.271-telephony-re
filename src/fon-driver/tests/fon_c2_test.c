// SPDX-License-Identifier: GPL-2.0-only
/*
 * Host-side tests for the Stage C2 readback logic.
 *
 * The kernel-side fon_c2.c cannot be compiled on the host (it needs
 * platform_device, clk, reset and io.h), so the parts that decide success
 * are factored into pure helpers here and tested directly:
 *
 *   - the register values C2 writes;
 *   - the comparison that decides tdm_ok / audio_mode_ok / stereo_*_ok;
 *   - the "all_ok" rule.
 *
 * Every fault branch is covered by feeding a modified readback.
 */

#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "fon_c2_bits.h"

static int fails;

#define CHECK(cond, msg) do { \
	if (cond) { \
		printf("PASS %s\n", msg); \
	} else { \
		printf("FAIL %s\n", msg); \
		fails++; \
	} \
} while (0)

/* ---- values C2 must produce from the reset snapshot ------------------- */

static void test_written_values(void)
{
	/* Reset snapshot observed on hardware in C1. */
	const u32 before_mode = 0x00000000;
	const u32 before_stereo = 0x00000102;
	u32 tdm, mode, st;

	tdm = fon_c2_tdm_value(8);
	CHECK(tdm == 0x06070007, "tdm value for 8 slots is 0x06070007");

	mode = fon_c2_audio_mode_value(before_mode, true, true, true);
	CHECK(mode == 0x10000005, "audio_mode value is 0x10000005");
	/* BIT(0) is the XMIT TDM bit, not a duplicate. */
	CHECK((mode & FON_C2_MODE_XMIT_TDM) != 0, "xmit TDM bit set once");

	st = fon_c2_stereo_value(before_stereo, true);
	CHECK((st & FON_C2_STEREO_MASTER) == 0, "stereo MASTER cleared (slave)");
	CHECK((st & FON_C2_STEREO_ENABLE) != 0, "stereo ENABLE set");
	CHECK((st & FON_C2_STEREO_MCK_SEL) != 0, "stereo MCK_SEL set (ext clock)");
	CHECK((st & FON_C2_STEREO_DATA_WORD_SIZE(3)) ==
	      FON_C2_STEREO_DATA_WORD_SIZE(1), "stereo data word size 16-bit");
	CHECK(fon_c2_stereo_value(before_stereo, false) &
	      FON_C2_STEREO_MASTER, "master mode keeps MASTER set");
}

/* ---- readback comparison --------------------------------------------- */

static void test_readback_all_match(void)
{
	struct fon_c2_check c = { .chip_ctrl_ok = true, .i2s_rst_ok = true };

	fon_c2_compare(&c, 0x06070007, 0x06070007,
		       0x10000005, 0x10000005,
		       0x00240400, 0x00240400,
		       0x00240400, 0x00240400);
	CHECK(c.tdm_ok, "tdm matches");
	CHECK(c.audio_mode_ok, "audio_mode matches");
	CHECK(c.stereo_tx_ok, "stereo_tx matches");
	CHECK(c.stereo_rx_ok, "stereo_rx matches");
	CHECK(fon_c2_all_ok(&c), "all_ok when every register matches");
	CHECK(c.tdm_xor == 0 && c.mode_xor == 0 && c.tx_xor == 0 &&
	      c.rx_xor == 0, "xor is zero when every register matches");
}

static void test_readback_tdm_mismatch(void)
{
	struct fon_c2_check c = { .chip_ctrl_ok = true, .i2s_rst_ok = true };

	fon_c2_compare(&c, 0x06070007, 0x00010001,
		       0x10000005, 0x10000005,
		       0x00240400, 0x00240400,
		       0x00240400, 0x00240400);
	CHECK(!c.tdm_ok, "tdm mismatch detected");
	CHECK(!fon_c2_all_ok(&c), "all_ok false when tdm mismatches");
	CHECK(c.tdm_xor == (0x06070007 ^ 0x00010001), "tdm xor reported");
}

static void test_readback_mode_mismatch(void)
{
	struct fon_c2_check c = { .chip_ctrl_ok = true, .i2s_rst_ok = true };

	fon_c2_compare(&c, 0x06070007, 0x06070007,
		       0x10000005, 0x00000000,
		       0x00240400, 0x00240400,
		       0x00240400, 0x00240400);
	CHECK(!c.audio_mode_ok, "audio_mode mismatch detected");
	CHECK(!fon_c2_all_ok(&c), "all_ok false when audio_mode mismatches");
}

static void test_readback_stereo_only_enable(void)
{
	struct fon_c2_check c = { .chip_ctrl_ok = true, .i2s_rst_ok = true };

	/*
	 * The old bug: a readback that has only ENABLE set was accepted.
	 * MASTER, MCK_SEL and the word size must all be checked.
	 */
	fon_c2_compare(&c, 0x06070007, 0x06070007,
		       0x10000005, 0x10000005,
		       0x00240400, 0x00200000,
		       0x00240400, 0x00200000);
	CHECK(!c.stereo_tx_ok, "stereo_tx alone-with-enable is rejected");
	CHECK(!c.stereo_rx_ok, "stereo_rx alone-with-enable is rejected");
	CHECK(!fon_c2_all_ok(&c), "all_ok false when stereo is wrong");
}

static void test_readback_master_left_set(void)
{
	struct fon_c2_check c = { .chip_ctrl_ok = true, .i2s_rst_ok = true };

	/* MASTER still set: the block would be a master, not a slave. */
	fon_c2_compare(&c, 0x06070007, 0x06070007,
		       0x10000005, 0x10000005,
		       0x00240400, 0x00240500,
		       0x00240400, 0x00240500);
	CHECK(!c.stereo_tx_ok, "stereo_tx with MASTER set is rejected");
	CHECK(c.tx_xor == FON_C2_STEREO_MASTER, "xor shows the MASTER bit");
}

static void test_readback_multiple_faults(void)
{
	struct fon_c2_check c = { .chip_ctrl_ok = true, .i2s_rst_ok = true };

	fon_c2_compare(&c, 0x06070007, 0x00000000,
		       0x10000005, 0x00000000,
		       0x00240400, 0x00000000,
		       0x00240400, 0x00000000);
	CHECK(!c.tdm_ok && !c.audio_mode_ok && !c.stereo_tx_ok &&
	      !c.stereo_rx_ok, "all four mismatches detected");
	CHECK(!fon_c2_all_ok(&c), "all_ok false on total failure");
}

static void test_chip_ctrl(void)
{
	struct fon_c2_check c;

	/* INTERFACE_EN must be set after the write. */
	memset(&c, 0, sizeof(c));
	fon_c2_compare_chip(&c, 0x00000001, 0x00000001);
	CHECK(c.chip_ctrl_ok, "chip_ctrl with INTERFACE_EN accepted");

	fon_c2_compare_chip(&c, 0x00000001, 0x00000000);
	CHECK(!c.chip_ctrl_ok, "chip_ctrl without INTERFACE_EN rejected");

	fon_c2_compare_chip(&c, 0x00000001, 0x00000005);
	CHECK(c.chip_ctrl_ok, "extra chip_ctrl bits do not fail the check");
}

static void test_i2s_rst(void)
{
	struct fon_c2_check c;

	memset(&c, 0, sizeof(c));
	fon_c2_compare_rst(&c, 0x00000000);
	CHECK(c.i2s_rst_ok, "i2s_rst cleared after the pulse accepted");

	fon_c2_compare_rst(&c, 0x0000000F);
	CHECK(!c.i2s_rst_ok, "i2s_rst still holding reset rejected");

	fon_c2_compare_rst(&c, 0x00000100);
	CHECK(c.i2s_rst_ok, "i2s_rst high bits outside the mask ignored");
}

static void test_all_ok_needs_new_checks(void)
{
	struct fon_c2_check c = { 0 };

	fon_c2_compare(&c, 0x06070007, 0x06070007,
		       0x10000005, 0x10000005,
		       0x00240400, 0x00240400,
		       0x00240400, 0x00240400);
	c.chip_ctrl_ok = false;
	c.i2s_rst_ok = true;
	CHECK(!fon_c2_all_ok(&c), "all_ok false when chip_ctrl flag is false");

	c.chip_ctrl_ok = true;
	c.i2s_rst_ok = false;
	CHECK(!fon_c2_all_ok(&c), "all_ok false when i2s_rst flag is false");

	c.i2s_rst_ok = true;
	CHECK(fon_c2_all_ok(&c), "all_ok true when every flag is true");
}

int main(void)
{
	test_written_values();
	test_chip_ctrl();
	test_i2s_rst();
	test_all_ok_needs_new_checks();
	test_readback_all_match();
	test_readback_tdm_mismatch();
	test_readback_mode_mismatch();
	test_readback_stereo_only_enable();
	test_readback_master_left_set();
	test_readback_multiple_faults();

	printf("\n%s\n", fails ? "FAILURES" : "all C2 readback tests passed");
	return fails ? 1 : 0;
}
