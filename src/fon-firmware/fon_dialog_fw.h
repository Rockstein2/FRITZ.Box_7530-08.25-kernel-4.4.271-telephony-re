/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef FON_DIALOG_FW_H
#define FON_DIALOG_FW_H

/*
 * Clean-room parser for the AVM/Piglet Intel-HEX upload image.
 *
 * This is a userspace research/transport component.  It does not upload
 * firmware to a device and it is not linked into the diagnostic TDM driver.
 */

#include <stddef.h>
#include <stdint.h>

#define FON_DIALOG_MAX_IMAGE       0x30005u
#define FON_DIALOG_BLOCK_HEADER    8u
#define FON_DIALOG_SOH             0x01u
#define FON_DIALOG_STX             0x02u
#define FON_DIALOG_ACK             0x06u
#define FON_DIALOG_NACK            0x15u

struct fon_dialog_image {
	uint8_t *data;
	size_t len;
	unsigned int blocks;
};

/**
 * fon_dialog_build_image - convert Intel HEX to the Piglet upload image
 * @hex: Intel HEX text
 * @hex_len: text length
 * @level: 0 = first-level (u16be payload length), 1 = second-level (u32be)
 * @out: caller-owned output descriptor
 *
 * Returns 0 on success.  The caller frees out->data with
 * fon_dialog_image_free().  The format is:
 *
 *   level 0: u16be payload_len, blocks..., xor_checksum
 *   level 1: u32be payload_len, blocks..., xor_checksum
 *
 * Each block is u32be address, u32be length, bytes.
 */
int fon_dialog_build_image(const char *hex, size_t hex_len, int level,
			   struct fon_dialog_image *out);

void fon_dialog_image_free(struct fon_dialog_image *image);

/**
 * fon_dialog_build_slow_header - build SOH + payload length
 * @level: 0 or 1
 * @payload_len: length of the block payload (without outer header/checksum)
 * @out: buffer
 * @out_cap: capacity
 * @out_len: receives the number of bytes written
 *
 * The slow boot path is: DECT sends STX; host sends SOH + length; DECT sends
 * ACK.  This helper builds only the host SOH/length part.
 */
int fon_dialog_build_slow_header(int level, size_t payload_len,
				 uint8_t *out, size_t out_cap,
				 size_t *out_len);

/* Build the 11-byte fast/HELLO probe. */
int fon_dialog_build_fast_hello(uint8_t *out, size_t out_cap, size_t *out_len);

/* Validate the observed four-byte fast/HELLO reply. */
int fon_dialog_check_fast_reply(const uint8_t *reply, size_t len);

/*
 * Minimal mockable UART transport.  This is for offline protocol tests only;
 * it performs one bounded handshake and never sleeps, retries, resets a pin
 * or touches a real UART.
 */
struct fon_dialog_uart_ops {
	int (*read_byte)(void *ctx);
	int (*write)(void *ctx, const uint8_t *buf, size_t len);
};

int fon_dialog_mock_slow_handshake(const struct fon_dialog_uart_ops *ops,
				   void *ctx, int level, size_t payload_len);
int fon_dialog_mock_fast_handshake(const struct fon_dialog_uart_ops *ops,
				   void *ctx);

#endif /* FON_DIALOG_FW_H */
