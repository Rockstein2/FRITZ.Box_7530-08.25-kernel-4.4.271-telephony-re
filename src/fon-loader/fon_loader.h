/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef FON_LOADER_H
#define FON_LOADER_H

/*
 * Dry-run planner for the Dialog SC14448 boot firmware transfer.
 *
 * This code never opens a device.  It converts the images produced by the
 * existing HEX parser into an explicit byte-level plan and can execute that
 * plan against an abstract transport, so the whole protocol can be tested
 * offline.
 */

#include <stddef.h>
#include <stdint.h>

#include "fon_dialog_fw.h"

#define FON_LOADER_MAX_BLOCKS 16u
#define FON_LOADER_BLOCK_HEADER 8u

struct fon_loader_block {
	uint32_t addr;
	uint32_t len;
	const uint8_t *data;      /* points into the image buffer */
};

struct fon_loader_level {
	int level;                /* 0 = first level, 1 = second level */
	const uint8_t *image;     /* owned by the caller/parser */
	size_t image_len;
	unsigned int nblocks;
	struct fon_loader_block blocks[FON_LOADER_MAX_BLOCKS];
	size_t trailer_off;       /* first byte after the last block */
	size_t trailer_len;
	uint8_t whole_image_xor;
	int checksum_verified;    /* 1 only for the local parser's rule */
};

enum fon_loader_result {
	FON_LOADER_OK = 0,
	FON_LOADER_ERR_ARG,
	FON_LOADER_ERR_FORMAT,
	FON_LOADER_ERR_TIMEOUT,
	FON_LOADER_ERR_REPLY,
	FON_LOADER_ERR_BLOCK,
	FON_LOADER_ERR_WRITE,
};

/* Abstract transport: one byte in, one byte out, no timing inside. */
struct fon_loader_transport {
	int (*read_byte)(void *ctx, uint8_t *out);
	int (*write)(void *ctx, const uint8_t *buf, size_t len);
	void *ctx;
};

/*
 * Split an image produced by fon_dialog_build_image() into its blocks and
 * verify footer checksum and bounds.  Returns FON_LOADER_OK on success.
 */
enum fon_loader_result fon_loader_level_init(struct fon_loader_level *out,
					     int level,
					     const uint8_t *image,
					     size_t image_len);

/* Bytes the host would send for one level, including the boot header. */
size_t fon_loader_host_bytes(const struct fon_loader_level *lvl);

/* Human-readable plan; writes into buf, returns bytes written or -1. */
int fon_loader_describe(const struct fon_loader_level *lvl, char *buf,
			size_t cap);

/*
 * Execute the plan against a transport.  Every block requires an explicit
 * acknowledgement; a NACK or a missing reply aborts with an error.  There is
 * no retry loop here: the caller decides policy.
 */
enum fon_loader_result fon_loader_run(const struct fon_loader_level *lvl,
				      const struct fon_loader_transport *t,
				      void *transport_ctx);

/* Mock transport used by the tests: answers with a scripted reply stream. */
struct fon_loader_mock {
	const uint8_t *replies;
	size_t len;
	size_t pos;
	size_t written;
	int fail_after;           /* -1 = never */
};

void fon_loader_mock_init(struct fon_loader_mock *m, const uint8_t *replies,
			  size_t len);

/* The transport that drives a struct fon_loader_mock. */
extern const struct fon_loader_transport fon_loader_mock_transport;

#endif /* FON_LOADER_H */
