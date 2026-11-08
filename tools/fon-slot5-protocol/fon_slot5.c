// SPDX-License-Identifier: GPL-2.0-only
#include "fon_slot5.h"

uint16_t fon_slot5_build_control(uint32_t reg48, uint32_t reg2c,
				 uint16_t special_field)
{
	uint16_t ctrl;

	if (special_field != 0u)
		return (uint16_t)(special_field | FON_SLOT5_SPECIAL_MARKER);

	ctrl = (uint16_t)(((reg48 >> 3) & 0x1e0u) |
			  ((reg48 >> 4) & 0x000fu));

	if (reg2c & (1u << 17))
		ctrl |= 0x0010u;
	if (reg2c & (1u << 18))
		ctrl |= 0x0200u;

	return (uint16_t)(ctrl | FON_SLOT5_NORMAL_MARKER);
}

uint32_t fon_slot5_decode_status(uint16_t rx_status)
{
	if (rx_status & 0x8000u)
		return FON_SLOT5_STATUS_NO_UPDATE;

	return 0x00020008u |
	       (((uint32_t)rx_status << 3) & 0x00000f00u) |
	       (((uint32_t)rx_status << 4) & 0x000000ffu);
}

int fon_slot5_build_frame_ex(uint16_t tx_words[8], uint16_t control,
			     int slot4_5555)
{
	if (!tx_words)
		return -1;

	tx_words[0] = 0x0000u;
	tx_words[1] = 0xfefeu;
	tx_words[2] = 0xfefeu;
	tx_words[3] = 0xfefeu;
	tx_words[4] = slot4_5555 ? 0x5555u : 0x0000u;
	tx_words[5] = control;
	tx_words[6] = 0x0000u;
	tx_words[7] = 0x0000u;
	return 0;
}

int fon_slot5_build_frame(uint16_t tx_words[8], uint16_t control)
{
	return fon_slot5_build_frame_ex(tx_words, control, 1);
}

int fon_slot5_frame_to_raw(const uint16_t logical[8], uint16_t raw[8])
{
	int i;

	if (!logical || !raw)
		return -1;
	for (i = 0; i < 8; i += 2) {
		uint16_t lo = logical[i];
		uint16_t hi = logical[i + 1];
		raw[i] = hi;
		raw[i + 1] = lo;
	}
	return 0;
}

int fon_slot5_raw_to_frame(const uint16_t raw[8], uint16_t logical[8])
{
	int i;

	if (!raw || !logical)
		return -1;
	for (i = 0; i < 8; i += 2) {
		uint16_t lo = raw[i];
		uint16_t hi = raw[i + 1];
		logical[i] = hi;
		logical[i + 1] = lo;
	}
	return 0;
}
