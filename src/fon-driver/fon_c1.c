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
 * A gated-clock read can raise a synchronous abort or hang the bus.  The
 * caller must treat "no console after this" as an expected failure mode and
 * power-cycle the board.  That is why this lives in its own file and behind
 * its own module parameter.
 */

#include <linux/delay.h>
#include <linux/device.h>
#include <linux/io.h>
#include <linux/platform_device.h>

#include "fon_c1.h"

/*
 * The six values C1 wants.  Offsets come from AVM's ipq-adss.h; the base
 * addresses come from the DT resources, never from hard-coded addresses.
 */
struct fon_c1_probe {
	struct device *dev;
	void __iomem *adss;
	void __iomem *stereo_tx;
	void __iomem *stereo_rx;
	struct clk *ahb;
	struct reset_control *rst;
};

static void c1_log(struct fon_c1_probe *p, const char *step)
{
	dev_info(p->dev, "C1: %s\n", step);
}

int fon_c1_run(struct platform_device *pdev, struct fon_c1_result *out)
{
	struct fon_c1_probe p = { .dev = &pdev->dev };
	int ret;

	if (!out)
		return -EINVAL;

	memset(out, 0, sizeof(*out));
	out->step = -1;

	/*
	 * Step 1: the AHB clock.  Getting it does not mean it is running;
	 * the enable count is reported so the log proves what happened.
	 */
	c1_log(&p, "step 1: request GCC_AUDIO_AHB_CLK");
	p.ahb = devm_clk_get(&pdev->dev, "audio_ahb");
	if (IS_ERR(p.ahb)) {
		out->err = PTR_ERR(p.ahb);
		dev_err(&pdev->dev, "C1: clock 'audio_ahb' unavailable: %d\n",
			out->err);
		return out->err;
	}
	out->step = 1;

	c1_log(&p, "step 2: enable the AHB clock");
	ret = clk_prepare_enable(p.ahb);
	out->clk_enabled = (ret == 0);
	if (ret) {
		out->err = ret;
		dev_err(&pdev->dev, "C1: clk_prepare_enable failed: %d\n", ret);
		return ret;
	}
	out->rate = clk_get_rate(p.ahb);
	dev_info(&pdev->dev, "C1: AHB clock enabled, rate %lu Hz\n",
		 out->rate);
	out->step = 2;

	/* Step 3: the reset line, then the shortest documented pulse. */
	c1_log(&p, "step 3: request the audio reset");
	p.rst = devm_reset_control_get_exclusive(&pdev->dev, "audio_blk");
	if (IS_ERR(p.rst)) {
		out->err = PTR_ERR(p.rst);
		dev_err(&pdev->dev, "C1: reset 'audio_blk' unavailable: %d\n",
			out->err);
		goto out_disable_clk;
	}
	out->step = 3;

	c1_log(&p, "step 4: assert/deassert the audio reset");
	ret = reset_control_assert(p.rst);
	if (ret) {
		out->err = ret;
		dev_err(&pdev->dev, "C1: reset assert failed: %d\n", ret);
		goto out_disable_clk;
	}
	out->reset_pulsed = true;
	usleep_range(20000, 24000);
	ret = reset_control_deassert(p.rst);
	if (ret) {
		out->err = ret;
		dev_err(&pdev->dev, "C1: reset deassert failed: %d\n", ret);
		goto out_disable_clk;
	}
	out->step = 4;

	/*
	 * Step 5: map and read.  ioremap itself does not touch the block;
	 * readl does.  Each read is preceded by a log line so that a hang is
	 * localised by the last message on the console.
	 */
	c1_log(&p, "step 5: map the ADSS window");
	p.adss = devm_platform_ioremap_resource_byname(pdev, "adss");
	if (IS_ERR(p.adss)) {
		out->err = PTR_ERR(p.adss);
		dev_err(&pdev->dev, "C1: cannot map adss: %d\n", out->err);
		goto out_disable_clk;
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
	out->step = 5;

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
	out->step = 11;

	dev_info(&pdev->dev,
		 "C1: audio_mode=0x%08x tdm_ctrl=0x%08x clk_ctrl=0x%08x i2s_rst=0x%08x stereo_tx=0x%08x stereo_rx=0x%08x\n",
		 out->audio_mode, out->tdm_ctrl, out->clk_ctrl, out->i2s_rst,
		 out->stereo_tx_cfg, out->stereo_rx_cfg);

	/*
	 * Step 12: put the block back the way we found it.  Re-asserting the
	 * reset is the conservative choice: AVM leaves the block running,
	 * but we have no proof that an unclocked block is safer than a
	 * held-in-reset one, and a held reset is at least deterministic.
	 */
	c1_log(&p, "step 12: re-assert the reset");
	if (reset_control_assert(p.rst))
		dev_warn(&pdev->dev, "C1: could not re-assert the reset\n");

out_disable_clk:
	c1_log(&p, "step 13: disable the AHB clock");
	clk_disable_unprepare(p.ahb);
	out->clk_enabled = false;
	out->step = 13;
	return 0;
}
