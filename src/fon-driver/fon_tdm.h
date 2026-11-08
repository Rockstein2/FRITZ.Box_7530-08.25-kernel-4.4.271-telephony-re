/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef FON_TDM_H
#define FON_TDM_H

/*
 * Pure TDM frame helpers for the FRITZ!Box 7530 FON transport.
 *
 * These functions are deliberately independent of kernel MMIO/DMA so they
 * can be tested in userspace.  The confirmed Linux-side format comes from
 * pcmlink.ko TxDMA/PutRxDMA:
 *
 *   byte offset 0x00 : 0x0000
 *   byte offset 0x02 : 0xfefe
 *   byte offset 0x04 : 0xfefe
 *   byte offset 0x06 : 0xfefe
 *   byte offset 0x08 : 0x5555 or 0x0000 (AVM picks by TDMPriv+0x808)
 *   byte offset 0x0a : 16-bit FON control/status word (physical slot 5)
 *   byte offset 0x0c..: audio / remaining slots
 *
 * This frame is NOT "all silence": 0x02..0x08 carry AVM framing rails whose
 * SC14448 meaning is not decoded.  Only 0x0c and beyond are audio.
 *
 * The 0xfefe/0x5555 values are copied from the AVM TxDMA header, and the
 * condition behind the 0x08 choice is not decoded, so it is a parameter.
 */

#ifdef __KERNEL__
#include <linux/types.h>
#include <linux/errno.h>
#include <linux/string.h>
#else
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
#include <errno.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
#endif

#define FON_TDM_CONTROL_SLOT       5
#define FON_TDM_CONTROL_OFFSET     (FON_TDM_CONTROL_SLOT * 2)
#define FON_TDM_MIN_FRAME_BYTES    (FON_TDM_CONTROL_OFFSET + 2)
#define FON_TDM_SLOTS              8
#define FON_TDM_FRAME_BYTES        (FON_TDM_SLOTS * 2)
#define FON_TDM_MAX_SLOTS          16
#define FON_TDM_MAX_FRAME_BYTES    (FON_TDM_MAX_SLOTS * 2)

#define FON_TDM_HEADER_ZERO        0x0000
#define FON_TDM_HEADER_SYNC        0xfefe
#define FON_TDM_HEADER_AUDIO       0x5555

/*
 * Word at byte offset 0x08.  AVM's TxDMA writes 0x5555 or 0x0000 depending
 * on TDMPriv+0x808; the condition behind that flag is not decoded, so the
 * caller must choose and say which branch it is exercising.
 */
enum fon_tdm_header_08 {
	FON_TDM_HDR08_ZERO = 0,   /* tx[0x08] = 0x0000 */
	FON_TDM_HDR08_5555 = 1,   /* tx[0x08] = 0x5555 */
};

/* build_slic_ctrl() in pcmlink.ko @0x8f68, line-control branch. */
u16 fon_tdm_slic_ctrl_from_regs(u32 reg48, u32 reg2c, u16 half_period);
u16 fon_tdm_ring_ctrl_from_half_period(u16 half_period);

/* PutRxDMA() in pcmlink.ko @0x9a60.  Register 0x44 is 32-bit. */
u32 fon_tdm_status_to_reg44(u16 status);
u16 fon_tdm_reg44_hook(u32 reg44);
u16 fon_tdm_reg48_ring_bits(u16 reg48);

/* Frame helpers.  Return -EINVAL if the buffer is too short. */
int fon_tdm_frame_init(u8 *frame, size_t len);

/*
 * Same as fon_tdm_frame_init() but with an explicit header selector.
 * fon_tdm_frame_init() is exactly this with FON_TDM_HDR08_5555, which keeps
 * its historical behaviour; the buffer helper defaults to _ZERO in the
 * driver.  Both share one internal builder, so they cannot drift apart.
 */
int fon_tdm_frame_init_ex(u8 *frame, size_t len, enum fon_tdm_header_08 hdr08);
int fon_tdm_frame_set_control(u8 *frame, size_t len, u16 control);
int fon_tdm_frame_get_status(const u8 *frame, size_t len, u16 *status);

/*
 * Control-only dry-run helpers.  They fill a whole DMA buffer (one or more
 * consecutive TDM frames) in CPU memory and never touch hardware.
 *
 * A frame is NOT "all silence".  It carries AVM's fixed header rails:
 *
 *   0x00  0x0000            header
 *   0x02  0xfefe            header (sync rail)
 *   0x04  0xfefe            header (sync rail)
 *   0x06  0xfefe            header (sync rail)
 *   0x08  0x5555 or 0x0000  selected by hdr08 (AVM TDMPriv+0x808 branch)
 *   0x0a  control word      slot 5
 *   0x0c.. audio slots      filled with 0
 *
 * Only the words at 0x0c and beyond are audio.  The 0xfefe/0x5555 rails are
 * AVM framing values whose SC14448 meaning is not decoded.
 *
 * `slots` must be uniform across the buffer because the control word is at a
 * fixed byte offset (0x0a) inside every frame; a frame shorter than
 * FON_TDM_MIN_FRAME_BYTES is rejected rather than silently truncated.
 */
int fon_tdm_buffer_init(u8 *buf, size_t len, unsigned int slots,
			unsigned int frames, enum fon_tdm_header_08 hdr08);

/* Write `control` into slot 5 of every frame.  No other byte changes. */
int fon_tdm_buffer_set_control(u8 *buf, size_t len, unsigned int slots,
			       unsigned int frames, u16 control);

/* Read slot 5 of frame `index`.  Returns -ERANGE if `index` is past `frames`. */
int fon_tdm_buffer_get_status(const u8 *buf, size_t len, unsigned int slots,
			      unsigned int frames, unsigned int index,
			      u16 *status);

#endif /* FON_TDM_H */
