// SPDX-License-Identifier: GPL-2.0-only
/*
 * Pure TDM frame and FON control-word helpers.
 *
 * The bit layouts below are recovered from pcmlink.ko:
 *   build_slic_ctrl @0x8f68
 *   PutRxDMA       @0x9a60
 *
 * The Linux-side packing is confirmed.  The meaning of the resulting bits
 * inside the Dialog SC14448 is not confirmed.
 */

#include "fon_tdm.h"

static void put_le16(u8 *p, u16 v)
{
	p[0] = (u8)(v & 0xff);
	p[1] = (u8)(v >> 8);
}

static u16 get_le16(const u8 *p)
{
	return (u16)p[0] | ((u16)p[1] << 8);
}

/*
 * Single internal frame builder.  Both the one-frame helper and the buffer
 * helper go through this, so they cannot drift apart again.
 */
static void fon_tdm_frame_build(u8 *frame, size_t frame_len,
				enum fon_tdm_header_08 hdr08)
{
	u16 hdr_word = (hdr08 == FON_TDM_HDR08_5555) ? FON_TDM_HEADER_AUDIO
						     : FON_TDM_HEADER_ZERO;

	memset(frame, 0, frame_len);
	put_le16(frame + 0x00, FON_TDM_HEADER_ZERO);
	put_le16(frame + 0x02, FON_TDM_HEADER_SYNC);
	put_le16(frame + 0x04, FON_TDM_HEADER_SYNC);
	put_le16(frame + 0x06, FON_TDM_HEADER_SYNC);
	put_le16(frame + 0x08, hdr_word);
	put_le16(frame + FON_TDM_CONTROL_OFFSET, 0);
}

int fon_tdm_frame_init(u8 *frame, size_t len)
{
	/* Historical behaviour: the one-frame helper always used 0x5555. */
	return fon_tdm_frame_init_ex(frame, len, FON_TDM_HDR08_5555);
}

int fon_tdm_frame_init_ex(u8 *frame, size_t len, enum fon_tdm_header_08 hdr08)
{
	if (!frame || len < FON_TDM_MIN_FRAME_BYTES)
		return -EINVAL;
	if (hdr08 != FON_TDM_HDR08_ZERO && hdr08 != FON_TDM_HDR08_5555)
		return -EINVAL;

	/*
	 * The one-frame API owns the whole buffer: zero all of `len` and lay
	 * the rails over the first frame, so trailing bytes are deterministic.
	 */
	memset(frame, 0, len);
	fon_tdm_frame_build(frame, len, hdr08);
	return 0;
}

int fon_tdm_frame_set_control(u8 *frame, size_t len, u16 control)
{
	if (!frame || len < FON_TDM_MIN_FRAME_BYTES)
		return -EINVAL;
	put_le16(frame + FON_TDM_CONTROL_OFFSET, control);
	return 0;
}

int fon_tdm_frame_get_status(const u8 *frame, size_t len, u16 *status)
{
	if (!frame || !status || len < FON_TDM_MIN_FRAME_BYTES)
		return -EINVAL;
	*status = get_le16(frame + FON_TDM_CONTROL_OFFSET);
	return 0;
}

u16 fon_tdm_ring_ctrl_from_half_period(u16 half_period)
{
	return (u16)(half_period | 0x8000);
}

/*
 * Exact line-control branch of build_slic_ctrl:
 *
 *   if (half_period != 0)
 *       return half_period | 0x8000;
 *   ctrl  = ((reg48 >> 3) & 0x1e0) | ((reg48 >> 4) & 0xf);
 *   if (reg2c & BIT(17)) ctrl |= 0x10;
 *   if (reg2c & BIT(18)) ctrl |= 0x200;
 *   return ctrl | 0x4000;
 */
u16 fon_tdm_slic_ctrl_from_regs(u32 reg48, u32 reg2c, u16 half_period)
{
	u16 ctrl;

	if (half_period)
		return fon_tdm_ring_ctrl_from_half_period(half_period);

	ctrl = (u16)(((reg48 >> 3) & 0x1e0) | ((reg48 >> 4) & 0xf));
	if (reg2c & (1u << 17))
		ctrl |= 0x10;
	if (reg2c & (1u << 18))
		ctrl |= 0x200;
	return ctrl | 0x4000;
}

/*
 * Exact PutRxDMA status conversion:
 *   reg44 = 0x00020008
 *         | ((status << 3) & 0x00000f00)
 *         | ((status << 4) & 0x000000ff);
 */
u32 fon_tdm_status_to_reg44(u16 status)
{
	u32 value = 0x00020008u;

	value |= ((u32)status << 3) & 0x00000f00u;
	value |= ((u32)status << 4) & 0x000000ffu;
	return value;
}

u16 fon_tdm_reg44_hook(u32 reg44)
{
	return (reg44 >> 7) & 1;
}

u16 fon_tdm_reg48_ring_bits(u16 reg48)
{
	return (reg48 >> 5) & 0x3;
}

/*
 * Buffer-level control-only helpers.
 *
 * The geometry check is deliberately strict and overflow-free.  On the
 * 32-bit IPQ4019, `frames * slots * 2` can wrap: `frames = 0x10000000` with
 * 8 slots gives 0 after truncation, which would accept a zero-length buffer
 * and let the writer run past its end.  Dividing instead of multiplying
 * cannot overflow.
 */
static bool fon_tdm_geometry_ok(unsigned int slots, unsigned int frames,
				size_t len)
{
	size_t frame_bytes;

	if (!slots || !frames)
		return false;
	if (slots > FON_TDM_MAX_SLOTS)
		return false;
	if (slots < FON_TDM_CONTROL_SLOT + 1)
		return false;

	frame_bytes = (size_t)slots * sizeof(u16);
	return len % frame_bytes == 0 && len / frame_bytes == frames;
}

int fon_tdm_buffer_init(u8 *buf, size_t len, unsigned int slots,
			unsigned int frames, enum fon_tdm_header_08 hdr08)
{
	unsigned int f;

	if (!buf || !fon_tdm_geometry_ok(slots, frames, len))
		return -EINVAL;
	if (hdr08 != FON_TDM_HDR08_ZERO && hdr08 != FON_TDM_HDR08_5555)
		return -EINVAL;

	for (f = 0; f < frames; f++)
		fon_tdm_frame_build(buf + (size_t)f * slots * sizeof(u16),
				    (size_t)slots * sizeof(u16), hdr08);
	return 0;
}

int fon_tdm_buffer_set_control(u8 *buf, size_t len, unsigned int slots,
			       unsigned int frames, u16 control)
{
	unsigned int f;

	if (!buf || !fon_tdm_geometry_ok(slots, frames, len))
		return -EINVAL;

	for (f = 0; f < frames; f++)
		put_le16(buf + (size_t)f * slots * sizeof(u16) +
			 FON_TDM_CONTROL_OFFSET, control);
	return 0;
}

int fon_tdm_buffer_get_status(const u8 *buf, size_t len, unsigned int slots,
			      unsigned int frames, unsigned int index,
			      u16 *status)
{
	if (!buf || !status || !fon_tdm_geometry_ok(slots, frames, len))
		return -EINVAL;
	if (index >= frames)
		return -ERANGE;

	*status = get_le16(buf + (size_t)index * slots * sizeof(u16) +
			   FON_TDM_CONTROL_OFFSET);
	return 0;
}
