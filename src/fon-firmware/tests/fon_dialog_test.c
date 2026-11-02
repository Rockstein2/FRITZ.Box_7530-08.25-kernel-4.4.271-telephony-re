// SPDX-License-Identifier: GPL-2.0-only
/*
 * Host-side tests for the Piglet Intel-HEX/image parser and boot helpers.
 */

#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fon_dialog_fw.h"


struct mock_uart {
	uint8_t in[64];
	size_t in_len;
	size_t in_pos;
	uint8_t out[64];
	size_t out_len;
};

static int mock_read_byte(void *ctx)
{
	struct mock_uart *m = ctx;

	if (m->in_pos >= m->in_len)
		return -1;
	return m->in[m->in_pos++];
}

static int mock_write(void *ctx, const uint8_t *buf, size_t len)
{
	struct mock_uart *m = ctx;

	if (m->out_len + len > sizeof(m->out))
		return -EIO;
	memcpy(m->out + m->out_len, buf, len);
	m->out_len += len;
	return (int)len;
}

static void test_mock_handshakes(void)
{
	static const struct fon_dialog_uart_ops ops = {
		.read_byte = mock_read_byte,
		.write = mock_write,
	};
	struct mock_uart m;

	memset(&m, 0, sizeof(m));
	m.in[0] = FON_DIALOG_STX;
	m.in[1] = FON_DIALOG_ACK;
	m.in_len = 2;
	assert(fon_dialog_mock_slow_handshake(&ops, &m, 0, 0x10) == 0);
	assert(m.out_len == 3 && m.out[0] == FON_DIALOG_SOH &&
	       m.out[1] == 0 && m.out[2] == 0x10);

	memset(&m, 0, sizeof(m));
	m.in[0] = FON_DIALOG_STX;
	m.in[1] = FON_DIALOG_NACK;
	m.in_len = 2;
	assert(fon_dialog_mock_slow_handshake(&ops, &m, 0, 1) == -EPROTO);

	memset(&m, 0, sizeof(m));
	memset(m.in, 0, sizeof(m.in));
	memcpy(m.in, "HELLO DCX81", 11);
	memcpy(m.in + 11, "\x11\xba\x5e\xba", 4);
	m.in_len = 15;
	assert(fon_dialog_mock_fast_handshake(&ops, &m) == 0);
	assert(m.out_len == 11 && memcmp(m.out, "HELLO DCX81", 11) == 0);

}


static const char *one_block =
	":03000000010203F7\n"
	":03000300040506EB\n"
	":00000001FF\n";

static void test_one_block(void)
{
	struct fon_dialog_image image;
	uint8_t expected[] = {
		0x00, 0x0e,                         /* u16be payload length */
		0x00, 0x00, 0x00, 0x00,             /* address */
		0x00, 0x00, 0x00, 0x06,             /* length */
		0x01, 0x02, 0x03, 0x04, 0x05, 0x06,
		0x01,
	};

	assert(fon_dialog_build_image(one_block, strlen(one_block), 0,
				      &image) == 0);
	assert(image.len == sizeof(expected));
	assert(image.blocks == 1);
	assert(memcmp(image.data, expected, sizeof(expected)) == 0);
	fon_dialog_image_free(&image);
	assert(image.data == NULL && image.len == 0);
}

static void test_gap_and_level1(void)
{
	const char *hex =
		":03000000010203F7\n"
		":01001000AA45\n"
		":00000001FF\n";
	struct fon_dialog_image image;
	const uint8_t *p;

	assert(fon_dialog_build_image(hex, strlen(hex), 1, &image) == 0);
	assert(image.blocks == 2);
	assert(image.data[0] == 0x00 && image.data[1] == 0x00 &&
	       image.data[2] == 0x00 && image.data[3] == 0x14);
	p = image.data + 4;
	assert(p[0] == 0 && p[1] == 0 && p[2] == 0 && p[3] == 0);
	assert(p[4] == 0 && p[5] == 0 && p[6] == 0 && p[7] == 3);
	assert(p[8] == 1 && p[9] == 2 && p[10] == 3);
	assert(p[11] == 0 && p[12] == 0 && p[13] == 0 && p[14] == 0x10);
	assert(p[15] == 0 && p[16] == 0 && p[17] == 0 && p[18] == 1);
	assert(p[19] == 0xaa);
	fon_dialog_image_free(&image);
}

static void test_extended_address(void)
{
	const char *hex =
		":020000040001F9\n"
		":0100000055AA\n"
		":00000001FF\n";
	struct fon_dialog_image image;

	assert(fon_dialog_build_image(hex, strlen(hex), 0, &image) == 0);
	assert(image.blocks == 1);
	assert(memcmp(image.data + 2, "\x00\x01\x00\x00"
				       "\x00\x00\x00\x01\x55", 9) == 0);
	fon_dialog_image_free(&image);
}

static void test_invalid(void)
{
	struct fon_dialog_image image;
	const char *bad_checksum =
		":03000000010203F8\n"
		":00000001FF\n";
	const char *duplicate =
		":03000000010203F7\n"
		":03000000040506EA\n"
		":00000001FF\n";

	assert(fon_dialog_build_image(bad_checksum, strlen(bad_checksum), 0,
				      &image) == -EINVAL);
	assert(fon_dialog_build_image(duplicate, strlen(duplicate), 0,
				      &image) == -EINVAL);
	assert(fon_dialog_build_image("junk", 4, 0, &image) == -EINVAL);
	assert(fon_dialog_build_image(one_block, strlen(one_block), 2,
				      &image) == -EINVAL);
	assert(fon_dialog_build_image(NULL, 0, 0, &image) == -EINVAL);
}


static char *read_file(const char *path, size_t *len)
{
	FILE *f = fopen(path, "rb");
	char *buf;
	long size;
	size_t got;

	if (!f)
		return NULL;
	if (fseek(f, 0, SEEK_END) != 0) {
		fclose(f);
		return NULL;
	}
	size = ftell(f);
	if (size < 0 || fseek(f, 0, SEEK_SET) != 0) {
		fclose(f);
		return NULL;
	}
	buf = malloc((size_t)size + 1);
	if (!buf) {
		fclose(f);
		return NULL;
	}
	got = fread(buf, 1, (size_t)size, f);
	fclose(f);
	if (got != (size_t)size) {
		free(buf);
		return NULL;
	}
	buf[got] = '\0';
	*len = got;
	return buf;
}

static void test_real_images(void)
{
	static const struct {
		const char *name;
		int level;
		size_t image_len;
		unsigned int blocks;
	} cases[] = {
		{ "dectfw_firstlevel_441_slow.hex", 0, 0x275, 1 },
		{ "dectfw_secondlevel_441.hex", 1, 0xd36c, 9 },
		{ "dectfw_secondlevel_441p2test.hex", 1, 0xc28d, 8 },
	};
	const char *dirs[] = {
		getenv("FON_FIRMWARE_DIR"),
		"../../../firmware",
		"../../firmware",
		"firmware",
	};
	unsigned int i, d;

	for (i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
		char path[512];
		char *hex = NULL;
		size_t hex_len = 0;

		for (d = 0; d < sizeof(dirs) / sizeof(dirs[0]); d++) {
			if (!dirs[d])
				continue;
			snprintf(path, sizeof(path), "%s/%s", dirs[d],
				 cases[i].name);
			hex = read_file(path, &hex_len);
			if (hex)
				break;
		}
		if (!hex) {
			fprintf(stderr, "skip %s (not present)\n",
				cases[i].name);
			continue;
		}
		{
			struct fon_dialog_image image;

			assert(fon_dialog_build_image(hex, hex_len,
						      cases[i].level,
						      &image) == 0);
			assert(image.len == cases[i].image_len);
			assert(image.blocks == cases[i].blocks);
			fon_dialog_image_free(&image);
			fprintf(stderr, "parsed %s: %zu bytes, %u blocks\n",
				cases[i].name, cases[i].image_len,
				cases[i].blocks);
		}
		free(hex);
	}
}

static void test_boot_helpers(void)
{
	uint8_t buf[16];
	size_t len = 0;
	static const uint8_t fast_reply[4] = { 0x11, 0xba, 0x5e, 0xba };

	assert(fon_dialog_build_slow_header(0, 0x1234, buf, sizeof(buf),
					    &len) == 0);
	assert(len == 3 && buf[0] == 0x01 && buf[1] == 0x12 && buf[2] == 0x34);
	assert(fon_dialog_build_slow_header(1, 0x12345678u, buf, sizeof(buf),
					    &len) == 0);
	assert(len == 5 && buf[0] == 0x01 && buf[1] == 0x12 &&
	       buf[2] == 0x34 && buf[3] == 0x56 && buf[4] == 0x78);
	assert(fon_dialog_build_slow_header(0, 0x10000, buf, sizeof(buf),
					    &len) == -E2BIG);
	assert(fon_dialog_build_slow_header(0, 1, buf, 2, &len) == -E2BIG);
	assert(fon_dialog_build_fast_hello(buf, sizeof(buf), &len) == 0);
	assert(len == 11 && memcmp(buf, "HELLO DCX81", 11) == 0);
	assert(fon_dialog_check_fast_reply(fast_reply, sizeof(fast_reply)) == 0);
	assert(fon_dialog_check_fast_reply(fast_reply, 3) == -EINVAL);
}

int main(void)
{
	test_one_block();
	test_gap_and_level1();
	test_extended_address();
	test_invalid();
	test_boot_helpers();
	test_mock_handshakes();
	test_real_images();
	puts("fon_dialog_test: all tests passed");
	return 0;
}
