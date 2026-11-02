/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef FON_DMA_H
#define FON_DMA_H

/*
 * Pure MBOX descriptor layout and ring construction.
 *
 * The IPQ4019 AVM driver uses:
 *   sizeof(struct _mbox_desc) = 156 bytes
 *   mbox_get_desc_size()      = L1_CACHE_ALIGN(156)
 *   NextPtr                   = physical(ring) + index * mbox_get_desc_size()
 *
 * The trailing bytes between sizeof(struct _mbox_desc) and the cache-aligned
 * stride are padding.  Keeping this code kernel-independent lets the layout
 * be tested on the host.
 */

#ifdef __KERNEL__
#include <linux/types.h>
#else
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
typedef uint32_t u32;
#endif

#define FON_MBOX_DESC_WORDS       36
#define FON_MBOX_DESC_SIZE        (3u * 4u + FON_MBOX_DESC_WORDS * 4u)
#define FON_DMA_ADDR_MASK         0x0fffffffu

#define FON_DESC_LENGTH_MASK      0x00000fff
#define FON_DESC_SIZE_MASK        0x00fff000
#define FON_DESC_SIZE(v)          (((v) & 0xfff) << 12)
#define FON_DESC_LENGTH(v)        ((v) & 0xfff)
#define FON_DESC_VUC              (1u << 24)
#define FON_DESC_EI               (1u << 25)
#define FON_DESC_EOM              (1u << 30)
#define FON_DESC_OWN              (1u << 31)

#define FON_DMA_FRAMES_PER_BUFFER 32u
#define FON_DMA_DESC_COUNT        16u

struct fon_mbox_desc {
	u32 ctrl;
	u32 buf_ptr;
	u32 next_ptr;
	u32 reserved[FON_MBOX_DESC_WORDS];
};

enum fon_tdm_state {
	FON_STATE_UNINITIALIZED = 0,
	FON_STATE_RESOURCES_READY,
	FON_STATE_DMA_PREPARED,
};

static inline bool fon_state_can_prepare(enum fon_tdm_state state)
{
	return state == FON_STATE_RESOURCES_READY;
}

static inline bool fon_state_can_release(enum fon_tdm_state state)
{
	return state == FON_STATE_DMA_PREPARED;
}

/**
 * fon_dma_build_ring - fill a coherent descriptor ring
 * @ring: CPU virtual address of the ring
 * @ring_bytes: size of the allocation containing the ring
 * @stride: hardware descriptor stride (cache-aligned descriptor size)
 * @count: number of descriptors
 * @desc_dma: physical address programmed into the MBOX descriptor base
 * @buf_dma: two physical ping-pong buffer addresses
 * @buf_size: size/length field in each descriptor
 *
 * Returns 0 on success, -EINVAL for invalid geometry, -ERANGE when a physical
 * address does not fit the IPQ4019 28-bit MBOX address mask.
 *
 * The function writes only CPU memory; it does not program MBOX registers and
 * does not start DMA.
 */
int fon_dma_build_ring(struct fon_mbox_desc *ring, size_t ring_bytes,
		       size_t stride, unsigned int count, u32 desc_dma,
		       const u32 buf_dma[2], u32 buf_size);

#endif /* FON_DMA_H */
