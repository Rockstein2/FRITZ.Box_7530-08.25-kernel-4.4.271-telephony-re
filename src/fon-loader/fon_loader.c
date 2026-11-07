// SPDX-License-Identifier: GPL-2.0-only
/*
 * Dry-run planner for the Dialog SC14448 boot firmware transfer.
 *
 * No device is opened here.  Everything below is arithmetic on already
 * parsed images plus an abstract transport, so it is fully testable offline.
 */

#include <stdio.h>
#include <string.h>

#include "fon_loader.h"

static uint32_t be32(const uint8_t *p)
{
	return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
	       ((uint32_t)p[2] << 8) | (uint32_t)p[3];
}

enum fon_loader_result fon_loader_level_init(struct fon_loader_level *out,
					     int level,
					     const uint8_t *image,
					     size_t image_len)
{
	size_t hdr = (level == 0) ? 2u : 4u;
	size_t off;
	uint32_t declared;
	uint8_t acc = 0;

	if (!out || !image)
		return FON_LOADER_ERR_ARG;
	if (level != 0 && level != 1)
		return FON_LOADER_ERR_ARG;
	if (image_len < hdr + 1u)
		return FON_LOADER_ERR_FORMAT;

	memset(out, 0, sizeof(*out));
	out->level = level;
	out->image = image;
	out->image_len = image_len;

	declared = (level == 0)
		? ((uint32_t)image[0] << 8 | image[1])
		: be32(image);

	/* The outer length covers the blocks only, not header or checksum. */
	/*
	 * The outer length counts the block payload only.  Good images are
	 * header + payload + checksum, i.e. image_len == declared + hdr + 1.
	 */
	if ((size_t)declared + hdr + 1u != image_len)
		return FON_LOADER_ERR_FORMAT;

	/*
	 * Block walk.  Parsing stops at the last full block; the tail after it
	 * is the trailer, whose layout on real AVM images is NOT the simple
	 * whole-image XOR the local parser emits.  The trailer is recorded
	 * verbatim and validated separately, because an unproven checksum
	 * rule must not be used to reject a real image.
	 */
	off = hdr;
	while (off + FON_LOADER_BLOCK_HEADER <= image_len - 1u) {
		uint32_t addr, len;

		if (off + FON_LOADER_BLOCK_HEADER > image_len - 1u)
			return FON_LOADER_ERR_FORMAT;
		addr = be32(image + off);
		len = be32(image + off + 4);
		off += FON_LOADER_BLOCK_HEADER;

		if (len == 0 || off + len > image_len)
			return FON_LOADER_ERR_FORMAT;
		if (out->nblocks >= FON_LOADER_MAX_BLOCKS)
			return FON_LOADER_ERR_FORMAT;

		out->blocks[out->nblocks].addr = addr;
		out->blocks[out->nblocks].len = len;
		out->blocks[out->nblocks].data = image + off;
		out->nblocks++;
		off += len;
	}

	if (out->nblocks == 0)
		return FON_LOADER_ERR_FORMAT;

	/* Whatever follows the last block is the image trailer. */
	out->trailer_off = off;
	out->trailer_len = image_len - off;

	for (size_t i = 0; i < image_len; i++)
		acc = (uint8_t)(acc ^ image[i]);
	out->whole_image_xor = acc;

	/*
	 * Accept either the local parser's rule (last byte == XOR of all
	 * preceding bytes) or a trailer we do not understand yet.  The caller
	 * decides what to do: a real image must not be rejected merely because
	 * our checksum model is incomplete.
	 */
	if (out->trailer_len == 1u && image[image_len - 1u] ==
	    (uint8_t)(acc ^ image[image_len - 1u]))
		out->checksum_verified = 1;
	else
		out->checksum_verified = 0;

	return FON_LOADER_OK;
}

size_t fon_loader_host_bytes(const struct fon_loader_level *lvl)
{
	size_t total = 0;

	if (!lvl)
		return 0;
	/* SOH + length field, then each block's header and payload. */
	total += 1u + ((lvl->level == 0) ? 2u : 4u);
	for (unsigned int i = 0; i < lvl->nblocks; i++)
		total += FON_LOADER_BLOCK_HEADER + lvl->blocks[i].len;
	return total;
}

int fon_loader_describe(const struct fon_loader_level *lvl, char *buf,
			size_t cap)
{
	int n;

	if (!lvl || !buf || cap == 0)
		return -1;
	n = snprintf(buf, cap,
		     "level %d: %zu-byte image, %u block(s), trailer %zu B, xor 0x%02x%s",
		     lvl->level, lvl->image_len, lvl->nblocks, lvl->trailer_len,
		     lvl->whole_image_xor,
		     lvl->checksum_verified ? " (verified)" : " (trailer not modelled)");
	if (n < 0 || (size_t)n >= cap)
		return -1;
	return n;
}

enum fon_loader_result fon_loader_run(const struct fon_loader_level *lvl,
				      const struct fon_loader_transport *t,
				      void *transport_ctx)
{
	uint8_t hdr[5];
	size_t hdr_len;
	uint8_t reply;

	if (!lvl || !t || !t->read_byte || !t->write)
		return FON_LOADER_ERR_ARG;

	hdr[0] = FON_DIALOG_SOH;
	if (lvl->level == 0) {
		/* level 0: 2-byte big-endian payload length after SOH */
		hdr[1] = (uint8_t)(lvl->image[0]);
		hdr[2] = (uint8_t)(lvl->image[1]);
		hdr_len = 3;
	} else {
		uint32_t declared = ((uint32_t)lvl->image[0] << 24) |
				    ((uint32_t)lvl->image[1] << 16) |
				    ((uint32_t)lvl->image[2] << 8) |
				    (uint32_t)lvl->image[3];

		hdr[1] = (uint8_t)(declared >> 24);
		hdr[2] = (uint8_t)(declared >> 16);
		hdr[3] = (uint8_t)(declared >> 8);
		hdr[4] = (uint8_t)(declared & 0xff);
		hdr_len = 5;
	}

	/* The transports return 0 on success; anything else is a write error. */
	if (t->write(transport_ctx, hdr, hdr_len) != 0)
		return FON_LOADER_ERR_WRITE;
	/* The transport read fills *out and returns 0 on success. */
	if (t->read_byte(transport_ctx, &reply) != 0)
		return FON_LOADER_ERR_TIMEOUT;
	if (reply != FON_DIALOG_ACK)
		return FON_LOADER_ERR_REPLY;

	for (unsigned int i = 0; i < lvl->nblocks; i++) {
		const struct fon_loader_block *b = &lvl->blocks[i];
		uint8_t bh[FON_LOADER_BLOCK_HEADER];

		bh[0] = (uint8_t)(b->addr >> 24);
		bh[1] = (uint8_t)(b->addr >> 16);
		bh[2] = (uint8_t)(b->addr >> 8);
		bh[3] = (uint8_t)(b->addr);
		bh[4] = (uint8_t)(b->len >> 24);
		bh[5] = (uint8_t)(b->len >> 16);
		bh[6] = (uint8_t)(b->len >> 8);
		bh[7] = (uint8_t)(b->len);

		if (t->write(transport_ctx, bh, sizeof(bh)) != 0)
			return FON_LOADER_ERR_WRITE;
		if (t->write(transport_ctx, b->data, b->len) != 0)
			return FON_LOADER_ERR_WRITE;
		if (t->read_byte(transport_ctx, &reply) != 0)
			return FON_LOADER_ERR_TIMEOUT;
		if (reply != FON_DIALOG_ACK)
			return FON_LOADER_ERR_REPLY;
	}

	return FON_LOADER_OK;
}

static int mock_read(void *ctx, uint8_t *out)
{
	struct fon_loader_mock *m = ctx;

	if (!m || !out || !m->replies || m->pos >= m->len)
		return -1;
	*out = m->replies[m->pos++];
	return 0;
}

static int mock_write(void *ctx, const uint8_t *buf, size_t len)
{
	struct fon_loader_mock *m = ctx;

	if (!m || !buf)
		return -1;
	if (m->fail_after >= 0 && (int)(m->written + len) > m->fail_after)
		return -1;
	m->written += len;
	return 0;
}

void fon_loader_mock_init(struct fon_loader_mock *m, const uint8_t *replies,
			  size_t len)
{
	if (!m)
		return;
	m->replies = replies;
	m->len = len;
	m->pos = 0;
	m->written = 0;
	m->fail_after = -1;
}

/* Exposed for the tests through main.c's mock mode. */
const struct fon_loader_transport fon_loader_mock_transport = {
	.read_byte = mock_read,
	.write = mock_write,
};
