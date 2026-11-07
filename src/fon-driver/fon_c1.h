/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef FON_C1_H
#define FON_C1_H

#include <linux/clk.h>
#include <linux/platform_device.h>
#include <linux/reset.h>
#include <linux/types.h>

/*
 * Stage C1 register offsets.  These are offsets inside the DT-provided
 * windows; no absolute address is hard-coded here.
 */
#define FON_C1_ADSS_AUDIO_MODE     0x30
#define FON_C1_ADSS_TDM_CTRL       0x1c
#define FON_C1_ADSS_CLK_I2S_CTRL   0x18
#define FON_C1_ADSS_I2S_RST        0x14
#define FON_C1_STEREO_CONFIG       0x00

struct fon_c1_result {
	int step;              /* last COMPLETED step, -1 if none */
	int err;               /* status of the main sequence */
	int cleanup_err;       /* status of the cleanup, 0 if it was clean */
	bool clk_enabled;      /* clock currently held by the driver */
	bool clk_released;     /* clk_disable_unprepare() was called */
	bool reset_pulsed;     /* assert+deassert were attempted */
	bool reset_restored;   /* the final assert succeeded */
	bool cleaned;          /* cleanup ran */
	unsigned long rate;
	u32 audio_mode;
	u32 tdm_ctrl;
	u32 clk_ctrl;
	u32 i2s_rst;
	u32 stereo_tx_cfg;
	u32 stereo_rx_cfg;
};

/*
 * Run the bounded C1 sequence.  Returns 0 when the six reads completed and
 * the cleanup was clean, a negative errno otherwise.  A bus hang inside a
 * readl() never returns here.
 *
 * The reset state before the call cannot be read back through the API, so a
 * zero return means "the sequence ran and the cleanup reported success", not
 * "the block is in its original state".
 */
int fon_c1_run(struct platform_device *pdev, struct fon_c1_result *out);

#endif /* FON_C1_H */
