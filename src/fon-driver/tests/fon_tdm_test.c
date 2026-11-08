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
#include <limits.h>
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

/*
 * Control-only buffer helpers.  Geometry follows the AVM call site:
 * 8 x 16-bit slots per frame, and the control word lives at byte 0x0a of
 * every frame (physical slot 5).
 */
static void test_buffer_geometry(void)
{
	u8 buf[8 * 16];
	unsigned int frames = 8;

	/* AVM geometry: 8 slots x 2 bytes x 8 frames = 128 bytes. */
	assert(fon_tdm_buffer_init(buf, sizeof(buf), 8, frames, FON_TDM_HDR08_5555) == 0);

	/* A short buffer is rejected, never partially written. */
	assert(fon_tdm_buffer_init(buf, sizeof(buf) - 1, 8, frames, FON_TDM_HDR08_5555) == -EINVAL);
	assert(fon_tdm_buffer_init(buf, sizeof(buf) + 1, 8, frames, FON_TDM_HDR08_5555) == -EINVAL);

	/* A frame too short to contain slot 5 is rejected. */
	assert(fon_tdm_buffer_init(buf, sizeof(buf), 4, frames, FON_TDM_HDR08_5555) == -EINVAL);
	assert(fon_tdm_buffer_init(buf, sizeof(buf), 5, frames, FON_TDM_HDR08_5555) == -EINVAL);

	/* Zero frames / slots are rejected. */
	assert(fon_tdm_buffer_init(buf, 0, 8, 0, FON_TDM_HDR08_5555) == -EINVAL);
	assert(fon_tdm_buffer_init(buf, 0, 0, 1, FON_TDM_HDR08_5555) == -EINVAL);

	/* Above the documented maximum. */
	assert(fon_tdm_buffer_init(buf, sizeof(buf), FON_TDM_MAX_SLOTS + 1,
				   1, FON_TDM_HDR08_5555) == -EINVAL);

	/* An out-of-range header selector is rejected. */
	assert(fon_tdm_buffer_init(buf, sizeof(buf), 8, frames,
				   (enum fon_tdm_header_08)7) == -EINVAL);
}

static void test_buffer_silence(void)
{
	u8 buf[8 * 16];
	unsigned int f;

	assert(fon_tdm_buffer_init(buf, sizeof(buf), 8, 8, FON_TDM_HDR08_5555) == 0);

	for (f = 0; f < 8; f++) {
		const u8 *frame = buf + f * 16;

		/* 0x00..0x08 are AVM framing rails, not audio. */
		assert(le16(frame + 0x00) == 0x0000);
		assert(le16(frame + 0x02) == 0xfefe);
		assert(le16(frame + 0x04) == 0xfefe);
		assert(le16(frame + 0x06) == 0xfefe);
		assert(le16(frame + 0x08) == 0x5555);
		/*
		 * 0x0a is the control slot.  Zero is the default buffer
		 * content, NOT a proven line-idle command.
		 */
		assert(le16(frame + 0x0a) == 0x0000);
		/* Only 0x0c onward is audio, and it starts silent. */
		assert(le16(frame + 0x0c) == 0x0000);
		assert(le16(frame + 0x0e) == 0x0000);
	}
}

/*
 * AVM's TxDMA writes 0x5555 or 0x0000 at offset 0x08.  Both branches must be
 * reproducible byte for byte, and nothing else may change between them.
 */
static void test_header08_branches(void)
{
	u8 a[8 * 16];
	u8 b[8 * 16];
	unsigned int f;
	int i;

	assert(fon_tdm_buffer_init(a, sizeof(a), 8, 8, FON_TDM_HDR08_ZERO) == 0);
	assert(fon_tdm_buffer_init(b, sizeof(b), 8, 8, FON_TDM_HDR08_5555) == 0);

	for (f = 0; f < 8; f++) {
		const u8 *fa = a + f * 16;
		const u8 *fb = b + f * 16;

		assert(le16(fa + 0x08) == 0x0000);
		assert(le16(fb + 0x08) == 0x5555);

		/* Apart from bytes 0x08/0x09 the frames are identical. */
		for (i = 0; i < 16; i++) {
			if (i == 0x08 || i == 0x09)
				continue;
			assert(fa[i] == fb[i]);
		}
	}
}

/*
 * 32-bit overflow regression.  On ARMv7 `size_t` is 32 bits, so
 * `frames * slots * 2` wraps: 0x10000000 frames * 8 slots * 2 == 0.  The old
 * check accepted `len == 0` and the writer then ran past the buffer.  These
 * cases must all be rejected.
 */
static void test_geometry_overflow(void)
{
	u8 buf[8];

	/* The exact wrap from the review: product truncates to 0. */
	assert(fon_tdm_buffer_init(buf, 0, 8, 0x10000000u,
				   FON_TDM_HDR08_ZERO) == -EINVAL);
	assert(fon_tdm_buffer_set_control(buf, 0, 8, 0x10000000u, 0) ==
	       -EINVAL);

	/* Products that overflow when multiplied in 32 bits. */
	assert(fon_tdm_buffer_init(buf, sizeof(buf), 8, 0x08000000u,
				   FON_TDM_HDR08_ZERO) == -EINVAL);
	assert(fon_tdm_buffer_init(buf, sizeof(buf), FON_TDM_MAX_SLOTS,
				   UINT_MAX, FON_TDM_HDR08_ZERO) == -EINVAL);
	assert(fon_tdm_buffer_init(buf, sizeof(buf), 8, UINT_MAX,
				   FON_TDM_HDR08_ZERO) == -EINVAL);

	/* A real buffer can never satisfy those frame counts. */
	assert(fon_tdm_buffer_init(buf, sizeof(buf), 8, 0x10000000u,
				   FON_TDM_HDR08_ZERO) == -EINVAL);

	/* Zero length with a positive frame count is still wrong. */
	assert(fon_tdm_buffer_init(buf, 0, 8, 1, FON_TDM_HDR08_ZERO) ==
	       -EINVAL);

	/*
	 * The largest legitimate geometry must still be accepted, so the
	 * overflow guard is not simply rejecting everything.
	 */
	{
		static u8 big[FON_TDM_MAX_SLOTS * 2 * 32];

		assert(fon_tdm_buffer_init(big, sizeof(big), FON_TDM_MAX_SLOTS,
					   32, FON_TDM_HDR08_ZERO) == 0);
		assert(fon_tdm_buffer_init(big, sizeof(big) - 1,
					   FON_TDM_MAX_SLOTS, 32,
					   FON_TDM_HDR08_ZERO) == -EINVAL);
	}
}


/*
 * The one-frame and buffer helpers must produce byte-identical frames for
 * the same parameters, so the two APIs cannot drift apart again.
 */
static void test_single_frame_matches_buffer(void)
{
	u8 single[FON_TDM_MAX_SLOTS * 2];
	u8 buffer[FON_TDM_MAX_SLOTS * 2];
	unsigned int slots;

	for (slots = FON_TDM_CONTROL_SLOT + 1; slots <= FON_TDM_MAX_SLOTS;
	     slots++) {
		size_t len = (size_t)slots * 2;

		assert(fon_tdm_frame_init_ex(single, len,
					     FON_TDM_HDR08_5555) == 0);
		assert(fon_tdm_buffer_init(buffer, len, slots, 1,
					   FON_TDM_HDR08_5555) == 0);
		assert(memcmp(single, buffer, len) == 0);

		assert(fon_tdm_frame_init_ex(single, len,
					     FON_TDM_HDR08_ZERO) == 0);
		assert(fon_tdm_buffer_init(buffer, len, slots, 1,
					   FON_TDM_HDR08_ZERO) == 0);
		assert(memcmp(single, buffer, len) == 0);
	}

	/*
	 * The historical one-frame entry point keeps its 0x5555 behaviour,
	 * so old callers are unaffected by the new selector.
	 */
	assert(fon_tdm_frame_init(single, 16) == 0);
	assert(fon_tdm_frame_init_ex(single, 16,
				     FON_TDM_HDR08_5555) == 0);
	assert(le16(single + 0x08) == 0x5555);

	/* An invalid selector is rejected by both entry points. */
	assert(fon_tdm_frame_init_ex(single, 16,
				     (enum fon_tdm_header_08)9) == -EINVAL);
}


/*
 * The single-frame helper must zero every byte it is given and must not
 * touch anything past `len`.  This guards the removal of the redundant
 * memset in fon_tdm_frame_init_ex(): the internal builder has to do it.
 */
static void test_single_frame_zeroes_only_len(void)
{
	u8 buf[24];
	unsigned int total;

	/* Fill with a poison pattern so a missing clear is visible. */
	memset(buf, 0x5a, sizeof(buf));

	assert(fon_tdm_frame_init_ex(buf, 16, FON_TDM_HDR08_5555) == 0);

	/* Rails inside the frame. */
	assert(le16(buf + 0x00) == 0x0000);
	assert(le16(buf + 0x02) == 0xfefe);
	assert(le16(buf + 0x04) == 0xfefe);
	assert(le16(buf + 0x06) == 0xfefe);
	assert(le16(buf + 0x08) == 0x5555);
	assert(le16(buf + 0x0a) == 0x0000);

	/* Every byte up to len is defined and zeroed apart from the rails. */
	for (total = 0; total < 16; total++) {
		bool rail = (total < 0x0c);

		if (!rail)
			assert(buf[total] == 0x00);
	}

	/* Nothing past len may be touched. */
	for (total = 16; total < sizeof(buf); total++)
		assert(buf[total] == 0x5a);
}

static void test_buffer_control_only(void)
{
	u8 buf[8 * 16];
	u8 before[8 * 16];
	unsigned int f;
	u16 status = 0;

	assert(fon_tdm_buffer_init(buf, sizeof(buf), 8, 8, FON_TDM_HDR08_5555) == 0);
	memcpy(before, buf, sizeof(buf));

	assert(fon_tdm_buffer_set_control(buf, sizeof(buf), 8, 8, 0x4001) == 0);

	for (f = 0; f < 8; f++) {
		const u8 *frame = buf + f * 16;
		const u8 *old = before + f * 16;
		int i;

		assert(le16(frame + 0x0a) == 0x4001);
		assert(frame[0x0a] == 0x01 && frame[0x0b] == 0x40);
		/* Every other byte is untouched: audio really stays silent. */
		for (i = 0; i < 16; i++) {
			if (i == 0x0a || i == 0x0b)
				continue;
			assert(frame[i] == old[i]);
		}
	}

	/* Read back a specific frame. */
	assert(fon_tdm_buffer_get_status(buf, sizeof(buf), 8, 8, 3,
					 &status) == 0);
	assert(status == 0x4001);

	/* Out-of-range frame index. */
	assert(fon_tdm_buffer_get_status(buf, sizeof(buf), 8, 8, 8,
					 &status) == -ERANGE);
	assert(fon_tdm_buffer_get_status(buf, sizeof(buf), 8, 8, 9,
					 &status) == -ERANGE);

	/* Geometry mismatch on the setters. */
	assert(fon_tdm_buffer_set_control(buf, sizeof(buf) - 1, 8, 8,
					  0x4001) == -EINVAL);
	assert(fon_tdm_buffer_get_status(buf, sizeof(buf), 8, 8, 0, NULL) ==
	       -EINVAL);
}

/*
 * The control word must land on the same byte that Stage 5 identified in
 * pcmlink.ko (offset 0x0a) for every supported slot count, so that the
 * "slot 5" claim is encoded in one place.
 */
static void test_control_offset_is_slot_five(void)
{
	unsigned int slots;

	for (slots = FON_TDM_CONTROL_SLOT + 1; slots <= FON_TDM_MAX_SLOTS;
	     slots++) {
		u8 buf[FON_TDM_MAX_SLOTS * 2 * 2];
		size_t len = (size_t)slots * 2 * 2;
		unsigned int byte;

		assert(fon_tdm_buffer_init(buf, len, slots, 2, FON_TDM_HDR08_5555) == 0);
		assert(fon_tdm_buffer_set_control(buf, len, slots, 2,
						  0x1234) == 0);

		for (byte = 0; byte < len; byte++) {
			bool in_slot5 = ((byte % (slots * 2)) == 0x0a) ||
					((byte % (slots * 2)) == 0x0b);

			if (in_slot5)
				assert(buf[byte] == (byte & 1 ? 0x12 : 0x34));
		}
		assert(le16(buf + FON_TDM_CONTROL_OFFSET) == 0x1234);
	}
}

/*
 * Cross-check against the AVM geometry recorded independently:
 *   docs/fon-adss-tdm-channel-map.md §4.1  DMABufferSize = slots * sizeof(short) * fs_per_dma
 *   docs/fon-known-facts.md                slots=8, 16-bit, 32 frames, 512-byte half
 *
 * This ties the constants to the source values rather than to our own
 * #defines, so a silent change in either is caught.
 */
static void test_avm_geometry_matches(void)
{
	const unsigned int avm_slots = 8;      /* 8 x 16-bit per frame */
	const unsigned int avm_fs_per_dma = 32;
	const size_t avm_half = 512;           /* bytes per ping-pong half */
	u8 buf[16 * 32];
	size_t len = (size_t)avm_slots * 2 * avm_fs_per_dma;

	assert(avm_slots * sizeof(u16) * avm_fs_per_dma == avm_half);
	assert(len == avm_half);
	assert(fon_tdm_buffer_init(buf, len, avm_slots, avm_fs_per_dma, FON_TDM_HDR08_5555) == 0);

	/* The control word exists in all 32 frames of the AVM half. */
	assert(fon_tdm_buffer_set_control(buf, len, avm_slots, avm_fs_per_dma,
					  0x0000) == 0);
}

/*
 * An all-zero RX buffer is a valid "no status" frame and must decode to 0
 * rather than to an error.  A truncated RX buffer must be an error, not a
 * read past the end.
 */
static void test_empty_rx(void)
{
	u8 buf[8 * 16];
	u16 status = 0xffff;

	memset(buf, 0, sizeof(buf));
	assert(fon_tdm_buffer_get_status(buf, sizeof(buf), 8, 8, 0, &status) ==
	       0);
	assert(status == 0x0000);

	/* One byte short of a whole frame. */
	assert(fon_tdm_buffer_get_status(buf, sizeof(buf) - 1, 8, 8, 0,
					 &status) == -EINVAL);
	/* Backing up by a whole frame is still a mismatch vs `frames`. */
	assert(fon_tdm_buffer_get_status(buf, sizeof(buf) - 16, 8, 8, 0,
					 &status) == -EINVAL);
}

int main(void)
{
	test_frame_layout_12();
	test_frame_layout_16();
	test_frame_bounds();
	test_slic_control();
	test_status_hook();
	test_ring_bits();
	test_buffer_geometry();
	test_buffer_silence();
	test_header08_branches();
	test_geometry_overflow();
	test_single_frame_matches_buffer();
	test_single_frame_zeroes_only_len();
	test_buffer_control_only();
	test_control_offset_is_slot_five();
	test_avm_geometry_matches();
	test_empty_rx();
	puts("fon_tdm_test: all tests passed");
	return 0;
}
