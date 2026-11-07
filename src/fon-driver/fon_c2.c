// SPDX-License-Identifier: GPL-2.0-only
/*
 * Stage C2: configure the ADSS TDM block the way the FON path needs it and
 * verify the result.  This is the first stage that WRITES to ADSS.
 *
 * Sequence, following AVM's ipq-adss-avm.c ordering:
 *   1. enable GCC_AUDIO_AHB_CLK;
 *   2. assert/deassert the audio reset, 20-24 ms;
 *   3. map the windows and take a baseline snapshot;
 *   4. write ADSS_GLB_CHIP_CTRL_I2S (interface enable) - AVM does this in
 *      intf_audio_adss_probe, before any TDM configuration;
 *   5. write TDM_CTRL for eight slots with the 1-bit delays;
 *   6. write STEREO0/3 CONFIG (slave, 16-bit, MCK_SEL for external clock);
 *   7. write AUDIO_MODE for TDM with B1K;
 *   8. read everything back and compare;
 *   9. re-assert the reset and drop the clock.
 *
 * It does not enable DMA, does not request an IRQ, does not touch GPIO and
 * does not talk to the SC14448.
 */

#include <linux/delay.h>
#include <linux/device.h>
#include <linux/io.h>
#include <linux/platform_device.h>

#include "fon_c2.h"

struct c2_ctx {
	struct device *dev;
	void __iomem *adss;
	void __iomem *stereo_tx;
	void __iomem *stereo_rx;
	struct clk *ahb;
	struct reset_control *rst;
};

enum {
	C2_STEP_NONE = -1,
	C2_STEP_CLOCK_GOT = 1,
	C2_STEP_CLOCK_ON = 2,
	C2_STEP_RESET_GOT = 3,
	C2_STEP_RESET_PULSED = 4,
	C2_STEP_MAPPED = 5,
	C2_STEP_SNAPSHOT = 6,
	C2_STEP_CHIPCTRL = 7,
	C2_STEP_I2S_RST = 8,
	C2_STEP_TDM = 9,
	C2_STEP_STEREO = 10,
	C2_STEP_MODE = 11,
	C2_STEP_VERIFIED = 12,
};

static void c2_log(struct c2_ctx *c, const char *s)
{
	dev_info(c->dev, "C2: %s\n", s);
}

static void c2_snapshot(struct c2_ctx *c, struct fon_c2_snapshot *s)
{
	c2_log(c, "snapshot");
	s->chip_ctrl = readl(c->adss + FON_C2_ADSS_CHIP_CTRL_I2S);
	s->audio_mode = readl(c->adss + FON_C2_ADSS_AUDIO_MODE);
	s->tdm_ctrl = readl(c->adss + FON_C2_ADSS_TDM_CTRL);
	s->clk_ctrl = readl(c->adss + FON_C2_ADSS_CLK_I2S_CTRL);
	s->i2s_rst = readl(c->adss + FON_C2_ADSS_I2S_RST);
	s->stereo_tx = readl(c->stereo_tx + FON_C2_STEREO_CONFIG);
	s->stereo_rx = readl(c->stereo_rx + FON_C2_STEREO_CONFIG);
	dev_info(c->dev,
		 "C2:   chip_ctrl=0x%08x audio_mode=0x%08x tdm_ctrl=0x%08x clk_ctrl=0x%08x i2s_rst=0x%08x st_tx=0x%08x st_rx=0x%08x\n",
		 s->chip_ctrl, s->audio_mode, s->tdm_ctrl, s->clk_ctrl,
		 s->i2s_rst, s->stereo_tx, s->stereo_rx);
}

static int c2_cleanup(struct c2_ctx *c, struct fon_c2_result *out)
{
	int ret = 0;
	int rc;

	if (out->cleaned)
		return 0;
	out->cleaned = true;

	if (c->rst && out->reset_pulsed) {
		c2_log(c, "cleanup: re-assert the reset");
		rc = reset_control_assert(c->rst);
		if (rc) {
			dev_warn(c->dev, "C2: cleanup reset assert failed: %d\n",
				 rc);
			ret = ret ? ret : rc;
		} else {
			out->reset_restored = true;
		}
	}

	if (c->ahb && out->clk_enabled) {
		c2_log(c, "cleanup: disable the AHB clock");
		/* void API; see docs/fon-audio-ahb-clock-warning.md. */
		clk_disable_unprepare(c->ahb);
		out->clk_enabled = false;
		out->clk_released = true;
	}

	return ret;
}

int fon_c2_run(struct platform_device *pdev, struct fon_c2_result *out)
{
	struct c2_ctx c = { .dev = &pdev->dev };
	u32 tdm, mode, st, chip;
	int ret = 0;
	int cleanup_ret;

	if (!out)
		return -EINVAL;
	memset(out, 0, sizeof(*out));
	out->step = C2_STEP_NONE;

	c2_log(&c, "step 1: request audio_ahb");
	c.ahb = devm_clk_get(&pdev->dev, "audio_ahb");
	if (IS_ERR(c.ahb)) {
		ret = PTR_ERR(c.ahb);
		c.ahb = NULL;
		return dev_err_probe(&pdev->dev, ret, "C2: clock unavailable\n");
	}
	out->step = C2_STEP_CLOCK_GOT;

	c2_log(&c, "step 2: enable the AHB clock");
	ret = clk_prepare_enable(c.ahb);
	if (ret) {
		dev_err(&pdev->dev, "C2: clock enable failed: %d\n", ret);
		goto out;
	}
	out->clk_enabled = true;
	out->step = C2_STEP_CLOCK_ON;

	c2_log(&c, "step 3: request and pulse the audio reset");
	c.rst = devm_reset_control_get_exclusive(&pdev->dev, "audio_blk");
	if (IS_ERR(c.rst)) {
		ret = PTR_ERR(c.rst);
		c.rst = NULL;
		dev_err(&pdev->dev, "C2: reset unavailable: %d\n", ret);
		goto out;
	}
	out->step = C2_STEP_RESET_GOT;

	ret = reset_control_assert(c.rst);
	if (ret) {
		dev_err(&pdev->dev, "C2: reset assert failed: %d\n", ret);
		goto out;
	}
	out->reset_pulsed = true;
	usleep_range(20000, 24000);
	ret = reset_control_deassert(c.rst);
	if (ret) {
		dev_err(&pdev->dev, "C2: reset deassert failed: %d\n", ret);
		goto out;
	}
	out->step = C2_STEP_RESET_PULSED;

	c2_log(&c, "step 4: map the ADSS and stereo windows");
	c.adss = devm_platform_ioremap_resource_byname(pdev, "adss");
	if (IS_ERR(c.adss)) {
		ret = PTR_ERR(c.adss);
		c.adss = NULL;
		goto out;
	}
	c.stereo_tx = devm_platform_ioremap_resource_byname(pdev, "stereo_tx");
	if (IS_ERR(c.stereo_tx)) {
		ret = PTR_ERR(c.stereo_tx);
		c.stereo_tx = NULL;
		goto out;
	}
	c.stereo_rx = devm_platform_ioremap_resource_byname(pdev, "stereo_rx");
	if (IS_ERR(c.stereo_rx)) {
		ret = PTR_ERR(c.stereo_rx);
		c.stereo_rx = NULL;
		goto out;
	}
	out->step = C2_STEP_MAPPED;

	c2_log(&c, "step 5: baseline snapshot");
	c2_snapshot(&c, &out->before);
	out->step = C2_STEP_SNAPSHOT;

	/*
	 * AVM enables the I2S/PCM interface in the ADSS probe through
	 * ADSS_GLB_CHIP_CTRL_I2S bit 0.  C2 does the same, before the TDM
	 * configuration, because AUDIO_MODE alone does not open it.
	 */
	chip = out->before.chip_ctrl | FON_C2_CHIP_I2S_INTERFACE_EN;
	c2_log(&c, "step 6: enable CHIP_CTRL_I2S interface");
	dev_info(&pdev->dev, "C2:   chip_ctrl <- 0x%08x\n", chip);
	writel(chip, c.adss + FON_C2_ADSS_CHIP_CTRL_I2S);
	out->chip_ctrl_written = chip;
	out->step = C2_STEP_CHIPCTRL;

	/*
	 * AVM's adss_config_clk() pulses ADSS_GLB_I2S_RST (0x14) BEFORE the TDM
	 * configuration: write the reset value, wait 4-5 ms, write zero.  This
	 * is a write, and it must come before TDM_CTRL, otherwise the block is
	 * configured while its sub-blocks are still held.
	 */
	c2_log(&c, "step 7: pulse I2S_RST");
	dev_info(&pdev->dev, "C2:   i2s_rst <- 0x%08x\n",
		 FON_C2_I2S_RESET_VAL);
	writel(FON_C2_I2S_RESET_VAL, c.adss + FON_C2_ADSS_I2S_RST);
	usleep_range(4000, 5000);
	dev_info(&pdev->dev, "C2:   i2s_rst <- 0x00000000\n");
	writel(0, c.adss + FON_C2_ADSS_I2S_RST);
	out->i2s_rst_pulsed = true;
	out->step = C2_STEP_I2S_RST;

	/* Eight slots, 1-bit delays, exactly as AVM computes them. */
	tdm = fon_c2_tdm_value(8);
	c2_log(&c, "step 8: program TDM_CTRL for 8 slots");
	dev_info(&pdev->dev, "C2:   tdm_ctrl <- 0x%08x\n", tdm);
	writel(tdm, c.adss + FON_C2_ADSS_TDM_CTRL);
	out->tdm_written = tdm;
	out->step = C2_STEP_TDM;

	/*
	 * AVM's adss_config_tdm() clears MASTER, ENABLE, both word-size
	 * fields, MCK_SEL and sets 16-bit data + 16-bit I2S, then sets
	 * ENABLE, and sets MCK_SEL only for the external-clock (slave) case.
	 * The read-modify-write preserves the reserved bits.
	 */
	st = fon_c2_stereo_value(out->before.stereo_tx, true);
	c2_log(&c, "step 9: program STEREO0/3 (slave, 16-bit, ext clock)");
	dev_info(&pdev->dev, "C2:   stereo_tx <- 0x%08x\n", st);
	writel(st, c.stereo_tx + FON_C2_STEREO_CONFIG);
	out->stereo_tx_written = st;

	st = fon_c2_stereo_value(out->before.stereo_rx, true);
	dev_info(&pdev->dev, "C2:   stereo_rx <- 0x%08x\n", st);
	writel(st, c.stereo_rx + FON_C2_STEREO_CONFIG);
	out->stereo_rx_written = st;
	out->step = C2_STEP_STEREO;

	mode = fon_c2_audio_mode_value(out->before.audio_mode, true, true,
				       true);
	c2_log(&c, "step 10: program AUDIO_MODE for TDM");
	dev_info(&pdev->dev, "C2:   audio_mode <- 0x%08x\n", mode);
	writel(mode, c.adss + FON_C2_ADSS_AUDIO_MODE);
	out->audio_mode_written = mode;
	out->step = C2_STEP_MODE;

	usleep_range(2000, 3000);

	c2_log(&c, "step 11: read back and verify");
	c2_snapshot(&c, &out->after);
	fon_c2_compare_chip(&out->check, out->chip_ctrl_written,
			    out->after.chip_ctrl);
	fon_c2_compare_rst(&out->check, out->after.i2s_rst);
	if (!out->check.chip_ctrl_ok)
		dev_err(&pdev->dev,
			"C2: CHIP_CTRL_I2S mismatch: expected INTERFACE_EN, actual 0x%08x xor 0x%08x\n",
			out->check.chip_actual, out->check.chip_xor);
	if (!out->check.i2s_rst_ok)
		dev_err(&pdev->dev,
			"C2: I2S_RST not cleared after the pulse: actual 0x%08x\n",
			out->check.rst_actual);

	fon_c2_compare(&out->check,
		       out->tdm_written, out->after.tdm_ctrl,
		       out->audio_mode_written, out->after.audio_mode,
		       out->stereo_tx_written, out->after.stereo_tx,
		       out->stereo_rx_written, out->after.stereo_rx);
	if (!out->check.tdm_ok)
		dev_err(&pdev->dev,
			"C2: TDM_CTRL mismatch: expected 0x%08x actual 0x%08x xor 0x%08x\n",
			out->check.tdm_expected, out->check.tdm_actual,
			out->check.tdm_xor);
	if (!out->check.audio_mode_ok)
		dev_err(&pdev->dev,
			"C2: AUDIO_MODE mismatch: expected 0x%08x actual 0x%08x xor 0x%08x\n",
			out->check.mode_expected, out->check.mode_actual,
			out->check.mode_xor);
	if (!out->check.stereo_tx_ok)
		dev_err(&pdev->dev,
			"C2: STEREO_TX mismatch: expected 0x%08x actual 0x%08x xor 0x%08x mask 0x%08lx\n",
			out->check.tx_expected, out->check.tx_actual,
			out->check.tx_xor, FON_C2_STEREO_RW_MASK);
	if (!out->check.stereo_rx_ok)
		dev_err(&pdev->dev,
			"C2: STEREO_RX mismatch: expected 0x%08x actual 0x%08x xor 0x%08x mask 0x%08lx\n",
			out->check.rx_expected, out->check.rx_actual,
			out->check.rx_xor, FON_C2_STEREO_RW_MASK);
	out->check.all_ok = fon_c2_all_ok(&out->check);
	out->step = C2_STEP_VERIFIED;
	if (!out->check.all_ok)
		ret = -EIO;

out:
	cleanup_ret = c2_cleanup(&c, out);
	out->cleanup_err = cleanup_ret;
	out->err = ret;
	if (!ret && cleanup_ret)
		ret = cleanup_ret;
	return ret;
}
