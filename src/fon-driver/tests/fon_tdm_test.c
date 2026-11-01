// SPDX-License-Identifier: GPL-2.0-only
/*
 * Host-side tests for the pure FON TDM frame helpers.
 *
 * Build/run from src/fon-driver:
 *   cc -Wall -Wextra -Werror -I. fon_tdm.c tests/fon_tdm_test.c \
 *      -o tests/fon_tdm_test
 *   ./tests/fon_tdm_test
 */

#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "fon_tdm.h"

static u16 le16(const u8 *p)
{
	return (u16)p[0] | ((u16)p[1] << 8);
}

static void test_frame_layout_12(void)
{
	u8 frame[12];
	u16 status = 0;

	assert(fon_tdm_frame_init(frame, sizeof(frame)) == 0);
	assert(le16(frame + 0x00) == 0x0000);
	assert(le16(frame + 0x02) == 0xfefe);
	assert(le16(frame + 0x04) == 0xfefe);
	assert(le16(frame + 0x06) == 0xfefe);
	assert(le16(frame + 0x08) == 0x5555);
	assert(le16(frame + 0x0a) == 0x0000);

	assert(fon_tdm_frame_set_control(frame, sizeof(frame), 0x1234) == 0);
	assert(fon_tdm_frame_get_status(frame, sizeof(frame), &status) == 0);
	assert(status == 0x1234);
	assert(frame[0x0a] == 0x34 && frame[0x0b] == 0x12);
}

static void test_frame_layout_16(void)
{
	u8 frame[16];
	u8 guarded[18];
	u16 status = 0;

	assert(fon_tdm_frame_init(frame, sizeof(frame)) == 0);
	assert(fon_tdm_frame_set_control(frame, sizeof(frame), 0xbeef) == 0);
	assert(fon_tdm_frame_get_status(frame, sizeof(frame), &status) == 0);
	assert(status == 0xbeef);
	/* Remaining slots are not touched by the control helper. */
	for (int i = 12; i < 16; i++)
		assert(frame[i] == 0);

	/* Allocation bounds: the helpers must not touch bytes outside len. */
	memset(guarded, 0xa5, sizeof(guarded));
	guarded[0] = 0x5a;
	guarded[17] = 0x3c;
	assert(fon_tdm_frame_init(guarded + 1, 16) == 0);
	assert(guarded[0] == 0x5a);
	assert(guarded[17] == 0x3c);
	assert(fon_tdm_frame_set_control(guarded + 1, 16, 0x1234) == 0);
	assert(guarded[0] == 0x5a);
	assert(guarded[17] == 0x3c);
}

static void test_frame_bounds(void)
{
	u8 frame[11];
	u16 status = 0;

	assert(fon_tdm_frame_init(frame, sizeof(frame)) == -EINVAL);
	assert(fon_tdm_frame_set_control(frame, sizeof(frame), 1) == -EINVAL);
	assert(fon_tdm_frame_get_status(frame, sizeof(frame), &status) == -EINVAL);
	assert(fon_tdm_frame_init(NULL, 16) == -EINVAL);
	assert(fon_tdm_frame_set_control(NULL, 16, 1) == -EINVAL);
	assert(fon_tdm_frame_get_status(NULL, 16, &status) == -EINVAL);
}

static void test_slic_control(void)
{
	/* No line/ring bits: marker only. */
	assert(fon_tdm_slic_ctrl_from_regs(0, 0, 0) == 0x4000);

	/* Register 0x48 bits 5/6 become control bits 1/2. */
	assert(fon_tdm_slic_ctrl_from_regs(0x20, 0, 0) == (0x4000 | 0x02));
	assert(fon_tdm_slic_ctrl_from_regs(0x40, 0, 0) == (0x4000 | 0x04));
	assert(fon_tdm_slic_ctrl_from_regs(0x60, 0, 0) == (0x4000 | 0x06));

	/* Register 0x48 bits 8..11 become control bits 5..8. */
	assert(fon_tdm_slic_ctrl_from_regs(0x100, 0, 0) == (0x4000 | 0x20));
	assert(fon_tdm_slic_ctrl_from_regs(0x800, 0, 0) == (0x4000 | 0x100));

	/* Register 0x2c flags. */
	assert(fon_tdm_slic_ctrl_from_regs(0, 1u << 17, 0) ==
	       (0x4000 | 0x10));
	assert(fon_tdm_slic_ctrl_from_regs(0, 1u << 18, 0) ==
	       (0x4000 | 0x200));

	/* Ring path bypasses the line-control bits. */
	assert(fon_tdm_slic_ctrl_from_regs(0xffff, 0xffff, 0x1234) == 0x9234);
	assert(fon_tdm_slic_ctrl_from_regs(0xffff, 0, 0) == 0x41ef);
	assert(fon_tdm_slic_ctrl_from_regs(0, 0xffffffffu, 0) == 0x4210);
	assert(fon_tdm_ring_ctrl_from_half_period(0) == 0x8000);
	assert(fon_tdm_ring_ctrl_from_half_period(0x7fff) == 0xffff);
}

static void test_status_hook(void)
{
	/* Baseline bits from PutRxDMA. */
	assert(fon_tdm_status_to_reg44(0x0000) == 0x00020008u);

	/* RX status bit 3 -> register 0x44 bit 7 -> hook = 1. */
	assert(fon_tdm_status_to_reg44(0x0008) == 0x00020088u);
	assert(fon_tdm_reg44_hook(fon_tdm_status_to_reg44(0x0008)) == 1);
	assert(fon_tdm_reg44_hook(fon_tdm_status_to_reg44(0x0000)) == 0);

	/* Status bits 5..8 map to register bits 8..11. */
	{
		u32 r = fon_tdm_status_to_reg44(0x0120);
		assert((r & 0x0f00) == 0x0900);
	}

	/* Status bits 0..3 map into register bits 4..7. */
	{
		u32 r = fon_tdm_status_to_reg44(0x000f);
		assert((r & 0x00f0) == 0x00f0);
	}

	/* No overflow / truncation beyond the documented 16-bit fields. */
	assert(fon_tdm_status_to_reg44(0xffff) == 0x00020ff8u);
}

static void test_ring_bits(void)
{
	assert(fon_tdm_reg48_ring_bits(0x0000) == 0);
	assert(fon_tdm_reg48_ring_bits(0x0020) == 1);
	assert(fon_tdm_reg48_ring_bits(0x0040) == 2);
	assert(fon_tdm_reg48_ring_bits(0x0060) == 3);
	/* High bits must not leak into the two-bit result. */
	assert(fon_tdm_reg48_ring_bits(0xff9f) == 0);
}

int main(void)
{
	test_frame_layout_12();
	test_frame_layout_16();
	test_frame_bounds();
	test_slic_control();
	test_status_hook();
	test_ring_bits();
	puts("fon_tdm_test: all tests passed");
	return 0;
}
