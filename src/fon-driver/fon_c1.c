// SPDX-License-Identifier: GPL-2.0-only
/*
 * Stage C1: first, carefully bounded access to the ADSS register block.
 *
 * What this does, in this exact order and nothing else:
 *   1. enable GCC_AUDIO_AHB_CLK (the clock that gates the block);
 *   2. assert the audio reset, wait 20-24 ms, deassert it;
 *   3. read six registers once each;
 *   4. release the clock.
 *
 * It does not write any ADSS/MBOX register, does not touch GPIO, does not
 * request an IRQ, does not use DMA and does not talk to the SC14448.
 *
 * Error handling rules used here (they are tested offline):
 *   - every failure stores its errno in out->err;
 *   - out->step always names the last step that COMPLETED, never a cleanup
 *     step;
 *   - a failure of the main sequence and a failure of the cleanup are
 *     reported separately (out->err and out->cleanup_err);
 *   - cleanup runs exactly once, on every exit path, and its result is
 *     never silently dropped;
 *   - the reset state before the run is unknown (there is no API to read
 *     it), so the driver never claims the block was restored exactly.
 */

#include <linux/delay.h>
#include <linux/device.h>
#include <linux/io.h>
#include <linux/platform_device.h>

#include "fon_c1.h"

struct fon_c1_probe {
	struct device *dev;
	void __iomem *adss;
	void __iomem *stereo_tx;
	void __iomem *stereo_rx;
	struct clk *ahb;
	struct reset_control *rst;
};

enum {
	C1_STEP_NONE = -1,
	C1_STEP_CLOCK_GOT = 1,
	C1_STEP_CLOCK_ON = 2,
	C1_STEP_RESET_GOT = 3,
	C1_STEP_RESET_PULSED = 4,
	C1_STEP_MAPPED = 5,
	C1_STEP_READ_DONE = 11,
};

static void c1_log(struct fon_c1_probe *p, const char *s)
{
	dev_info(p->dev, "C1: %s\n", s);
}

/*
 * Release everything acquired so far, exactly once, and record the result.
 * Returns the first cleanup error, or 0.
 */
static int c1_cleanup(struct fon_c1_probe *p, struct fon_c1_result *out)
{
	int ret = 0;
	int rc;

	if (out->cleaned)
		return 0;
	out->cleaned = true;

	/*
	 * Put the block back into reset first: the reset is what stops the
	 * block, so asserting it before dropping the bus clock is the
	 * conservative order.  The previous reset state is unknown, hence
	 * "restored" stays false even when the assert succeeds.
	 */
	if (p->rst && out->reset_pulsed) {
		c1_log(p, "cleanup: re-assert the reset");
		rc = reset_control_assert(p->rst);
		if (rc) {
			dev_warn(p->dev, "C1: cleanup reset assert failed: %d\n",
				 rc);
			ret = ret ? ret : rc;
		} else {
			out->reset_restored = true;
		}
	}

	if (p->ahb && out->clk_enabled) {
		c1_log(p, "cleanup: disable the AHB clock");
		/*
		 * clk_disable_unprepare() returns void: the clock framework
		 * cannot report failure here, and clk_branch2_disable() drops
		 * its -EBUSY, so a halt-bit warning is the only signal.
		 * Record that the clock was dropped, but do not claim it
		 * stopped (see docs/fon-audio-ahb-clock-warning.md).
		 */
		clk_disable_unprepare(p->ahb);
		out->clk_enabled = false;
		out->clk_released = true;
	}

	return ret;
}

int fon_c1_run(struct platform_device *pdev, struct fon_c1_result *out)
{
	struct fon_c1_probe p = { .dev = &pdev->dev };
	int ret = 0;
	int cleanup_ret;

	if (!out)
		return -EINVAL;

	memset(out, 0, sizeof(*out));
	out->step = C1_STEP_NONE;

	/* Step 1: the AHB clock handle.  Getting it does not mean it runs. */
	c1_log(&p, "step 1: request GCC_AUDIO_AHB_CLK");
	p.ahb = devm_clk_get(&pdev->dev, "audio_ahb");
	if (IS_ERR(p.ahb)) {
		ret = PTR_ERR(p.ahb);
		dev_err(&pdev->dev, "C1: clock 'audio_ahb' unavailable: %d\n",
			ret);
		p.ahb = NULL;
		goto out;
	}
	out->step = C1_STEP_CLOCK_GOT;

	c1_log(&p, "step 2: enable the AHB clock");
	ret = clk_prepare_enable(p.ahb);
	if (ret) {
		dev_err(&pdev->dev, "C1: clk_prepare_enable failed: %d\n", ret);
		goto out;
	}
	out->clk_enabled = true;
	out->rate = clk_get_rate(p.ahb);
	dev_info(&pdev->dev, "C1: AHB clock enabled, rate %lu Hz\n",
		 out->rate);
	out->step = C1_STEP_CLOCK_ON;

	/* Step 3: the reset line. */
	c1_log(&p, "step 3: request the audio reset");
	p.rst = devm_reset_control_get_exclusive(&pdev->dev, "audio_blk");
	if (IS_ERR(p.rst)) {
		ret = PTR_ERR(p.rst);
		dev_err(&pdev->dev, "C1: reset 'audio_blk' unavailable: %d\n",
			ret);
		p.rst = NULL;
		goto out;
	}
	out->step = C1_STEP_RESET_GOT;

	/* Step 4: assert, wait, deassert. */
	c1_log(&p, "step 4: assert/deassert the audio reset");
	ret = reset_control_assert(p.rst);
	if (ret) {
		dev_err(&pdev->dev, "C1: reset assert failed: %d\n", ret);
		goto out;
	}
	/* The pulse started, so cleanup must re-assert even if deassert fails. */
	out->reset_pulsed = true;
	usleep_range(20000, 24000);
	ret = reset_control_deassert(p.rst);
	if (ret) {
		dev_err(&pdev->dev, "C1: reset deassert failed: %d\n", ret);
		goto out;
	}
	out->step = C1_STEP_RESET_PULSED;

	/* Step 5: map the windows.  Mapping alone does not touch the block. */
	c1_log(&p, "step 5: map the ADSS window");
	p.adss = devm_platform_ioremap_resource_byname(pdev, "adss");
	if (IS_ERR(p.adss)) {
		ret = PTR_ERR(p.adss);
		dev_err(&pdev->dev, "C1: cannot map adss: %d\n", ret);
		p.adss = NULL;
		goto out;
	}
	p.stereo_tx = devm_platform_ioremap_resource_byname(pdev, "stereo_tx");
	if (IS_ERR(p.stereo_tx)) {
		p.stereo_tx = NULL;
		dev_warn(&pdev->dev, "C1: stereo_tx not mapped, skipping\n");
	}
	p.stereo_rx = devm_platform_ioremap_resource_byname(pdev, "stereo_rx");
	if (IS_ERR(p.stereo_rx)) {
		p.stereo_rx = NULL;
		dev_warn(&pdev->dev, "C1: stereo_rx not mapped, skipping\n");
	}
	out->step = C1_STEP_MAPPED;

	/* Steps 6-11: one read each, logged before it happens. */
	c1_log(&p, "step 6: read AUDIO_MODE");
	out->audio_mode = readl(p.adss + FON_C1_ADSS_AUDIO_MODE);
	c1_log(&p, "step 7: read TDM_CTRL");
	out->tdm_ctrl = readl(p.adss + FON_C1_ADSS_TDM_CTRL);
	c1_log(&p, "step 8: read CLK_I2S_CTRL");
	out->clk_ctrl = readl(p.adss + FON_C1_ADSS_CLK_I2S_CTRL);
	c1_log(&p, "step 9: read I2S_RST");
	out->i2s_rst = readl(p.adss + FON_C1_ADSS_I2S_RST);
	if (p.stereo_tx) {
		c1_log(&p, "step 10: read STEREO_TX_CONFIG");
		out->stereo_tx_cfg = readl(p.stereo_tx + FON_C1_STEREO_CONFIG);
	}
	if (p.stereo_rx) {
		c1_log(&p, "step 11: read STEREO_RX_CONFIG");
		out->stereo_rx_cfg = readl(p.stereo_rx + FON_C1_STEREO_CONFIG);
	}
	out->step = C1_STEP_READ_DONE;

	dev_info(&pdev->dev,
		 "C1: audio_mode=0x%08x tdm_ctrl=0x%08x clk_ctrl=0x%08x i2s_rst=0x%08x stereo_tx=0x%08x stereo_rx=0x%08x\n",
		 out->audio_mode, out->tdm_ctrl, out->clk_ctrl, out->i2s_rst,
		 out->stereo_tx_cfg, out->stereo_rx_cfg);
	ret = 0;

out:
	cleanup_ret = c1_cleanup(&p, out);
	out->cleanup_err = cleanup_ret;
	out->err = ret;

	/*
	 * A cleanup failure is reported even when the main sequence
	 * succeeded: leaving the clock or the reset in an unknown state is
	 * not a success.
	 */
	if (!ret && cleanup_ret)
		ret = cleanup_ret;

	return ret;
}
