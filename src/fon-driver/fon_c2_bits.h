/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * Pure helpers shared by fon_c2.c (kernel) and tests/fon_c2_test.c (host).
 *
 * Keeping the bit arithmetic and the readback rule here means the logic that
 * decides success can be tested without the kernel.
 */
#ifndef FON_C2_BITS_H
#define FON_C2_BITS_H

#include <linux/types.h>

/* TDM_CTRL fields (AVM ipq-adss.h). */
#define FON_C2_TDM_TX_CHAN_NUM(slots)  (((slots) - 1) & 0xf)
#define FON_C2_TDM_RX_CHAN_NUM(slots)  ((((slots) - 1) & 0xf) << 16)
#define FON_C2_TDM_TX_DELAY            BIT(25)
#define FON_C2_TDM_RX_DELAY            BIT(26)

/* I2S_RST: AVM writes 0xF, waits 4-5 ms, then writes 0. */
#define FON_C2_I2S_RESET_VAL           0xFu

/* CHIP_CTRL_I2S. */
#define FON_C2_CHIP_I2S_INTERFACE_EN   BIT(0)

/* AUDIO_MODE. */
#define FON_C2_MODE_XMIT_TDM           BIT(0)
#define FON_C2_MODE_RECV_TDM           BIT(2)
#define FON_C2_MODE_B1K                BIT(28)

/* STEREO_CONFIG. */
#define FON_C2_STEREO_MASTER           BIT(8)
#define FON_C2_STEREO_MCK_SEL          BIT(10)
#define FON_C2_STEREO_NO_I2S_DELAY     BIT(18)
#define FON_C2_STEREO_ENABLE           BIT(21)
#define FON_C2_STEREO_DATA_WORD_SIZE(x) (((x) & 3) << 12)
#define FON_C2_STEREO_DATA_WORD_SIZE_MASK FON_C2_STEREO_DATA_WORD_SIZE(3)

/*
 * Bits compared on a STEREO readback.  Everything here is software-owned
 * per ipq-adss.h.  ENABLE/RESET/MIC_RESET are excluded because the vendor
 * code treats them as pulse-like, and they are not part of the format.
 */
#define FON_C2_STEREO_RW_MASK  (FON_C2_STEREO_MASTER | \
				FON_C2_STEREO_MCK_SEL | \
				FON_C2_STEREO_NO_I2S_DELAY | \
				FON_C2_STEREO_DATA_WORD_SIZE_MASK | \
				BIT(11) | BIT(13) | BIT(14) | \
				BIT(16) | BIT(17) | BIT(23) | BIT(24))

struct fon_c2_check {
	bool tdm_ok;
	bool audio_mode_ok;
	bool stereo_tx_ok;
	bool stereo_rx_ok;
	bool all_ok;
	u32 tdm_expected, tdm_actual, tdm_xor;
	u32 mode_expected, mode_actual, mode_xor;
	u32 tx_expected, tx_actual, tx_xor;
	u32 rx_expected, rx_actual, rx_xor;
};

static inline u32 fon_c2_tdm_value(u32 slots)
{
	return FON_C2_TDM_TX_CHAN_NUM(slots) |
	       FON_C2_TDM_RX_CHAN_NUM(slots) |
	       FON_C2_TDM_TX_DELAY | FON_C2_TDM_RX_DELAY;
}

static inline u32 fon_c2_audio_mode_value(u32 before, bool xmit_tdm,
					  bool recv_tdm, bool b1k)
{
	u32 v = before;

	if (xmit_tdm)
		v |= FON_C2_MODE_XMIT_TDM;
	if (recv_tdm)
		v |= FON_C2_MODE_RECV_TDM;
	if (b1k)
		v |= FON_C2_MODE_B1K;
	return v;
}

static inline u32 fon_c2_stereo_value(u32 before, bool slave)
{
	u32 v = before;

	v &= ~(FON_C2_STEREO_MASTER | FON_C2_STEREO_DATA_WORD_SIZE_MASK |
	       BIT(11) | BIT(16) | FON_C2_STEREO_MCK_SEL | BIT(19) | BIT(20));
	v |= FON_C2_STEREO_DATA_WORD_SIZE(1) | FON_C2_STEREO_NO_I2S_DELAY |
	     FON_C2_STEREO_ENABLE | FON_C2_STEREO_MCK_SEL;
	if (!slave)
		v |= FON_C2_STEREO_MASTER;
	return v;
}

static inline void fon_c2_compare(struct fon_c2_check *c,
				  u32 tdm_exp, u32 tdm_act,
				  u32 mode_exp, u32 mode_act,
				  u32 tx_exp, u32 tx_act,
				  u32 rx_exp, u32 rx_act)
{
	c->tdm_expected = tdm_exp;
	c->tdm_actual = tdm_act;
	c->tdm_xor = tdm_exp ^ tdm_act;
	c->tdm_ok = (c->tdm_xor == 0);

	c->mode_expected = mode_exp;
	c->mode_actual = mode_act;
	c->mode_xor = mode_exp ^ mode_act;
	c->audio_mode_ok = (c->mode_xor == 0);

	c->tx_expected = tx_exp;
	c->tx_actual = tx_act;
	c->tx_xor = tx_exp ^ tx_act;
	c->stereo_tx_ok = ((c->tx_xor & FON_C2_STEREO_RW_MASK) == 0);

	c->rx_expected = rx_exp;
	c->rx_actual = rx_act;
	c->rx_xor = rx_exp ^ rx_act;
	c->stereo_rx_ok = ((c->rx_xor & FON_C2_STEREO_RW_MASK) == 0);

	c->all_ok = c->tdm_ok && c->audio_mode_ok &&
		    c->stereo_tx_ok && c->stereo_rx_ok;
}

#endif /* FON_C2_BITS_H */
