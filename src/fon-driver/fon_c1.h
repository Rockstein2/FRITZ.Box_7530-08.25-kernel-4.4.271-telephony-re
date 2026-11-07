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
	int step;              /* last step reached, -1 if none */
	int err;
	bool clk_enabled;
	bool reset_pulsed;
	unsigned long rate;
	u32 audio_mode;
	u32 tdm_ctrl;
	u32 clk_ctrl;
	u32 i2s_rst;
	u32 stereo_tx_cfg;
	u32 stereo_rx_cfg;
};

/*
 * Run the bounded C1 sequence.  Returns 0 when the six reads completed,
 * a negative errno when a resource was missing or a step failed.  A bus
 * hang inside a readl() never returns here.
 */
int fon_c1_run(struct platform_device *pdev, struct fon_c1_result *out);

#endif /* FON_C1_H */
