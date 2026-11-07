// SPDX-License-Identifier: GPL-2.0-only
/*
 * Offline tests for src/fon-loader.
 *
 * The transport is scripted, so no device can be opened.  The tests build
 * synthetic images in memory and check:
 *   - block parsing and bounds;
 *   - checksum rejection;
 *   - the exact number of host bytes;
 *   - ACK handling, NACK handling, timeout handling and write errors.
 */

#include <stdio.h>
#include <string.h>

#include "fon_loader.h"

static int fails;

#define CHECK(cond, msg) do { \
	if (cond) { \
		printf("PASS %s\n", msg); \
	} else { \
		printf("FAIL %s\n", msg); \
		fails++; \
	} \
} while (0)

/* Build a level-1 image with two blocks. */
static size_t build_image(uint8_t *buf, size_t cap, int level,
			  const uint8_t *b1, uint32_t l1,
			  const uint8_t *b2, uint32_t l2)
{
	size_t hdr = (level == 0) ? 2u : 4u;
	size_t off = hdr;
	size_t payload = 8u + l1 + 8u + l2;
	uint8_t acc = 0;

	if (hdr + payload + 1u > cap)
		return 0;

	if (level == 0) {
		buf[0] = (uint8_t)(payload >> 8);
		buf[1] = (uint8_t)payload;
	} else {
		buf[0] = (uint8_t)(payload >> 24);
		buf[1] = (uint8_t)(payload >> 16);
		buf[2] = (uint8_t)(payload >> 8);
		buf[3] = (uint8_t)payload;
	}

	memcpy(buf + off, "\x00\x00\x10\x00", 4);
	buf[off + 4] = (uint8_t)(l1 >> 24);
	buf[off + 5] = (uint8_t)(l1 >> 16);
	buf[off + 6] = (uint8_t)(l1 >> 8);
	buf[off + 7] = (uint8_t)l1;
	off += 8;
	memcpy(buf + off, b1, l1);
	off += l1;

	memcpy(buf + off, "\x00\x00\x20\x00", 4);
	buf[off + 4] = (uint8_t)(l2 >> 24);
	buf[off + 5] = (uint8_t)(l2 >> 16);
	buf[off + 6] = (uint8_t)(l2 >> 8);
	buf[off + 7] = (uint8_t)l2;
	off += 8;
	memcpy(buf + off, b2, l2);
	off += l2;

	for (size_t i = 0; i < off; i++)
		acc ^= buf[i];
	buf[off++] = acc;
	return off;
}

static void test_parse_ok(void)
{
	uint8_t img[256];
	const uint8_t d1[] = { 1, 2, 3 };
	const uint8_t d2[] = { 4, 5 };
	struct fon_loader_level lvl;
	size_t len;
	enum fon_loader_result rc;

	for (int level = 0; level <= 1; level++) {
		len = build_image(img, sizeof(img), level, d1, 3, d2, 2);
		rc = fon_loader_level_init(&lvl, level, img, len);
		CHECK(rc == FON_LOADER_OK, level ? "level 1 parses" : "level 0 parses");
		CHECK(lvl.nblocks == 2, level ? "level 1 has 2 blocks" : "level 0 has 2 blocks");
		CHECK(lvl.blocks[0].len == 3 && lvl.blocks[1].len == 2,
		      level ? "level 1 lengths" : "level 0 lengths");
		CHECK(lvl.trailer_len == 1 && lvl.checksum_verified == 1,
		      level ? "level 1 local checksum verified"
			    : "level 0 local checksum verified");
		CHECK(fon_loader_host_bytes(&lvl) == (1u + (level ? 4u : 2u) + 8u + 3u + 8u + 2u),
		      level ? "level 1 host bytes" : "level 0 host bytes");
	}
}

static void test_checksum(void)
{
	uint8_t img[256];
	const uint8_t d1[] = { 1, 2, 3 };
	const uint8_t d2[] = { 4, 5 };
	struct fon_loader_level lvl;
	size_t len = build_image(img, sizeof(img), 1, d1, 3, d2, 2);

	img[len - 1] ^= 0xff;
	CHECK(fon_loader_level_init(&lvl, 1, img, len) == FON_LOADER_OK,
	      "unknown trailer is accepted as data");
	CHECK(lvl.checksum_verified == 0,
	      "altered trailer is flagged as unverified");
}

static void test_truncated(void)
{
	uint8_t img[256];
	const uint8_t d1[] = { 1, 2, 3 };
	const uint8_t d2[] = { 4, 5 };
	struct fon_loader_level lvl;
	size_t len = build_image(img, sizeof(img), 1, d1, 3, d2, 2);

	CHECK(fon_loader_level_init(&lvl, 1, img, len - 2) != FON_LOADER_OK,
	      "truncated image rejected");
	CHECK(fon_loader_level_init(&lvl, 1, img, 2) != FON_LOADER_OK,
	      "tiny image rejected");
	CHECK(fon_loader_level_init(&lvl, 2, img, len) == FON_LOADER_ERR_ARG,
	      "bad level rejected");
}

static void test_run_ok(void)
{
	uint8_t img[256];
	const uint8_t d1[] = { 1, 2, 3 };
	const uint8_t d2[] = { 4, 5 };
	struct fon_loader_level lvl;
	struct fon_loader_mock mock;
	uint8_t acks[8];
	size_t len = build_image(img, sizeof(img), 1, d1, 3, d2, 2);

	memset(acks, FON_DIALOG_ACK, sizeof(acks));
	fon_loader_level_init(&lvl, 1, img, len);
	fon_loader_mock_init(&mock, acks, sizeof(acks));
	CHECK(fon_loader_run(&lvl, &fon_loader_mock_transport, &mock) == FON_LOADER_OK,
	      "mock transfer accepts all ACKs");
	CHECK(mock.written == fon_loader_host_bytes(&lvl),
	      "mock transfer wrote exactly the planned bytes");
}

static void test_run_nack(void)
{
	uint8_t img[256];
	const uint8_t d1[] = { 1, 2, 3 };
	const uint8_t d2[] = { 4, 5 };
	struct fon_loader_level lvl;
	struct fon_loader_mock mock;
	uint8_t replies[8];
	size_t len = build_image(img, sizeof(img), 1, d1, 3, d2, 2);

	memset(replies, FON_DIALOG_ACK, sizeof(replies));
	replies[2] = FON_DIALOG_NACK;
	fon_loader_level_init(&lvl, 1, img, len);
	fon_loader_mock_init(&mock, replies, 3);
	CHECK(fon_loader_run(&lvl, &fon_loader_mock_transport, &mock) == FON_LOADER_ERR_REPLY,
	      "NACK aborts the transfer");
}

static void test_run_timeout(void)
{
	uint8_t img[256];
	const uint8_t d1[] = { 1, 2, 3 };
	const uint8_t d2[] = { 4, 5 };
	struct fon_loader_level lvl;
	struct fon_loader_mock mock;
	uint8_t replies[8];
	size_t len = build_image(img, sizeof(img), 1, d1, 3, d2, 2);

	memset(replies, FON_DIALOG_ACK, sizeof(replies));
	fon_loader_level_init(&lvl, 1, img, len);
	/* only the first ACK exists */
	fon_loader_mock_init(&mock, replies, 1);
	CHECK(fon_loader_run(&lvl, &fon_loader_mock_transport, &mock) == FON_LOADER_ERR_TIMEOUT,
	      "missing ACK is a timeout");
}

static void test_run_write_error(void)
{
	uint8_t img[256];
	const uint8_t d1[] = { 1, 2, 3 };
	const uint8_t d2[] = { 4, 5 };
	struct fon_loader_level lvl;
	struct fon_loader_mock mock;
	uint8_t acks[8];
	size_t len = build_image(img, sizeof(img), 1, d1, 3, d2, 2);

	memset(acks, FON_DIALOG_ACK, sizeof(acks));
	fon_loader_level_init(&lvl, 1, img, len);
	fon_loader_mock_init(&mock, acks, sizeof(acks));
	/* The header is 5 bytes; fail on the first block header (5 + 8). */
	mock.fail_after = 5;
	CHECK(fon_loader_run(&lvl, &fon_loader_mock_transport, &mock) == FON_LOADER_ERR_WRITE,
	      "write error aborts");
}

int main(void)
{
	test_parse_ok();
	test_checksum();
	test_truncated();
	test_run_ok();
	test_run_nack();
	test_run_timeout();
	test_run_write_error();

	printf("\n%s\n", fails ? "FAILURES" : "all fon-loader tests passed");
	return fails ? 1 : 0;
}
