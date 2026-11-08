// SPDX-License-Identifier: GPL-2.0-only
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include "fon_slot5.h"

static int failures;

static void check_u16(const char *name, uint16_t got, uint16_t want)
{
	if (got == want) {
		printf("PASS %s (0x%04x)\n", name, got);
	} else {
		printf("FAIL %s: got 0x%04x want 0x%04x\n", name, got, want);
		failures++;
	}
}

static void check_u32(const char *name, uint32_t got, uint32_t want)
{
	if (got == want) {
		printf("PASS %s (0x%08x)\n", name, got);
	} else {
		printf("FAIL %s: got 0x%08x want 0x%08x\n", name, got, want);
		failures++;
	}
}

int main(void)
{
	uint16_t frame[8];
	uint32_t reg44;
	int i;

	/* Normal control marker and the reg 0x48 4..11 -> control mapping. */
	check_u16("idle control", fon_slot5_build_control(0, 0, 0), 0x4000);
	check_u16("reg48 bit4 -> ctrl bit0",
		  fon_slot5_build_control(1u << 4, 0, 0), 0x4001);
	check_u16("reg48 bit5 -> ctrl bit1",
		  fon_slot5_build_control(1u << 5, 0, 0), 0x4002);
	check_u16("reg48 bit6 -> ctrl bit2",
		  fon_slot5_build_control(1u << 6, 0, 0), 0x4004);
	check_u16("reg48 bit7 -> ctrl bit3",
		  fon_slot5_build_control(1u << 7, 0, 0), 0x4008);
	check_u16("reg48 bit8 -> ctrl bit5",
		  fon_slot5_build_control(1u << 8, 0, 0), 0x4020);
	check_u16("reg48 bit9 -> ctrl bit6",
		  fon_slot5_build_control(1u << 9, 0, 0), 0x4040);
	check_u16("reg48 bit10 -> ctrl bit7",
		  fon_slot5_build_control(1u << 10, 0, 0), 0x4080);
	check_u16("reg48 bit11 -> ctrl bit8",
		  fon_slot5_build_control(1u << 11, 0, 0), 0x4100);
	check_u16("reg48 bit3 is not serialized",
		  fon_slot5_build_control(1u << 3, 0, 0), 0x4000);
	check_u16("reg48 bit12 is not serialized",
		  fon_slot5_build_control(1u << 12, 0, 0), 0x4000);
	check_u16("reg48 bits4..11", fon_slot5_build_control(0x00000ff0u, 0, 0),
		  0x41ef);

	/* reg 0x2c bits 17/18. */
	check_u16("reg2c bit17 -> ctrl bit4",
		  fon_slot5_build_control(0, 1u << 17, 0), 0x4010);
	check_u16("reg2c bit18 -> ctrl bit9",
		  fon_slot5_build_control(0, 1u << 18, 0), 0x4200);
	check_u16("reg2c both -> ctrl bits4/9",
		  fon_slot5_build_control(0, (1u << 17) | (1u << 18), 0),
		  0x4210);

	/* The special path bypasses the normal formula. */
	check_u16("special 1", fon_slot5_build_control(0, 0, 0x0001), 0x8001);
	check_u16("special 0x7fff", fon_slot5_build_control(0, 0, 0x7fff),
		  0xffff);
	check_u16("special marker", fon_slot5_build_control(0, 0, 0x8000),
		  0x8000);
	check_u16("special takes priority over reg48",
		  fon_slot5_build_control(0x00000ff0u, 0, 0x0001), 0x8001);

	/* RX status -> register 0x44.  Bit 3 -> hook bit 7. */
	check_u32("status zero", fon_slot5_decode_status(0x0000), 0x00020008);
	check_u32("status bit0 -> reg44 bit4",
		  fon_slot5_decode_status(0x0001), 0x00020018);
	check_u32("status bit1 -> reg44 bit5",
		  fon_slot5_decode_status(0x0002), 0x00020028);
	check_u32("status bit2 -> reg44 bit6",
		  fon_slot5_decode_status(0x0004), 0x00020048);
	check_u32("status bit3 -> hook bit7",
		  fon_slot5_decode_status(0x0008), 0x00020088);
	check_u32("status bit4 is not mapped to reg44",
		  fon_slot5_decode_status(0x0010), 0x00020008);
	check_u32("status bit5 -> reg44 bit8",
		  fon_slot5_decode_status(0x0020), 0x00020108);
	check_u32("status bit6 -> reg44 bit9",
		  fon_slot5_decode_status(0x0040), 0x00020208);
	check_u32("status bit7 -> reg44 bit10",
		  fon_slot5_decode_status(0x0080), 0x00020408);
	check_u32("status bit8 -> reg44 bit11",
		  fon_slot5_decode_status(0x0100), 0x00020808);
	check_u32("status bit9 is outside the mapping",
		  fon_slot5_decode_status(0x0200), 0x00020008);
	for (i = 10; i <= 14; i++)
		check_u32("status bits 10-14 are outside reg44 mapping",
			  fon_slot5_decode_status((uint16_t)(1u << i)),
			  0x00020008);
	check_u32("status 0x4000 marker still updates reg44",
		  fon_slot5_decode_status(0x4000), 0x00020008);
	check_u32("status 0x8000 means no reg44 update",
		  fon_slot5_decode_status(0x8000),
		  FON_SLOT5_STATUS_NO_UPDATE);
	check_u32("status 0xffff means no update",
		  fon_slot5_decode_status(0xffff),
		  FON_SLOT5_STATUS_NO_UPDATE);

	reg44 = fon_slot5_decode_status(0x0008);
	check_u16("hook bit is set", (uint16_t)fon_slot5_hook_state(reg44), 1);
	reg44 = fon_slot5_decode_status(0x0000);
	check_u16("hook bit is clear", (uint16_t)fon_slot5_hook_state(reg44), 0);

	/* Logical frame layout. */
	memset(frame, 0xaa, sizeof(frame));
	check_u16("frame build return", (uint16_t)fon_slot5_build_frame(frame,
								       0x4200), 0);
	check_u16("frame slot0", frame[0], 0x0000);
	check_u16("frame slot1", frame[1], 0xfefe);
	check_u16("frame slot2", frame[2], 0xfefe);
	check_u16("frame slot3", frame[3], 0xfefe);
	check_u16("frame slot4", frame[4], 0x5555);
	check_u16("frame slot5", frame[5], 0x4200);
	check_u16("frame slot6", frame[6], 0x0000);
	check_u16("frame slot7", frame[7], 0x0000);

	/* Raw ARM TxDMA memory: adjacent 16-bit words are address-XOR-2 swapped. */
	{
		uint16_t raw[8];
		uint16_t back[8];
		check_u16("logical frame to raw",
			  (uint16_t)fon_slot5_frame_to_raw(frame, raw), 0);
		check_u16("raw slot0", raw[0], 0xfefe);
		check_u16("raw slot1", raw[1], 0x0000);
		check_u16("raw slot2", raw[2], 0xfefe);
		check_u16("raw slot3", raw[3], 0xfefe);
		check_u16("raw slot4", raw[4], 0x4200);
		check_u16("raw slot5", raw[5], 0x5555);
		check_u16("raw slot6", raw[6], 0x0000);
		check_u16("raw slot7", raw[7], 0x0000);
		check_u16("raw frame to logical",
			  (uint16_t)fon_slot5_raw_to_frame(raw, back), 0);
		check_u16("round-trip slot0", back[0], frame[0]);
		check_u16("round-trip slot1", back[1], frame[1]);
		check_u16("round-trip slot2", back[2], frame[2]);
		check_u16("round-trip slot3", back[3], frame[3]);
		check_u16("round-trip slot4", back[4], frame[4]);
		check_u16("round-trip slot5", back[5], frame[5]);
		check_u16("round-trip slot6", back[6], frame[6]);
		check_u16("round-trip slot7", back[7], frame[7]);
	}
	{
		uint16_t in_place[8] = { 0, 0xfefe, 0xfefe, 0xfefe,
					 0x5555, 0x4200, 0x1111, 0x2222 };
		check_u16("in-place raw conversion",
			  (uint16_t)fon_slot5_frame_to_raw(in_place,
							   in_place), 0);
		check_u16("in-place raw slot0", in_place[0], 0xfefe);
		check_u16("in-place raw slot1", in_place[1], 0x0000);
		check_u16("in-place raw slot4", in_place[4], 0x4200);
		check_u16("in-place raw slot5", in_place[5], 0x5555);
		check_u16("in-place raw slot6", in_place[6], 0x2222);
		check_u16("in-place raw slot7", in_place[7], 0x1111);
		check_u16("in-place back conversion",
			  (uint16_t)fon_slot5_raw_to_frame(in_place,
							   in_place), 0);
		check_u16("in-place back slot0", in_place[0], 0x0000);
		check_u16("in-place back slot1", in_place[1], 0xfefe);
		check_u16("in-place back slot4", in_place[4], 0x5555);
		check_u16("in-place back slot5", in_place[5], 0x4200);
	}

	check_u16("frame with slot4 suppressed",
		  (uint16_t)fon_slot5_build_frame_ex(frame, 0x4000, 0), 0);
	check_u16("suppressed slot4", frame[4], 0x0000);
	check_u16("null frame rejected",
		  (uint16_t)fon_slot5_build_frame_ex(NULL, 0, 1), 0xffff);

	/* Non-used reg48/reg2c bits must not leak into the control word. */
	for (i = 0; i < 3; i++) {
		check_u16("unused reg48 bit above 11",
			  fon_slot5_build_control(1u << (12 + i), 0, 0),
			  0x4000);
	}

	printf("\n%d failure(s)\n", failures);
	return failures ? 1 : 0;
}
