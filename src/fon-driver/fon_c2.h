/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef FON_C2_H
#define FON_C2_H

#include <linux/clk.h>
#include <linux/platform_device.h>
#include <linux/reset.h>
#include <linux/types.h>

#include "fon_c2_bits.h"

/*
 * Offsets inside the DT-provided windows; see the STEREO address table in
 * docs/fon-adss-clock-reset.md.
 */
#define FON_C2_ADSS_AUDIO_MODE     0x30
#define FON_C2_ADSS_TDM_CTRL       0x1c
#define FON_C2_ADSS_CLK_I2S_CTRL   0x18
#define FON_C2_ADSS_I2S_RST        0x14
#define FON_C2_ADSS_CHIP_CTRL_I2S  0x10
#define FON_C2_STEREO_CONFIG       0x00

struct fon_c2_snapshot {
	u32 chip_ctrl;
	u32 audio_mode;
	u32 tdm_ctrl;
	u32 clk_ctrl;
	u32 i2s_rst;
	u32 stereo_tx;
	u32 stereo_rx;
};

struct fon_c2_result {
	int step;              /* last COMPLETED step, -1 if none */
	int err;
	int cleanup_err;
	bool clk_enabled;
	bool clk_released;
	bool reset_pulsed;
	bool i2s_rst_pulsed;
	bool reset_restored;
	bool cleaned;
	struct fon_c2_snapshot before;
	struct fon_c2_snapshot after;
	u32 tdm_written;
	u32 stereo_tx_written;
	u32 stereo_rx_written;
	u32 audio_mode_written;
	u32 chip_ctrl_written;
	bool all_ok;          /* single source of truth: fon_c2_all_ok() */
	struct fon_c2_check check;
};

/*
 * Program the FON TDM configuration once, read it back, verify every value
 * and return the block to reset.
 *
 * Returns 0 only when every mandatory readback matched AND the cleanup was
 * clean.  Returns -EIO when a mandatory readback did not match, and the
 * cleanup/step errors take precedence over the readback result.
 */
int fon_c2_run(struct platform_device *pdev, struct fon_c2_result *out);

#endif /* FON_C2_H */
