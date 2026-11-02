// SPDX-License-Identifier: GPL-2.0-only
/*
 * Pure MBOX descriptor layout and ring construction.
 */

#include "fon_dma.h"

#ifdef __KERNEL__
#include <linux/errno.h>
#include <linux/string.h>
#else
#include <errno.h>
#include <stdbool.h>
#include <string.h>
#endif

_Static_assert(sizeof(struct fon_mbox_desc) == FON_MBOX_DESC_SIZE,
	       "unexpected MBOX descriptor size");
_Static_assert(sizeof(u32) == 4, "MBOX descriptor requires 32-bit words");

int fon_dma_build_ring(struct fon_mbox_desc *ring, size_t ring_bytes,
		       size_t stride, unsigned int count, u32 desc_dma,
		       const u32 buf_dma[2], u32 buf_size)
{
	unsigned int i;
	unsigned long long ring_span;

	if (!ring || !buf_dma)
		return -EINVAL;
	if (stride < sizeof(struct fon_mbox_desc) || (stride & 3))
		return -EINVAL;
	if (count < 2 || count > 64)
		return -EINVAL;
	if (!buf_size || buf_size > FON_DESC_LENGTH_MASK)
		return -EINVAL;
	if (((unsigned long)ring & 3) != 0)
		return -EINVAL;

	ring_span = (unsigned long long)count * stride;
	if (ring_span > ring_bytes)
		return -EINVAL;

	if (desc_dma & ~FON_DMA_ADDR_MASK)
		return -ERANGE;
	if (buf_dma[0] & ~FON_DMA_ADDR_MASK ||
	    buf_dma[1] & ~FON_DMA_ADDR_MASK)
		return -ERANGE;
	if ((unsigned long long)desc_dma +
	    (unsigned long long)(count - 1) * stride > FON_DMA_ADDR_MASK)
		return -ERANGE;

	memset(ring, 0, (size_t)ring_span);
	for (i = 0; i < count; i++) {
		struct fon_mbox_desc *desc =
			(struct fon_mbox_desc *)((unsigned char *)ring +
						 i * stride);
		unsigned int next = (i + 1) % count;

		desc->ctrl = FON_DESC_SIZE(buf_size) |
			     FON_DESC_LENGTH(buf_size) |
			     FON_DESC_EI | FON_DESC_OWN;
		desc->buf_ptr = buf_dma[i & 1];
		desc->next_ptr = (u32)(((unsigned long long)desc_dma +
				       (unsigned long long)next * stride) &
				      FON_DMA_ADDR_MASK);
	}
	return 0;
}
