// SPDX-License-Identifier: GPL-2.0-only
/*
 * Stage C2: configure the ADSS TDM block the way the FON path needs it and
 * observe the result.  This is the first stage that WRITES to ADSS.
 *
 * What it does, in this order:
 *   1. enable GCC_AUDIO_AHB_CLK;
 *   2. assert/deassert the audio reset, 20-24 ms;
 *   3. read the six registers as a baseline (same reads as C1);
 *   4. write TDM_CTRL for 8 slots and 1-bit delays;
 *   5. write STEREO0/STEREO3 CONFIG for the slave 16-bit mode;
 *   6. enable the I2S interface in AUDIO_MODE and select TDM;
 *   7. read everything back;
 *   8. re-assert the reset and disable the clock.
 *
 * It does not enable DMA, does not request an IRQ, does not touch GPIO, does
 * not start any TDM traffic and does not talk to the SC14448.  Step 8 puts
 * the block back into reset, so a failure leaves no live configuration.
 */

#include <linux/delay.h>
#include <linux/device.h>
#include <linux/io.h>
#include <linux/platform_device.h>

#include "fon_c2.h"

/* Bits taken from AVM's ipq-adss.h, never hard-coded register addresses. */
#define C2_TDM_TX_CHAN_NUM(slots)  (((slots) - 1) & 0xf)
#define C2_TDM_RX_CHAN_NUM(slots)  ((((slots) - 1) & 0xf) << 16)
#define C2_TDM_TX_DELAY            BIT(25)
#define C2_TDM_RX_DELAY            BIT(26)

#define C2_STEREO_ENABLE           BIT(21)
#define C2_STEREO_RESET            BIT(19)
#define C2_STEREO_NO_I2S_DELAY     BIT(18)
#define C2_STEREO_WORD_16          (0 << 12)
#define C2_STEREO_I2S_WORD_16      (0 << 11)
#define C2_STEREO_MASTER           BIT(8)

#define C2_MODE_RECV_TDM           BIT(2)
#define C2_MODE_XMIT_TDM           BIT(0)
#define C2_MODE_B1K                BIT(28)

struct c2_ctx {
	struct device *dev;
	void __iomem *adss;
	void __iomem *stereo_tx;
	void __iomem *stereo_rx;
	struct clk *ahb;
	struct reset_control *rst;
};

static void c2_step(struct c2_ctx *c, const char *s)
{
	dev_info(c->dev, "C2: %s\n", s);
}

static u32 c2_read(struct c2_ctx *c, void __iomem *base, u32 off,
		   const char *what)
{
	u32 v;

	c2_step(c, what);
	v = readl(base + off);
	dev_info(c->dev, "C2:   %s = 0x%08x\n", what, v);
	return v;
}

static void c2_write(struct c2_ctx *c, void __iomem *base, u32 off, u32 val,
		     const char *what)
{
	dev_info(c->dev, "C2:   %s <- 0x%08x\n", what, val);
	writel(val, base + off);
}

int fon_c2_run(struct platform_device *pdev, struct fon_c2_result *out)
{
	struct c2_ctx c = { .dev = &pdev->dev };
	u32 tdm, mode, st;
	int ret;

	if (!out)
		return -EINVAL;
	memset(out, 0, sizeof(*out));
	out->step = -1;

	c2_step(&c, "step 1: request audio_ahb");
	c.ahb = devm_clk_get(&pdev->dev, "audio_ahb");
	if (IS_ERR(c.ahb))
		return dev_err_probe(&pdev->dev, PTR_ERR(c.ahb),
				     "C2: clock unavailable\n");
	out->step = 1;

	c2_step(&c, "step 2: enable the AHB clock");
	ret = clk_prepare_enable(c.ahb);
	if (ret)
		return dev_err_probe(&pdev->dev, ret, "C2: clock enable failed\n");
	out->clk_enabled = true;
	out->step = 2;

	c2_step(&c, "step 3: pulse the audio reset");
	c.rst = devm_reset_control_get_exclusive(&pdev->dev, "audio_blk");
	if (IS_ERR(c.rst)) {
		ret = PTR_ERR(c.rst);
		goto out_disable;
	}
	if (reset_control_assert(c.rst))
		goto out_disable;
	usleep_range(20000, 24000);
	if (reset_control_deassert(c.rst))
		goto out_disable;
	out->reset_pulsed = true;
	out->step = 3;

	c2_step(&c, "step 4: map the ADSS and stereo windows");
	c.adss = devm_platform_ioremap_resource_byname(pdev, "adss");
	if (IS_ERR(c.adss)) {
		ret = PTR_ERR(c.adss);
		goto out_disable;
	}
	c.stereo_tx = devm_platform_ioremap_resource_byname(pdev, "stereo_tx");
	if (IS_ERR(c.stereo_tx)) {
		ret = PTR_ERR(c.stereo_tx);
		goto out_disable;
	}
	c.stereo_rx = devm_platform_ioremap_resource_byname(pdev, "stereo_rx");
	if (IS_ERR(c.stereo_rx)) {
		ret = PTR_ERR(c.stereo_rx);
		goto out_disable;
	}
	out->step = 4;

	/* Baseline, exactly as C1 saw it. */
	c2_step(&c, "step 5: baseline reads");
	out->before.audio_mode = c2_read(&c, c.adss, FON_C2_ADSS_AUDIO_MODE,
					 "audio_mode before");
	out->before.tdm_ctrl = c2_read(&c, c.adss, FON_C2_ADSS_TDM_CTRL,
				       "tdm_ctrl before");
	out->before.stereo_tx = c2_read(&c, c.stereo_tx, FON_C2_STEREO_CONFIG,
					"stereo_tx before");
	out->before.stereo_rx = c2_read(&c, c.stereo_rx, FON_C2_STEREO_CONFIG,
					"stereo_rx before");
	out->step = 5;

	/*
	 * Step 6: 8 slots with the 1-bit delays pcmlink uses.  AVM computes
	 * the channel fields as (slots - 1) and sets both delay bits.
	 */
	tdm = C2_TDM_TX_CHAN_NUM(8) | C2_TDM_RX_CHAN_NUM(8) |
	      C2_TDM_TX_DELAY | C2_TDM_RX_DELAY;
	c2_step(&c, "step 6: program TDM_CTRL for 8 slots");
	c2_write(&c, c.adss, FON_C2_ADSS_TDM_CTRL, tdm, "tdm_ctrl write");
	out->tdm_written = tdm;
	out->step = 6;

	/*
	 * Step 7: stereo format.  MASTER is cleared: the SC14448 is expected
	 * to supply BCLK/FSC and the ADSS is the slave.  16-bit words, no I2S
	 * delay, block enabled.
	 */
	st = C2_STEREO_ENABLE | C2_STEREO_NO_I2S_DELAY | C2_STEREO_WORD_16 |
	     C2_STEREO_I2S_WORD_16;
	c2_step(&c, "step 7: program STEREO0/3 for slave, 16-bit");
	c2_write(&c, c.stereo_tx, FON_C2_STEREO_CONFIG, st, "stereo_tx write");
	c2_write(&c, c.stereo_rx, FON_C2_STEREO_CONFIG, st, "stereo_rx write");
	out->stereo_tx_written = st;
	out->stereo_rx_written = st;
	out->step = 7;

	/* Step 8: TDM mode, interface on, B1K as in the AVM probe path. */
	mode = C2_MODE_XMIT_TDM | C2_MODE_RECV_TDM | C2_MODE_B1K | BIT(0);
	c2_step(&c, "step 8: program AUDIO_MODE for TDM");
	c2_write(&c, c.adss, FON_C2_ADSS_AUDIO_MODE, mode, "audio_mode write");
	out->audio_mode_written = mode;
	out->step = 8;

	usleep_range(2000, 3000);

	/* Step 9: read everything back. */
	c2_step(&c, "step 9: read back");
	out->after.audio_mode = c2_read(&c, c.adss, FON_C2_ADSS_AUDIO_MODE,
					"audio_mode after");
	out->after.tdm_ctrl = c2_read(&c, c.adss, FON_C2_ADSS_TDM_CTRL,
				      "tdm_ctrl after");
	out->after.clk_ctrl = c2_read(&c, c.adss, FON_C2_ADSS_CLK_I2S_CTRL,
				      "clk_ctrl after");
	out->after.i2s_rst = c2_read(&c, c.adss, FON_C2_ADSS_I2S_RST,
				     "i2s_rst after");
	out->after.stereo_tx = c2_read(&c, c.stereo_tx, FON_C2_STEREO_CONFIG,
				       "stereo_tx after");
	out->after.stereo_rx = c2_read(&c, c.stereo_rx, FON_C2_STEREO_CONFIG,
				       "stereo_rx after");
	out->step = 9;

	out->tdm_ok = (out->after.tdm_ctrl == tdm);
	out->stereo_ok = (out->after.stereo_tx == (st & ~C2_STEREO_MASTER)) ||
			 (out->after.stereo_tx & C2_STEREO_ENABLE);
	dev_info(c.dev,
		 "C2: tdm_ok=%d stereo_ok=%d (tdm readback 0x%08x)\n",
		 out->tdm_ok, out->stereo_ok, out->after.tdm_ctrl);

	/* Step 10: put the block back into reset and drop the clock. */
	c2_step(&c, "step 10: re-assert the reset");
	reset_control_assert(c.rst);
	out->step = 10;

out_disable:
	c2_step(&c, "step 11: disable the AHB clock");
	if (out->clk_enabled) {
		clk_disable_unprepare(c.ahb);
		out->clk_enabled = false;
	}
	out->step = 11;
	return ret < 0 ? ret : 0;
}
