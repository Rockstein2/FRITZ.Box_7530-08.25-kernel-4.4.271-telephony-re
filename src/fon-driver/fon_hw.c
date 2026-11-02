// SPDX-License-Identifier: GPL-2.0-only
/*
 * Minimal diagnostic transport for the FRITZ!Box 7530 analog FON port.
 *
 * This driver intentionally stops before telephony:
 *   - it maps ADSS/PCM/MBOX resources from DT;
 *   - it does not read or write MMIO during probe;
 *   - it can allocate and fill TX/RX MBOX DMA rings;
 *   - it never starts DMA automatically;
 *   - it never drives ring/line voltages;
 *   - it has no ALSA/DAHDI/CAPI/DECT integration.
 *
 * The DMA start path is deliberately gated and returns -EOPNOTSUPP until the
 * physical TDM parameters and the SC14448 slot-5 semantics are validated on
 * hardware.
 */

#include <linux/bitops.h>
#include <linux/clk.h>
#include <linux/device.h>
#include <linux/dma-mapping.h>
#include <linux/err.h>
#include <linux/io.h>
#include <linux/kernel.h>
#include <linux/kstrtox.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_device.h>
#include <linux/pinctrl/consumer.h>
#include <linux/platform_device.h>
#include <linux/reset.h>
#include <linux/sysfs.h>
#include <linux/version.h>

#include "fon_hw.h"
#include "fon_tdm.h"

static int fon_tdm_read_diagnostics(struct fon_tdm_dev *tdm);

static bool allow_dma;
module_param(allow_dma, bool, 0444);
MODULE_PARM_DESC(allow_dma,
		 "Allow the explicit dma_start sysfs action (default: false)");

static bool allow_hw_writes;
module_param(allow_hw_writes, bool, 0444);
MODULE_PARM_DESC(allow_hw_writes,
		 "Allow ADSS/MBOX hardware writes and DMA start (default: false)");

static bool allow_mmio_reads;
module_param(allow_mmio_reads, bool, 0444);
MODULE_PARM_DESC(allow_mmio_reads,
		 "Allow explicit read-only MMIO diagnostics after the caller has proven the ADSS clock/reset state (default: false)");

static void fon_dma_ring_free(struct device *dev, struct fon_dma_ring *ring)
{
	if (ring->desc) {
		dma_free_coherent(dev,
				  ring->desc_count * FON_DMA_DESC_STRIDE,
				  ring->desc, ring->desc_dma);
		ring->desc = NULL;
	}
	for (int i = 0; i < 2; i++) {
		if (ring->buf[i]) {
			dma_free_coherent(dev, ring->buf_size,
					  ring->buf[i], ring->buf_dma[i]);
			ring->buf[i] = NULL;
		}
	}
	ring->buf_size = 0;
	ring->desc_count = 0;
}

static int fon_dma_ring_prepare(struct device *dev, struct fon_dma_ring *ring,
				size_t buf_size)
{
	u32 buf_addrs[2];
	unsigned int i;
	int ret = 0;

	ring->desc_count = FON_DMA_DESC_COUNT;
	ring->buf_size = buf_size;
	ring->desc = dma_alloc_coherent(dev,
					ring->desc_count * FON_DMA_DESC_STRIDE,
					&ring->desc_dma, GFP_KERNEL);
	if (!ring->desc)
		return -ENOMEM;

	for (i = 0; i < 2; i++) {
		ring->buf[i] = dma_alloc_coherent(dev, buf_size,
						  &ring->buf_dma[i], GFP_KERNEL);
		if (!ring->buf[i]) {
			ret = -ENOMEM;
			goto err;
		}
		memset(ring->buf[i], 0, buf_size);
	}

	if ((ring->desc_dma | ring->buf_dma[0] | ring->buf_dma[1]) &
	    ~(dma_addr_t)FON_DMA_ADDR_MASK) {
		dev_err(dev,
			"DMA address outside ADSS 28-bit mask: desc=%pad buf0=%pad buf1=%pad\n",
			&ring->desc_dma, &ring->buf_dma[0], &ring->buf_dma[1]);
		ret = -ERANGE;
		goto err;
	}
	if (ring->desc_dma & 3) {
		dev_err(dev, "descriptor ring is not 4-byte aligned: %pad\n",
			&ring->desc_dma);
		ret = -EINVAL;
		goto err;
	}
	for (i = 0; i < 2; i++) {
		if (ring->buf_dma[i] & (L1_CACHE_BYTES - 1)) {
			dev_err(dev,
				"DMA buffer is not cache-line aligned: buf=%pad line=%u\n",
				&ring->buf_dma[i], L1_CACHE_BYTES);
			ret = -EINVAL;
			goto err;
		}
	}

	buf_addrs[0] = (u32)ring->buf_dma[0];
	buf_addrs[1] = (u32)ring->buf_dma[1];
	ret = fon_dma_build_ring(ring->desc,
				 ring->desc_count * FON_DMA_DESC_STRIDE,
				 FON_DMA_DESC_STRIDE,
				 ring->desc_count,
				 (u32)ring->desc_dma,
				 buf_addrs,
				 (u32)buf_size);
	if (ret)
		goto err;
	dma_wmb();
	return 0;

err:
	fon_dma_ring_free(dev, ring);
	return ret;
}

static int fon_tdm_dma_prepare(struct fon_tdm_dev *tdm)
{
	unsigned int frame_bytes;
	size_t buf_size;
	int ret;

	if (tdm->state == FON_STATE_DMA_PREPARED)
		return 0;
	if (tdm->state != FON_STATE_RESOURCES_READY)
		return -ENODEV;

	if (tdm->slots < 2 || tdm->slots > FON_TDM_MAX_SLOTS)
		return -EINVAL;

	frame_bytes = tdm->slots * 2;
	if (frame_bytes < FON_TDM_MIN_FRAME_BYTES)
		return -EINVAL;

	buf_size = frame_bytes * FON_DMA_FRAMES_PER_BUFFER;

	ret = dma_set_mask_and_coherent(tdm->dev, DMA_BIT_MASK(28));
	if (ret) {
		dev_err(tdm->dev, "cannot set ADSS 28-bit DMA mask: %d\n", ret);
		return ret;
	}

	ret = fon_dma_ring_prepare(tdm->dev, &tdm->tx, buf_size);
	if (ret)
		return ret;
	ret = fon_dma_ring_prepare(tdm->dev, &tdm->rx, buf_size);
	if (ret) {
		fon_dma_ring_free(tdm->dev, &tdm->tx);
		return ret;
	}

	tdm->state = FON_STATE_DMA_PREPARED;
	tdm->stage |= FON_STAGE_DMA_READY;
	dev_info(tdm->dev,
		 "DMA rings prepared: slots=%u frame_bytes=%u frames=%u desc=%u\n",
		 tdm->slots, frame_bytes, FON_DMA_FRAMES_PER_BUFFER,
		 FON_DMA_DESC_COUNT);
	return 0;
}

static void fon_tdm_dma_release(struct fon_tdm_dev *tdm)
{
	if (tdm->state != FON_STATE_DMA_PREPARED)
		return;

	fon_dma_ring_free(tdm->dev, &tdm->tx);
	fon_dma_ring_free(tdm->dev, &tdm->rx);
	tdm->state = FON_STATE_RESOURCES_READY;
	tdm->stage &= ~FON_STAGE_DMA_READY;
}

static ssize_t stage_show(struct device *dev, struct device_attribute *attr,
			  char *buf)
{
	struct fon_tdm_dev *tdm = dev_get_drvdata(dev);
	ssize_t ret;

	if (!tdm)
		return -ENODEV;
	mutex_lock(&tdm->lock);
	ret = sysfs_emit(buf, "0x%x\n", tdm->stage);
	mutex_unlock(&tdm->lock);
	return ret;
}

static ssize_t diagnostics_show(struct device *dev, struct device_attribute *attr,
				 char *buf)
{
	struct fon_tdm_dev *tdm = dev_get_drvdata(dev);
	int n = 0;

	if (!tdm)
		return -ENODEV;
	mutex_lock(&tdm->lock);
	n += sysfs_emit_at(buf, n, "state=%u\n", tdm->state);
	n += sysfs_emit_at(buf, n, "diag_valid=%u\n", tdm->diag_valid);
	n += sysfs_emit_at(buf, n, "stage=0x%x\n", tdm->stage);
	n += sysfs_emit_at(buf, n, "slots=%u\n", tdm->slots);
	n += sysfs_emit_at(buf, n, "adss_tx_slots=%u\n", tdm->adss_tx_slots);
	n += sysfs_emit_at(buf, n, "adss_rx_slots=%u\n", tdm->adss_rx_slots);
	n += sysfs_emit_at(buf, n, "irq=%d\n", tdm->irq);
	n += sysfs_emit_at(buf, n, "clk_present=%u\n",
			   (tdm->clks[0] != NULL) + (tdm->clks[1] != NULL) +
			   (tdm->clks[2] != NULL) + (tdm->clks[3] != NULL));
	n += sysfs_emit_at(buf, n, "reset_present=%u\n", tdm->rst != NULL);
	n += sysfs_emit_at(buf, n, "pinctrl_present=%u\n",
			   tdm->pinctrl != NULL);
	n += sysfs_emit_at(buf, n, "audio_mode=0x%08x\n", tdm->audio_mode);
	n += sysfs_emit_at(buf, n, "tdm_ctrl=0x%08x\n", tdm->tdm_ctrl);
	n += sysfs_emit_at(buf, n, "clk_ctrl=0x%08x\n", tdm->clk_ctrl);
	n += sysfs_emit_at(buf, n, "i2s_rst=0x%08x\n", tdm->i2s_rst);
	n += sysfs_emit_at(buf, n, "stereo_tx_cfg=0x%08x\n",
			   tdm->stereo_tx_cfg);
	n += sysfs_emit_at(buf, n, "stereo_rx_cfg=0x%08x\n",
			   tdm->stereo_rx_cfg);
	n += sysfs_emit_at(buf, n, "fon_ctrl_slot=%u\n", FON_TDM_CONTROL_SLOT);
	n += sysfs_emit_at(buf, n, "fon_ctrl_offset=0x%x\n",
			   FON_TDM_CONTROL_OFFSET);
	n += sysfs_emit_at(buf, n, "dma_prepared=%u\n",
			   tdm->state == FON_STATE_DMA_PREPARED);
	n += sysfs_emit_at(buf, n, "dma_started=0\n");
	mutex_unlock(&tdm->lock);
	return n;
}

static ssize_t diag_refresh_store(struct device *dev,
				  struct device_attribute *attr,
				  const char *buf, size_t count)
{
	struct fon_tdm_dev *tdm = dev_get_drvdata(dev);
	bool enable;
	int ret;

	if (!tdm)
		return -ENODEV;
	ret = kstrtobool(buf, &enable);
	if (ret)
		return ret;
	if (!enable)
		return count;

	mutex_lock(&tdm->lock);
	if (tdm->removing) {
		ret = -ENODEV;
		goto out;
	}
	if (!allow_mmio_reads) {
		dev_warn(dev,
			 "MMIO diagnostics refused: load with allow_mmio_reads=1 only after ADSS clock/reset is proven safe\n");
		ret = -EPERM;
		goto out;
	}
	if (tdm->state < FON_STATE_RESOURCES_READY) {
		ret = -ENODEV;
		goto out;
	}
	ret = fon_tdm_read_diagnostics(tdm);
	if (!ret)
		tdm->diag_valid = true;
out:
	mutex_unlock(&tdm->lock);
	return ret ? ret : count;
}

static ssize_t dma_prepare_store(struct device *dev,
				 struct device_attribute *attr,
				 const char *buf, size_t count)
{
	struct fon_tdm_dev *tdm = dev_get_drvdata(dev);
	bool enable;
	int ret;

	if (!tdm)
		return -ENODEV;
	ret = kstrtobool(buf, &enable);
	if (ret)
		return ret;

	mutex_lock(&tdm->lock);
	if (tdm->removing) {
		ret = -ENODEV;
		goto out;
	}
	if (!enable) {
		fon_tdm_dma_release(tdm);
		ret = 0;
		goto out;
	}
	ret = fon_tdm_dma_prepare(tdm);
out:
	mutex_unlock(&tdm->lock);
	return ret ? ret : count;
}

static ssize_t dma_release_store(struct device *dev,
				 struct device_attribute *attr,
				 const char *buf, size_t count)
{
	struct fon_tdm_dev *tdm = dev_get_drvdata(dev);
	bool enable;
	int ret;

	if (!tdm)
		return -ENODEV;
	ret = kstrtobool(buf, &enable);
	if (ret)
		return ret;
	if (!enable)
		return count;

	mutex_lock(&tdm->lock);
	if (tdm->removing)
		ret = -ENODEV;
	else {
		fon_tdm_dma_release(tdm);
		ret = 0;
	}
	mutex_unlock(&tdm->lock);
	return ret ? ret : count;
}

static ssize_t dma_start_store(struct device *dev,
			       struct device_attribute *attr,
			       const char *buf, size_t count)
{
	struct fon_tdm_dev *tdm = dev_get_drvdata(dev);
	bool enable;
	int ret;

	if (!tdm)
		return -ENODEV;
	ret = kstrtobool(buf, &enable);
	if (ret)
		return ret;
	if (!enable)
		return count;

	mutex_lock(&tdm->lock);
	if (tdm->removing) {
		ret = -ENODEV;
		goto out;
	}
	if (tdm->state != FON_STATE_DMA_PREPARED) {
		ret = -EINVAL;
		goto out;
	}
	if (!allow_dma || !allow_hw_writes) {
		dev_warn(dev,
			 "DMA start refused: require allow_dma=1 and allow_hw_writes=1\n");
		ret = -EPERM;
		goto out;
	}

	/*
	 * Deliberately not implemented yet.  The exact slave/master state,
	 * ADSS clock ownership, MBOX policy and SC14448 slot-5 handshake must
	 * be validated on a safe bench before any hardware write.
	 */
	dev_warn(dev,
		 "DMA start is not implemented: TDM/MBOX and SC14448 semantics are not hardware-validated\n");
	ret = -EOPNOTSUPP;
out:
	mutex_unlock(&tdm->lock);
	return ret ? ret : count;
}

static DEVICE_ATTR_RO(stage);
static DEVICE_ATTR_RO(diagnostics);
static DEVICE_ATTR_WO(diag_refresh);
static DEVICE_ATTR_WO(dma_prepare);
static DEVICE_ATTR_WO(dma_release);
static DEVICE_ATTR_WO(dma_start);

static struct attribute *fon_tdm_attrs[] = {
	&dev_attr_stage.attr,
	&dev_attr_diagnostics.attr,
	&dev_attr_diag_refresh.attr,
	&dev_attr_dma_prepare.attr,
	&dev_attr_dma_release.attr,
	&dev_attr_dma_start.attr,
	NULL,
};

static const struct attribute_group fon_tdm_group = {
	.attrs = fon_tdm_attrs,
};

static void __iomem *fon_map_resource(struct platform_device *pdev,
				      const char *name)
{
	struct resource *res;

	res = platform_get_resource_byname(pdev, IORESOURCE_MEM, name);
	if (!res)
		return NULL;
	return devm_ioremap_resource(&pdev->dev, res);
}

static int fon_tdm_read_diagnostics(struct fon_tdm_dev *tdm)
{
	if (tdm->adss) {
		tdm->audio_mode = readl(tdm->adss + FON_ADSS_GLB_AUDIO_MODE_REG);
		tdm->tdm_ctrl = readl(tdm->adss + FON_ADSS_GLB_TDM_CTRL_REG);
		tdm->clk_ctrl = readl(tdm->adss + FON_ADSS_GLB_CLK_I2S_CTRL_REG);
		tdm->i2s_rst = readl(tdm->adss + FON_ADSS_GLB_I2S_RST_REG);
	}
	if (tdm->stereo_tx)
		tdm->stereo_tx_cfg = readl(tdm->stereo_tx +
					   FON_ADSS_STEREO_CONFIG_REG);
	if (tdm->stereo_rx)
		tdm->stereo_rx_cfg = readl(tdm->stereo_rx +
					   FON_ADSS_STEREO_CONFIG_REG);

	if (tdm->adss || tdm->stereo_tx || tdm->stereo_rx)
		tdm->stage |= FON_STAGE_REGS;

	/* TDM channel fields are read-only diagnostics, not a configuration. */
	if (tdm->adss && tdm->tdm_ctrl) {
		unsigned int tx_slots = (tdm->tdm_ctrl & 0xf) + 1;
		unsigned int rx_slots = ((tdm->tdm_ctrl >> 16) & 0xf) + 1;

		tdm->stage |= FON_STAGE_TDM;
		tdm->adss_tx_slots = tx_slots;
		tdm->adss_rx_slots = rx_slots;
		dev_info(tdm->dev,
			 "ADSS TDM: tx_slots=%u rx_slots=%u mode=0x%08x clk=0x%08x rst=0x%08x\n",
			 tx_slots, rx_slots, tdm->tdm_ctrl, tdm->clk_ctrl,
			 tdm->i2s_rst);
		if (tdm->slots != tx_slots || tdm->slots != rx_slots)
			dev_warn(tdm->dev,
				 "DT slots=%u differs from ADSS tx/rx slots=%u/%u\n",
				 tdm->slots, tx_slots, rx_slots);
	}

	return 0;
}

static int fon_tdm_probe(struct platform_device *pdev)
{
	static const char *const clk_names[4] = {
		"audio_tx_bclk", "audio_tx_mclk",
		"audio_rx_bclk", "audio_rx_mclk",
	};
	struct fon_tdm_dev *tdm;
	u32 slots = FON_TDM_SLOTS;
	int i, ret;

	tdm = devm_kzalloc(&pdev->dev, sizeof(*tdm), GFP_KERNEL);
	if (!tdm)
		return -ENOMEM;

	tdm->dev = &pdev->dev;
	tdm->stage = FON_STAGE_PLATFORM;
	tdm->state = FON_STATE_UNINITIALIZED;
	mutex_init(&tdm->lock);
	platform_set_drvdata(pdev, tdm);

	device_property_read_u32(&pdev->dev, "qcom,tdm-slots", &slots);
	if (slots < 2 || slots > FON_TDM_MAX_SLOTS) {
		dev_err(&pdev->dev, "invalid qcom,tdm-slots=%u\n", slots);
		return -EINVAL;
	}
	tdm->slots = slots;
	if (slots != 8)
		dev_warn(&pdev->dev,
			 "qcom,tdm-slots=%u: only the recovered 8-slot FON geometry is validated\n",
			 slots);
	tdm->adss = fon_map_resource(pdev, "adss");
	if (IS_ERR(tdm->adss))
		return PTR_ERR(tdm->adss);
	tdm->pcm = fon_map_resource(pdev, "pcm");
	if (IS_ERR(tdm->pcm))
		return PTR_ERR(tdm->pcm);
	tdm->mbox_tx = fon_map_resource(pdev, "mbox_tx");
	if (IS_ERR(tdm->mbox_tx))
		return PTR_ERR(tdm->mbox_tx);
	tdm->mbox_rx = fon_map_resource(pdev, "mbox_rx");
	if (IS_ERR(tdm->mbox_rx))
		return PTR_ERR(tdm->mbox_rx);
	tdm->stereo_tx = fon_map_resource(pdev, "stereo_tx");
	if (IS_ERR(tdm->stereo_tx))
		return PTR_ERR(tdm->stereo_tx);
	tdm->stereo_rx = fon_map_resource(pdev, "stereo_rx");
	if (IS_ERR(tdm->stereo_rx))
		return PTR_ERR(tdm->stereo_rx);

	if (!tdm->adss && !tdm->pcm && !tdm->mbox_tx && !tdm->mbox_rx) {
		dev_err(&pdev->dev, "no ADSS/PCM/MBOX resources in DT\n");
		return -ENODEV;
	}

	for (i = 0; i < ARRAY_SIZE(tdm->clks); i++) {
		tdm->clks[i] = devm_clk_get_optional(&pdev->dev, clk_names[i]);
		if (IS_ERR(tdm->clks[i]))
			return dev_err_probe(&pdev->dev, PTR_ERR(tdm->clks[i]),
					     "failed to get clock %s\n",
					     clk_names[i]);
	}

	tdm->rst = devm_reset_control_get_optional_exclusive(&pdev->dev, NULL);
	if (IS_ERR(tdm->rst))
		return dev_err_probe(&pdev->dev, PTR_ERR(tdm->rst),
				     "failed to get optional reset\n");

	tdm->pinctrl = devm_pinctrl_get(&pdev->dev);
	if (IS_ERR(tdm->pinctrl))
		tdm->pinctrl = NULL;

	tdm->irq = platform_get_irq_optional(pdev, 0);
	if (tdm->irq == -ENXIO)
		tdm->irq = -1;
	else if (tdm->irq < 0)
		return tdm->irq;

	tdm->stage |= FON_STAGE_RESOURCES;
	tdm->state = FON_STATE_RESOURCES_READY;
	dev_info(&pdev->dev,
		 "resources: adss=%s pcm=%s mbox_tx=%s mbox_rx=%s stereo_tx=%s stereo_rx=%s irq=%d\n",
		 tdm->adss ? "yes" : "no", tdm->pcm ? "yes" : "no",
		 tdm->mbox_tx ? "yes" : "no", tdm->mbox_rx ? "yes" : "no",
		 tdm->stereo_tx ? "yes" : "no", tdm->stereo_rx ? "yes" : "no",
		 tdm->irq);

	/* No MMIO reads during probe; use diag_refresh explicitly. */
	ret = devm_device_add_group(&pdev->dev, &fon_tdm_group);
	if (ret)
		return ret;

	dev_info(&pdev->dev,
		 "FON diagnostic transport ready; DMA and line control disabled\n");
	return 0;
}

#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 11, 0)
static void fon_tdm_remove(struct platform_device *pdev)
#else
static int fon_tdm_remove(struct platform_device *pdev)
#endif
{
	struct fon_tdm_dev *tdm = platform_get_drvdata(pdev);

	if (tdm) {
		mutex_lock(&tdm->lock);
		tdm->removing = true;
		fon_tdm_dma_release(tdm);
		tdm->state = FON_STATE_UNINITIALIZED;
		mutex_unlock(&tdm->lock);
		platform_set_drvdata(pdev, NULL);
	}
#if LINUX_VERSION_CODE < KERNEL_VERSION(6, 11, 0)
	return 0;
#endif
}

static const struct of_device_id fon_tdm_of_match[] = {
	{ .compatible = "avm,fon-tdm" },
	{ }
};
MODULE_DEVICE_TABLE(of, fon_tdm_of_match);

static struct platform_driver fon_tdm_driver = {
	.probe = fon_tdm_probe,
	.remove = fon_tdm_remove,
	.driver = {
		.name = "fon-tdm",
		.of_match_table = fon_tdm_of_match,
	},
};
module_platform_driver(fon_tdm_driver);

MODULE_AUTHOR("FRITZ!Box 7530 FON reverse-engineering project");
MODULE_DESCRIPTION("Minimal diagnostic QCA ADSS/TDM/MBOX transport for FRITZ!Box 7530 FON");
MODULE_LICENSE("GPL");
