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
#include <linux/of_address.h>
#include <linux/of_device.h>
#include <linux/of_irq.h>
#include <linux/irq.h>
#include <linux/pinctrl/consumer.h>
#include <linux/platform_device.h>
#include <linux/reset.h>
#include <linux/sysfs.h>
#include <linux/version.h>

#include "fon_c1.h"
#include "fon_c2.h"
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

/*
 * probe_only is the default and intentionally acquires no MMIO, clock or
 * reset resource.  It is the first hardware-test mode: it only reports what
 * the DT describes and whether sibling DT reg ranges overlap.
 */
static bool probe_only = true;
module_param(probe_only, bool, 0444);
MODULE_PARM_DESC(probe_only,
		 "Do not map MMIO or acquire clocks/reset/pinctrl (default: true)");

/*
 * Stage C1: the first bounded, explicitly authorised access to the ADSS
 * block.  Requires probe_only=0 and run_c1=1, and refuses to run with any
 * other module parameter that would widen the scope (DMA, hardware writes).
 * There is no sysfs trigger: the sequence runs once during probe, so an
 * accidental write cannot re-run it.
 */
static bool run_c1;
module_param(run_c1, bool, 0444);
MODULE_PARM_DESC(run_c1,
		 "Run the bounded Stage C1 ADSS clock/reset/read once during probe (default: false; requires probe_only=0)");

/*
 * Stage C2 is the first stage that WRITES to the ADSS block: it programs the
 * TDM control and stereo format, reads them back, then re-asserts the block
 * reset.  It needs allow_hw_writes=1 as well, so a single forgotten
 * parameter cannot turn a read-only run into a write.
 */
static bool run_c2;
module_param(run_c2, bool, 0444);
MODULE_PARM_DESC(run_c2,
		 "Run the bounded Stage C2 ADSS TDM write test once during probe (default: false; requires probe_only=0 allow_hw_writes=1)");

static const char *const fon_resource_names[FON_RESOURCE_COUNT] = {
	"adss", "pcm", "mbox_tx", "mbox_rx", "stereo_tx", "stereo_rx",
};

/*
 * Raw DT interrupt specifiers.  These are NOT Linux virqs and do not create
 * any IRQ mapping.  A raw GIC SPI value of 156 has GIC INTID 188; the Linux
 * virq may not exist at all and is only obtained in full mode through
 * platform_get_irq_optional().
 */
static int fon_parse_dt_irq(struct device *dev, unsigned int index,
			    u32 *spi, u32 *intid)
{
	struct of_phandle_args args;
	int ret;

	ret = of_irq_parse_one(dev->of_node, index, &args);
	if (ret)
		return ret;
	if (args.args_count < 2) {
		of_node_put(args.np);
		return -EINVAL;
	}
	if (args.args[0] != 0) {	/* GIC_SPI only */
		of_node_put(args.np);
		return -EINVAL;
	}
	*spi = args.args[1];
	*intid = args.args[1] + 32;
	of_node_put(args.np);
	return 0;
}

static unsigned int fon_dt_string_count(struct device_node *np,
					  const char *name)
{
	int count = of_property_count_strings(np, name);

	return count > 0 ? (unsigned int)count : 0;
}

/*
 * Number of phandles in a <name> property, e.g. clocks = <&gcc ID>.
 * This is deliberately separate from <name>-names: a node can describe a
 * clock without naming it, and C1 relies on exactly that case.  Reporting
 * only <name>-names made "clock_refs=0" mean nothing, so both are counted
 * and the raw property is reported verbatim.
 */
static unsigned int fon_dt_phandle_count(struct device_node *np,
					 const char *name)
{
	int count = of_count_phandle_with_args(np, name, NULL);

	return count > 0 ? (unsigned int)count : 0;
}

static bool fon_resource_overlap(const struct resource *a,
				 const struct resource *b)
{
	return a->start <= b->end && b->start <= a->end;
}

/*
 * DT-level overlap check only.  It detects sibling nodes that describe
 * overlapping reg ranges; it cannot prove which driver owns an iomem
 * resource.  It performs no request_mem_region() and no MMIO access.
 */
static bool fon_dt_resource_overlaps(struct device_node *np,
				     struct resource *res)
{
	struct device_node *sibling;
	unsigned int index;

	for_each_child_of_node(np->parent, sibling) {
		struct resource other;

		if (sibling == np)
			continue;
		for (index = 0; index < 16; index++) {
			if (of_address_to_resource(sibling, index, &other))
				break;
			if (fon_resource_overlap(res, &other)) {
				of_node_put(sibling);
				return true;
			}
		}
	}
	return false;
}

static void fon_report_resources(struct fon_tdm_dev *tdm)
{
	struct device_node *np = tdm->dev->of_node;
	unsigned int i;

	tdm->clock_refs = fon_dt_phandle_count(np, "clocks") +
			  fon_dt_string_count(np, "clock-names");
	tdm->reset_refs = fon_dt_phandle_count(np, "resets") +
			  fon_dt_string_count(np, "reset-names");
	tdm->pinctrl_ref = of_find_property(np, "pinctrl-0", NULL) != NULL;

	for (i = 0; i < FON_RESOURCE_COUNT; i++) {
		struct resource *res = platform_get_resource_byname(
			to_platform_device(tdm->dev), IORESOURCE_MEM,
			fon_resource_names[i]);

		if (!res)
			continue;
		tdm->resource_mask |= BIT(i);
		tdm->dt_res[i] = res;
		if (fon_dt_resource_overlaps(np, res)) {
			tdm->dt_overlap = true;
			dev_warn(tdm->dev,
				 "DT reg overlap: %s %pa-%pa\n",
				 fon_resource_names[i], &res->start, &res->end);
		}
	}
}

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
	if (!tdm->adss || !tdm->mbox_tx || !tdm->mbox_rx ||
	    !tdm->stereo_tx || !tdm->stereo_rx)
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
	n += sysfs_emit_at(buf, n, "mode=%s\n",
			   tdm->probe_only ? "probe-only" : "full");
	n += sysfs_emit_at(buf, n, "state=%u\n", tdm->state);
	n += sysfs_emit_at(buf, n, "diag_valid=%u\n", tdm->diag_valid);
	n += sysfs_emit_at(buf, n, "stage=0x%x\n", tdm->stage);
	n += sysfs_emit_at(buf, n, "resource_mask=0x%x\n", tdm->resource_mask);
	n += sysfs_emit_at(buf, n, "dt_overlap=%u\n", tdm->dt_overlap);
	n += sysfs_emit_at(buf, n, "clock_refs=%u\n", tdm->clock_refs);
	n += sysfs_emit_at(buf, n, "reset_refs=%u\n", tdm->reset_refs);
	n += sysfs_emit_at(buf, n, "dt_clocks=%u\n",
			   fon_dt_phandle_count(tdm->dev->of_node, "clocks"));
	n += sysfs_emit_at(buf, n, "dt_clock_names=%u\n",
			   fon_dt_string_count(tdm->dev->of_node, "clock-names"));
	n += sysfs_emit_at(buf, n, "dt_resets=%u\n",
			   fon_dt_phandle_count(tdm->dev->of_node, "resets"));
	n += sysfs_emit_at(buf, n, "dt_reset_names=%u\n",
			   fon_dt_string_count(tdm->dev->of_node, "reset-names"));
	n += sysfs_emit_at(buf, n, "pinctrl_ref=%u\n", tdm->pinctrl_ref);
	n += sysfs_emit_at(buf, n, "slots=%u\n", tdm->slots);
	for (unsigned int i = 0; i < FON_RESOURCE_COUNT; i++) {
		struct resource *res = tdm->dt_res[i];

		if (!res)
			continue;
		n += sysfs_emit_at(buf, n,
				   "resource[%u]=%s start=0x%llx end=0x%llx\n",
				   i, fon_resource_names[i],
				   (unsigned long long)res->start,
				   (unsigned long long)res->end);
	}
	n += sysfs_emit_at(buf, n, "adss_tx_slots=%u\n", tdm->adss_tx_slots);
	n += sysfs_emit_at(buf, n, "adss_rx_slots=%u\n", tdm->adss_rx_slots);
	n += sysfs_emit_at(buf, n, "irq_spi=%u/%u\n",
			   tdm->irq_spi[0], tdm->irq_spi[1]);
	n += sysfs_emit_at(buf, n, "irq_intid=%u/%u\n",
			   tdm->irq_intid[0], tdm->irq_intid[1]);
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
	if (tdm->probe_only) {
		dev_warn(dev, "MMIO diagnostics refused in probe-only mode\n");
		ret = -EPERM;
		goto out;
	}
	if (!allow_mmio_reads) {
		dev_warn(dev,
			 "MMIO diagnostics refused: load with allow_mmio_reads=1 only after ADSS clock/reset is proven safe\n");
		ret = -EPERM;
		goto out;
	}
	if (tdm->state < FON_STATE_RESOURCES_READY ||
	    (!tdm->adss && !tdm->stereo_tx && !tdm->stereo_rx)) {
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
	if (tdm->probe_only) {
		dev_warn(dev, "DMA prepare refused in probe-only mode\n");
		ret = -EPERM;
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
	tdm->probe_only = probe_only;
	fon_report_resources(tdm);
	if (!tdm->resource_mask) {
		dev_err(&pdev->dev, "no ADSS/PCM/MBOX resources in DT\n");
		return -ENODEV;
	}

	/*
	 * Probe-only parses the raw DT interrupt specifiers; it must not call
	 * platform_get_irq_optional()/of_irq_get(), because that creates a
	 * Linux IRQ mapping and may set the trigger type in the GIC domain.
	 */
	tdm->irq_spi[0] = tdm->irq_spi[1] = 0;
	tdm->irq_intid[0] = tdm->irq_intid[1] = 0;
	for (i = 0; i < 2; i++) {
		u32 spi, intid;
		int rc = fon_parse_dt_irq(&pdev->dev, i, &spi, &intid);

		if (rc) {
			dev_warn(&pdev->dev,
				 "DT IRQ[%u] parse failed: %d\n", i, rc);
			continue;
		}
		tdm->irq_spi[i] = spi;
		tdm->irq_intid[i] = intid;
	}

	if (tdm->probe_only) {
		tdm->irq = -1;
		tdm->stage |= FON_STAGE_RESOURCES | FON_STAGE_PROBE_ONLY;
		tdm->state = FON_STATE_RESOURCES_READY;
		dev_info(&pdev->dev,
			 "probe-only: resources=0x%x irq_spi=%u/%u irq_intid=%u/%u clock_refs=%u reset_refs=%u pinctrl_ref=%u dt_overlap=%u\n",
			 tdm->resource_mask, tdm->irq_spi[0], tdm->irq_spi[1],
			 tdm->irq_intid[0], tdm->irq_intid[1],
			 tdm->clock_refs, tdm->reset_refs, tdm->pinctrl_ref,
			 tdm->dt_overlap);
		ret = devm_device_add_group(&pdev->dev, &fon_tdm_group);
		if (ret)
			return ret;
		dev_info(&pdev->dev,
			 "FON probe-only ready; no MMIO/clock/reset/IRQ/DMA access\n");
		if (run_c1)
			dev_warn(&pdev->dev,
				 "run_c1 ignored: it requires probe_only=0\n");
		return 0;
	}

	/*
	 * Stage C1 is deliberately exclusive: it needs the real clock and reset
	 * resources, so it cannot run together with probe_only, with DMA
	 * permission or with hardware writes.  Anything ambiguous refuses.
	 */
	if (run_c2) {
		struct fon_c2_result c2;
		int c2_ret;

		if (!allow_hw_writes) {
			dev_err(&pdev->dev,
				"C2 refused: run_c2 additionally requires allow_hw_writes=1\n");
			return -EINVAL;
		}
		if (allow_dma) {
			dev_err(&pdev->dev,
				"C2 refused: run_c2 requires allow_dma=0\n");
			return -EINVAL;
		}
		dev_warn(&pdev->dev,
			 "C2: programming TDM for 8 slots and stereo for slave mode, then reading back\n");
		c2_ret = fon_c2_run(pdev, &c2);
		dev_warn(&pdev->dev,
			 "C2 finished: step=%d err=%d cleanup_err=%d tdm=%d mode=%d tx=%d rx=%d\n",
			 c2.step, c2.err, c2.cleanup_err,
			 c2.check.tdm_ok, c2.check.audio_mode_ok,
			 c2.check.stereo_tx_ok, c2.check.stereo_rx_ok);
		if (c2_ret)
			return c2_ret;
		return 0;
	}

	if (run_c1) {
		struct fon_c1_result c1;
		int c1_ret;

		if (allow_dma || allow_hw_writes) {
			dev_err(&pdev->dev,
				"C1 refused: run_c1 requires allow_dma=0 and allow_hw_writes=0\n");
			return -EINVAL;
		}
		dev_warn(&pdev->dev,
			 "C1: enabling the audio AHB clock, pulsing the audio reset and reading six registers once\n");
		c1_ret = fon_c1_run(pdev, &c1);
		dev_warn(&pdev->dev,
			 "C1 finished: step=%d err=%d clk_enabled=%d reset_pulsed=%d\n",
			 c1.step, c1.err, c1.clk_enabled, c1.reset_pulsed);
		if (c1_ret)
			return c1_ret;
		/* C1 is a one-shot: leave the probe path afterwards. */
		return 0;
	}

	tdm->irq = platform_get_irq_optional(pdev, 0);
	if (tdm->irq == -ENXIO)
		tdm->irq = -1;
	else if (tdm->irq == -EPROBE_DEFER)
		return -EPROBE_DEFER;
	else if (tdm->irq < 0) {
		dev_warn(&pdev->dev, "optional IRQ unavailable: %d\n", tdm->irq);
		tdm->irq = -1;
	}

	/*
	 * Full mode still does not read/write MMIO.  On any error below the
	 * devm-managed mappings, clock/reset/pinctrl handles and group are
	 * unwound by the driver core; no DMA is allocated here.
	 */
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

	tdm->stage |= FON_STAGE_RESOURCES;
	tdm->state = FON_STATE_RESOURCES_READY;
	dev_info(&pdev->dev,
		 "full resources: adss=%s pcm=%s mbox_tx=%s mbox_rx=%s stereo_tx=%s stereo_rx=%s irq=%d\n",
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
