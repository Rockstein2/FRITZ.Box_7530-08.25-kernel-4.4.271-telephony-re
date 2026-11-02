// SPDX-License-Identifier: GPL-2.0-only
/*
 * Clean-room Intel-HEX to Piglet image parser.
 */

#include "fon_dialog_fw.h"

#include <errno.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>

struct hex_record {
	uint32_t addr;
	uint8_t len;
	uint8_t data[255];
};

static int hex_nibble(char c)
{
	if (c >= '0' && c <= '9')
		return c - '0';
	if (c >= 'a' && c <= 'f')
		return c - 'a' + 10;
	if (c >= 'A' && c <= 'F')
		return c - 'A' + 10;
	return -1;
}

static int parse_hex_byte(const char *p, uint8_t *out)
{
	int hi = hex_nibble(p[0]);
	int lo = hex_nibble(p[1]);

	if (hi < 0 || lo < 0)
		return -EINVAL;
	*out = (uint8_t)((hi << 4) | lo);
	return 0;
}

static int record_cmp(const void *a, const void *b)
{
	const struct hex_record *ra = a;
	const struct hex_record *rb = b;

	if (ra->addr < rb->addr)
		return -1;
	if (ra->addr > rb->addr)
		return 1;
	return 0;
}

static int push_record(struct hex_record **records, size_t *count,
		       size_t *capacity, uint32_t addr, const uint8_t *data,
		       size_t len)
{
	struct hex_record *tmp;

	if (len > 255)
		return -E2BIG;
	if (*count == *capacity) {
		size_t new_capacity = *capacity ? *capacity * 2 : 64;

		tmp = realloc(*records, new_capacity * sizeof(**records));
		if (!tmp)
			return -ENOMEM;
		*records = tmp;
		*capacity = new_capacity;
	}
	(*records)[*count].addr = addr;
	(*records)[*count].len = (uint8_t)len;
	memcpy((*records)[*count].data, data, len);
	(*count)++;
	return 0;
}

static int parse_hex(const char *hex, size_t hex_len,
		     struct hex_record **records_out, size_t *count_out)
{
	struct hex_record *records = NULL;
	size_t count = 0, capacity = 0;
	size_t pos = 0;
	uint32_t upper = 0;
	int ret = 0;

	while (pos < hex_len) {
		size_t start = pos, end, line_len, raw_len;
		uint8_t raw[260];
		uint8_t data[255];
		uint8_t n, type;
		uint16_t offset;
		uint8_t sum = 0;
		size_t i;

		while (pos < hex_len && hex[pos] != '\n')
			pos++;
		end = pos;
		if (pos < hex_len)
			pos++;
		while (end > start && (hex[end - 1] == '\r' ||
				      hex[end - 1] == ' ' ||
				      hex[end - 1] == '\t'))
			end--;
		while (start < end && (hex[start] == ' ' || hex[start] == '\t'))
			start++;
		if (start == end)
			continue;
		if (hex[start] != ':') {
			ret = -EINVAL;
			goto out;
		}
		line_len = end - start - 1;
		if (!line_len || (line_len & 1) || line_len / 2 > sizeof(raw)) {
			ret = -EINVAL;
			goto out;
		}
		raw_len = line_len / 2;
		for (i = 0; i < raw_len; i++) {
			ret = parse_hex_byte(&hex[start + 1 + i * 2], &raw[i]);
			if (ret)
				goto out;
			sum = (uint8_t)(sum + raw[i]);
		}
		if (sum != 0 || raw_len < 5) {
			ret = -EINVAL;
			goto out;
		}
		n = raw[0];
		offset = (uint16_t)((raw[1] << 8) | raw[2]);
		type = raw[3];
		if ((size_t)n + 5 != raw_len) {
			ret = -EINVAL;
			goto out;
		}
		memcpy(data, &raw[4], n);
		if (type == 0x00) {
			uint64_t abs = (uint64_t)upper + offset;
			uint64_t end_addr = abs + n;

			if (end_addr > 0xffffffffu) {
				ret = -E2BIG;
				goto out;
			}
			ret = push_record(&records, &count, &capacity,
					  (uint32_t)abs, data, n);
			if (ret)
				goto out;
		} else if (type == 0x01) {
			break;
		} else if (type == 0x02) {
			if (n != 2) {
				ret = -EINVAL;
				goto out;
			}
			upper = (uint32_t)(((data[0] << 8) | data[1]) << 4);
		} else if (type == 0x04) {
			if (n != 2) {
				ret = -EINVAL;
				goto out;
			}
			upper = (uint32_t)(((data[0] << 8) | data[1]) << 16);
		} else {
			ret = -EINVAL;
			goto out;
		}
	}
	if (!count) {
		ret = -EINVAL;
		goto out;
	}
	qsort(records, count, sizeof(*records), record_cmp);
	*records_out = records;
	*count_out = count;
	return 0;
out:
	free(records);
	return ret;
}

static void put_be32(uint8_t *p, uint32_t v)
{
	p[0] = (uint8_t)(v >> 24);
	p[1] = (uint8_t)(v >> 16);
	p[2] = (uint8_t)(v >> 8);
	p[3] = (uint8_t)v;
}

int fon_dialog_build_image(const char *hex, size_t hex_len, int level,
			   struct fon_dialog_image *out)
{
	struct hex_record *records = NULL;
	size_t count = 0, i;
	uint8_t *payload = NULL;
	size_t payload_len = 0, payload_cap;
	size_t header_len;
	uint8_t *image = NULL;
	size_t pos;
	uint8_t checksum = 0;
	int ret;

	if (!hex || !out || (level != 0 && level != 1))
		return -EINVAL;
	memset(out, 0, sizeof(*out));
	ret = parse_hex(hex, hex_len, &records, &count);
	if (ret)
		return ret;

	/* Reject overlapping records after sorting. */
	for (i = 1; i < count; i++) {
		uint64_t prev_end = (uint64_t)records[i - 1].addr +
				    records[i - 1].len;

		if (records[i].addr < prev_end) {
			ret = -EINVAL;
			goto out;
		}
	}

	payload_cap = FON_DIALOG_MAX_IMAGE;
	payload = calloc(1, payload_cap);
	if (!payload) {
		ret = -ENOMEM;
		goto out;
	}

	i = 0;
	while (i < count) {
		size_t first = i;
		uint32_t block_addr = records[i].addr;
		uint64_t block_end = (uint64_t)records[i].addr + records[i].len;
		size_t block_len;
		size_t block_start;
		size_t j;

		i++;
		while (i < count && records[i].addr == block_end) {
			block_end += records[i].len;
			i++;
		}
		block_len = (size_t)(block_end - block_addr);
		if (block_len > 0xffffffffu ||
		    payload_len > payload_cap - FON_DIALOG_BLOCK_HEADER ||
		    block_len > payload_cap - payload_len -
				FON_DIALOG_BLOCK_HEADER) {
			ret = -E2BIG;
			goto out;
		}
		block_start = payload_len;
		put_be32(payload + block_start, block_addr);
		put_be32(payload + block_start + 4, (uint32_t)block_len);
		for (j = first; j < i; j++) {
			struct hex_record *r = &records[j];

			memcpy(payload + block_start + FON_DIALOG_BLOCK_HEADER +
			       (r->addr - block_addr), r->data, r->len);
		}
		payload_len += FON_DIALOG_BLOCK_HEADER + block_len;
	}

	header_len = level == 0 ? 2 : 4;
	if (level == 0 && payload_len > 0xffff) {
		ret = -E2BIG;
		goto out;
	}
	if (payload_len > FON_DIALOG_MAX_IMAGE - header_len - 1) {
		ret = -E2BIG;
		goto out;
	}
	image = calloc(1, header_len + payload_len + 1);
	if (!image) {
		ret = -ENOMEM;
		goto out;
	}
	if (level == 0) {
		image[0] = (uint8_t)(payload_len >> 8);
		image[1] = (uint8_t)payload_len;
	} else {
		put_be32(image, (uint32_t)payload_len);
	}
	memcpy(image + header_len, payload, payload_len);
	for (pos = 0; pos < payload_len; pos++)
		checksum ^= payload[pos];
	image[header_len + payload_len] = checksum;
	out->data = image;
	out->len = header_len + payload_len + 1;
	out->blocks = 0;
	{
		size_t block_count = 0;
		uint64_t end = 0;

		for (i = 0; i < count; i++) {
			if (!block_count ||
			    records[i].addr != end) {
				block_count++;
			}
			end = (uint64_t)records[i].addr + records[i].len;
		}
		out->blocks = (unsigned int)block_count;
	}
	ret = 0;
out:
	free(payload);
	free(records);
	if (ret && image) {
		free(image);
		out->data = NULL;
		out->len = 0;
		out->blocks = 0;
	}
	return ret;
}

void fon_dialog_image_free(struct fon_dialog_image *image)
{
	if (!image)
		return;
	free(image->data);
	image->data = NULL;
	image->len = 0;
	image->blocks = 0;
}

int fon_dialog_build_slow_header(int level, size_t payload_len,
				 uint8_t *out, size_t out_cap,
				 size_t *out_len)
{
	size_t need = level == 0 ? 3 : 5;

	if (!out || !out_len || (level != 0 && level != 1))
		return -EINVAL;
	if (out_cap < need)
		return -E2BIG;
	if (level == 0 && payload_len > 0xffff)
		return -E2BIG;
	out[0] = FON_DIALOG_SOH;
	if (level == 0) {
		out[1] = (uint8_t)(payload_len >> 8);
		out[2] = (uint8_t)payload_len;
	} else {
		put_be32(out + 1, (uint32_t)payload_len);
	}
	*out_len = need;
	return 0;
}

int fon_dialog_build_fast_hello(uint8_t *out, size_t out_cap, size_t *out_len)
{
	static const uint8_t hello[] = "HELLO DCX81";

	if (!out || !out_len)
		return -EINVAL;
	if (out_cap < sizeof(hello) - 1)
		return -E2BIG;
	memcpy(out, hello, sizeof(hello) - 1);
	*out_len = sizeof(hello) - 1;
	return 0;
}

int fon_dialog_check_fast_reply(const uint8_t *reply, size_t len)
{
	static const uint8_t expected[4] = { 0x11, 0xba, 0x5e, 0xba };

	if (!reply)
		return -EINVAL;
	if (len != sizeof(expected))
		return -EINVAL;
	return memcmp(reply, expected, sizeof(expected)) == 0 ? 0 : -EINVAL;
}

int fon_dialog_mock_slow_handshake(const struct fon_dialog_uart_ops *ops,
				   void *ctx, int level, size_t payload_len)
{
	uint8_t header[5];
	size_t header_len;
	int ret;

	if (!ops || !ops->read_byte || !ops->write)
		return -EINVAL;
	ret = ops->read_byte(ctx);
	if (ret != FON_DIALOG_STX)
		return -EPROTO;
	ret = fon_dialog_build_slow_header(level, payload_len, header,
					    sizeof(header), &header_len);
	if (ret)
		return ret;
	ret = ops->write(ctx, header, header_len);
	if (ret < 0)
		return ret;
	if ((size_t)ret != header_len)
		return -EIO;
	ret = ops->read_byte(ctx);
	if (ret != FON_DIALOG_ACK)
		return -EPROTO;
	return 0;
}

int fon_dialog_mock_fast_handshake(const struct fon_dialog_uart_ops *ops,
				   void *ctx)
{
	uint8_t hello[11], reply[11], fast_reply[4];
	size_t i;
	int ret;

	if (!ops || !ops->read_byte || !ops->write)
		return -EINVAL;
	ret = fon_dialog_build_fast_hello(hello, sizeof(hello), &i);
	if (ret)
		return ret;
	ret = ops->write(ctx, hello, i);
	if (ret < 0)
		return ret;
	if ((size_t)ret != i)
		return -EIO;
	for (i = 0; i < sizeof(reply); i++) {
		ret = ops->read_byte(ctx);
		if (ret < 0)
			return ret;
		reply[i] = (uint8_t)ret;
	}
	if (memcmp(reply, "HELLO DCX81", sizeof(reply)) != 0)
		return -EPROTO;
	for (i = 0; i < sizeof(fast_reply); i++) {
		ret = ops->read_byte(ctx);
		if (ret < 0)
			return ret;
		fast_reply[i] = (uint8_t)ret;
	}
	return fon_dialog_check_fast_reply(fast_reply, sizeof(fast_reply));
}
