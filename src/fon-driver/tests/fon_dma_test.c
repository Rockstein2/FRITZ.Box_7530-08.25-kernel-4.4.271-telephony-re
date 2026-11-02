// SPDX-License-Identifier: GPL-2.0-only
/*
 * Host-side tests for MBOX descriptor layout and DMA ring construction.
 */

#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

#include "fon_dma.h"

#define TEST_STRIDE_64 192u
#define TEST_STRIDE_32 160u

static void test_layout(void)
{
	assert(sizeof(struct fon_mbox_desc) == 156);
	assert(FON_MBOX_DESC_SIZE == 156);
	assert(sizeof(((struct fon_mbox_desc *)0)->reserved) == 144);
}

static void test_two_descriptor_ring(void)
{
	unsigned char storage[2 * TEST_STRIDE_64 + 16];
	struct fon_mbox_desc *ring = (struct fon_mbox_desc *)storage;
	const u32 buf[2] = { 0x00100000, 0x00101000 };
	struct fon_mbox_desc *d0, *d1;

	memset(storage, 0xa5, sizeof(storage));
	assert(fon_dma_build_ring(ring, 2 * TEST_STRIDE_64, TEST_STRIDE_64,
				  2, 0x00200000, buf, 512) == 0);

	d0 = (struct fon_mbox_desc *)storage;
	d1 = (struct fon_mbox_desc *)(storage + TEST_STRIDE_64);
	assert(d0->ctrl == (u32)(FON_DESC_SIZE(512) | FON_DESC_LENGTH(512) |
				    FON_DESC_EI | FON_DESC_OWN));
	assert(d0->buf_ptr == buf[0]);
	assert(d0->next_ptr == 0x00200000 + TEST_STRIDE_64);
	assert(d1->ctrl == d0->ctrl);
	assert(d1->buf_ptr == buf[1]);
	assert(d1->next_ptr == 0x00200000);
	/* The padding after each 156-byte descriptor must be zeroed. */
	for (unsigned int i = 0; i < TEST_STRIDE_64 - sizeof(*d0); i++) {
		assert(storage[i + sizeof(*d0)] == 0);
		assert(storage[TEST_STRIDE_64 + sizeof(*d0) + i] == 0);
	}
	/* Guard bytes outside ring_bytes remain untouched. */
	assert(storage[2 * TEST_STRIDE_64] == 0xa5);
	assert(storage[sizeof(storage) - 1] == 0xa5);
}

static void test_wrap_and_32_byte_stride(void)
{
	unsigned char storage[FON_DMA_DESC_COUNT * TEST_STRIDE_32];
	struct fon_mbox_desc *ring = (struct fon_mbox_desc *)storage;
	const u32 buf[2] = { 0x00110000, 0x00111000 };
	unsigned int i;

	assert(fon_dma_build_ring(ring, sizeof(storage), TEST_STRIDE_32,
				  FON_DMA_DESC_COUNT, 0x00220000, buf,
				  512) == 0);
	for (i = 0; i < FON_DMA_DESC_COUNT; i++) {
		struct fon_mbox_desc *d = (struct fon_mbox_desc *)
			(storage + i * TEST_STRIDE_32);
		u32 expected_next = 0x00220000 +
			((i + 1) % FON_DMA_DESC_COUNT) * TEST_STRIDE_32;

		assert(d->buf_ptr == buf[i & 1]);
		assert(d->next_ptr == expected_next);
		assert(d->ctrl == (u32)(FON_DESC_SIZE(512) |
					 FON_DESC_LENGTH(512) |
					 FON_DESC_EI | FON_DESC_OWN));
	}
}

static void test_invalid_geometry(void)
{
	unsigned char storage[1024];
	struct fon_mbox_desc *ring = (struct fon_mbox_desc *)storage;
	const u32 buf[2] = { 0x00100000, 0x00101000 };

	assert(fon_dma_build_ring(NULL, 1024, TEST_STRIDE_64, 2,
				  0x00200000, buf, 512) == -EINVAL);
	assert(fon_dma_build_ring(ring, 1024, TEST_STRIDE_64, 2,
				  0x00200000, NULL, 512) == -EINVAL);
	assert(fon_dma_build_ring(ring, 1024, 155, 2,
				  0x00200000, buf, 512) == -EINVAL);
	assert(fon_dma_build_ring(ring, 1024, 158, 2,
				  0x00200000, buf, 512) == -EINVAL);
	assert(fon_dma_build_ring(ring, 1024, TEST_STRIDE_64, 1,
				  0x00200000, buf, 512) == -EINVAL);
	assert(fon_dma_build_ring(ring, 1024, TEST_STRIDE_64, 65,
				  0x00200000, buf, 512) == -EINVAL);
	assert(fon_dma_build_ring(ring, 1024, TEST_STRIDE_64, 2,
				  0x00200000, buf, 0) == -EINVAL);
	assert(fon_dma_build_ring(ring, 1024, TEST_STRIDE_64, 2,
				  0x00200000, buf, 0x1000) == -EINVAL);
	assert(fon_dma_build_ring(ring, 1024, TEST_STRIDE_64, 2,
				  0x10000000, buf, 512) == -ERANGE);
	assert(fon_dma_build_ring(ring, 1024, TEST_STRIDE_64, 2,
				  0x00200000,
				  (const u32[2]){ 0x00100000, 0x10000000 },
				  512) == -ERANGE);
	assert(fon_dma_build_ring(ring, 1024, TEST_STRIDE_64, 2,
				  0x0fffff80, buf, 512) == -ERANGE);
	assert(fon_dma_build_ring(ring, (size_t)2 * TEST_STRIDE_64 - 1,
				  TEST_STRIDE_64, 2, 0x00200000, buf,
				  512) == -EINVAL);
	assert(fon_dma_build_ring((struct fon_mbox_desc *)(storage + 1),
				  1024, TEST_STRIDE_64, 2, 0x00200000, buf,
				  512) == -EINVAL);
}

static void test_state_helpers(void)
{
	assert(!fon_state_can_prepare(FON_STATE_UNINITIALIZED));
	assert(fon_state_can_prepare(FON_STATE_RESOURCES_READY));
	assert(!fon_state_can_prepare(FON_STATE_DMA_PREPARED));
	assert(!fon_state_can_release(FON_STATE_RESOURCES_READY));
	assert(fon_state_can_release(FON_STATE_DMA_PREPARED));
	assert(!fon_state_can_release(FON_STATE_UNINITIALIZED));
}

int main(void)
{
	test_layout();
	test_two_descriptor_ring();
	test_wrap_and_32_byte_stride();
	test_invalid_geometry();
	test_state_helpers();
	puts("fon_dma_test: all tests passed");
	return 0;
}
