/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef FON_SLOT5_H
#define FON_SLOT5_H

#include <stdint.h>

/*
 * Linux-side slot-5 reference encoder/decoder.
 *
 * This is a data transformation only.  It does not access hardware, MMIO,
 * DMA, GPIO, clocks, reset or firmware.  The physical wire bit order and the
 * SC14448 interpretation remain separate, unproven questions.
 */

#define FON_SLOT5_NORMAL_MARKER  0x4000u
#define FON_SLOT5_SPECIAL_MARKER 0x8000u
#define FON_SLOT5_STATUS_NO_UPDATE 0x80000000u

/*
 * build_slic_ctrl() at pcmlink.ko 0x8f68.
 *
 * special_field is the value read from TDMPriv+0x7f4.  When it is non-zero
 * the code returns special_field | 0x8000; otherwise it serializes the
 * selected bits of virtual registers 0x48 and 0x2c and adds 0x4000.
 */
uint16_t fon_slot5_build_control(uint32_t reg48, uint32_t reg2c,
				 uint16_t special_field);

/*
 * PutRxDMA() at pcmlink.ko 0x9a60.
 *
 * Returns the value written to virtual register 0x44, or
 * FON_SLOT5_STATUS_NO_UPDATE when the RX status has bit 15 set.
 * The caller must not add the 0x4000/0x8000 markers to this result.
 */
uint32_t fon_slot5_decode_status(uint16_t rx_status);

/* slic_get_hook_state(): SLIC0 hook is register 0x44 bit 7. */
static inline int fon_slot5_hook_state(uint32_t reg44)
{
	return (int)((reg44 >> 7) & 1u);
}

/*
 * Build the eight logical 16-bit TX words.  Slots 6 and 7 are audio slots;
 * this function sets them to zero and leaves the caller to fill them from
 * the audio path.  slot4_5555=0 reproduces the TDMPriv+0x808 suppression.
 *
 * This is the logical slot order used by the existing reconstruction.  The
 * TxDMA code writes through an ARM EOR #2 address transformation; byte-level
 * DMA-memory order is a separate representation and is not claimed here.
 */
int fon_slot5_build_frame(uint16_t tx_words[8], uint16_t control);

/* Same as above with explicit slot-4 marker control. */
int fon_slot5_build_frame_ex(uint16_t tx_words[8], uint16_t control,
			     int slot4_5555);

/*
 * Low-level ARM TxDMA representation: the code stores each logical halfword
 * at an address XORed with 2, which swaps adjacent 16-bit words inside every
 * 32-bit DMA word.  This helper makes that raw-memory order explicit.  It is
 * NOT a claim about the physical TDM wire order.
 */
int fon_slot5_frame_to_raw(const uint16_t logical[8], uint16_t raw[8]);
int fon_slot5_raw_to_frame(const uint16_t raw[8], uint16_t logical[8]);

#endif /* FON_SLOT5_H */
