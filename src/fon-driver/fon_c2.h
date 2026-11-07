/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef FON_C2_H
#define FON_C2_H

#include <linux/clk.h>
#include <linux/platform_device.h>
#include <linux/reset.h>
#include <linux/types.h>

/* Offsets inside the DT-provided windows. */
#define FON_C2_ADSS_AUDIO_MODE     0x30
#define FON_C2_ADSS_TDM_CTRL       0x1c
#define FON_C2_ADSS_CLK_I2S_CTRL   0x18
#define FON_C2_ADSS_I2S_RST        0x14
#define FON_C2_STEREO_CONFIG       0x00

struct fon_c2_snapshot {
	u32 audio_mode;
	u32 tdm_ctrl;
	u32 clk_ctrl;
	u32 i2s_rst;
	u32 stereo_tx;
	u32 stereo_rx;
};

struct fon_c2_result {
	int step;
	bool clk_enabled;
	bool reset_pulsed;
	bool tdm_ok;
	bool stereo_ok;
	struct fon_c2_snapshot before;
	struct fon_c2_snapshot after;
	u32 tdm_written;
	u32 stereo_tx_written;
	u32 stereo_rx_written;
	u32 audio_mode_written;
};

/*
 * Write the FON TDM configuration once, read it back and return the block to
 * reset.  Returns 0 when the sequence reached the end, negative errno when a
 * step failed.  A bus hang inside a writel()/readl() never returns here.
 */
int fon_c2_run(struct platform_device *pdev, struct fon_c2_result *out);

#endif /* FON_C2_H */
