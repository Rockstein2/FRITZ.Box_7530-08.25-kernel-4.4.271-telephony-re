// SPDX-License-Identifier: GPL-2.0-only
/*
 * fon-loader: dry-run planner for the SC14448 boot firmware.
 *
 * Usage:
 *   fon-loader plan    HEXFILE LEVEL
 *   fon-loader dry-run HEXFILE LEVEL
 *   fon-loader mock    HEXFILE LEVEL
 *
 * plan     parses and prints the block layout, opens nothing;
 * dry-run  same as plan, plus the exact byte counts and sequence;
 * mock     runs the transfer against a scripted transport that answers ACK.
 *
 * There is no code path that opens a serial device, toggles a GPIO or
 * touches firmware on the chip.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fon_dialog_fw.h"
#include "fon_loader.h"

static char *read_file(const char *path, size_t *len)
{
	FILE *f = fopen(path, "rb");
	char *buf;
	long sz;

	if (!f)
		return NULL;
	if (fseek(f, 0, SEEK_END) != 0) {
		fclose(f);
		return NULL;
	}
	sz = ftell(f);
	if (sz < 0) {
		fclose(f);
		return NULL;
	}
	rewind(f);
	buf = malloc((size_t)sz + 1u);
	if (!buf) {
		fclose(f);
		return NULL;
	}
	if (fread(buf, 1, (size_t)sz, f) != (size_t)sz) {
		free(buf);
		fclose(f);
		return NULL;
	}
	buf[sz] = '\0';
	fclose(f);
	*len = (size_t)sz;
	return buf;
}

static int usage(void)
{
	fprintf(stderr,
		"usage: fon-loader plan|dry-run|mock HEXFILE LEVEL\n"
		"  LEVEL is 0 (first level) or 1 (second level)\n");
	return 2;
}

int main(int argc, char **argv)
{
	const char *cmd, *path;
	int level;
	size_t hex_len = 0;
	char *hex;
	struct fon_dialog_image img = { 0 };
	struct fon_loader_level lvl;
	enum fon_loader_result rc;
	char desc[200];

	if (argc != 4)
		return usage();

	cmd = argv[1];
	path = argv[2];
	level = atoi(argv[3]);
	if (level != 0 && level != 1)
		return usage();

	hex = read_file(path, &hex_len);
	if (!hex) {
		fprintf(stderr, "cannot read %s\n", path);
		return 1;
	}

	if (fon_dialog_build_image(hex, hex_len, level, &img) != 0) {
		fprintf(stderr, "HEX parse failed for %s\n", path);
		free(hex);
		return 1;
	}
	free(hex);

	rc = fon_loader_level_init(&lvl, level, img.data, img.len);
	if (rc != FON_LOADER_OK) {
		fprintf(stderr, "plan rejected (rc=%d)\n", (int)rc);
		fon_dialog_image_free(&img);
		return 1;
	}

	if (fon_loader_describe(&lvl, desc, sizeof(desc)) < 0) {
		fprintf(stderr, "describe failed\n");
		fon_dialog_image_free(&img);
		return 1;
	}
	printf("%s\n", desc);
	for (unsigned int i = 0; i < lvl.nblocks; i++)
		printf("  block %u: addr 0x%08x len %u\n", i,
		       lvl.blocks[i].addr, lvl.blocks[i].len);
	printf("host bytes: %zu, expected replies: %u\n",
	       fon_loader_host_bytes(&lvl), lvl.nblocks + 1u);

	if (strcmp(cmd, "plan") == 0) {
		printf("plan only; nothing sent\n");
	} else if (strcmp(cmd, "dry-run") == 0) {
		printf("sequence: SOH/length -> ACK");
		for (unsigned int i = 0; i < lvl.nblocks; i++)
			printf(" -> block %u -> ACK", i);
		printf("\n");
		printf("dry-run; nothing sent\n");
	} else if (strcmp(cmd, "mock") == 0) {
		uint8_t *replies = calloc(lvl.nblocks + 1u, 1);
		struct fon_loader_mock mock;

		if (!replies) {
			fon_dialog_image_free(&img);
			return 1;
		}
		memset(replies, FON_DIALOG_ACK, lvl.nblocks + 1u);
		fon_loader_mock_init(&mock, replies, lvl.nblocks + 1u);
		rc = fon_loader_run(&lvl, &fon_loader_mock_transport, &mock);
		printf("mock transfer: %s (wrote %zu bytes)\n",
		       rc == FON_LOADER_OK ? "OK" : "FAILED", mock.written);
		free(replies);
		if (rc != FON_LOADER_OK) {
			fon_dialog_image_free(&img);
			return 1;
		}
	} else {
		fon_dialog_image_free(&img);
		return usage();
	}

	fon_dialog_image_free(&img);
	return 0;
}
