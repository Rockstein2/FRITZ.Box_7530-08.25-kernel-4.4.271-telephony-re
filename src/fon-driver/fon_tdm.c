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

int fon_tdm_frame_init(u8 *frame, size_t len)
{
	if (!frame || len < FON_TDM_MIN_FRAME_BYTES)
		return -EINVAL;

	memset(frame, 0, len);
	put_le16(frame + 0x00, FON_TDM_HEADER_ZERO);
	put_le16(frame + 0x02, FON_TDM_HEADER_SYNC);
	put_le16(frame + 0x04, FON_TDM_HEADER_SYNC);
	put_le16(frame + 0x06, FON_TDM_HEADER_SYNC);
	put_le16(frame + 0x08, FON_TDM_HEADER_AUDIO);
	put_le16(frame + FON_TDM_CONTROL_OFFSET, 0);
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
