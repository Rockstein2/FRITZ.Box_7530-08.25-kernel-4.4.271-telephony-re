/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef FON_HW_H
#define FON_HW_H

#include <linux/clk.h>
#include <linux/cache.h>
#include <linux/device.h>
#include <linux/dma-mapping.h>
#include <linux/kernel.h>
#include <linux/io.h>
#include <linux/ioport.h>
#include <linux/pinctrl/consumer.h>
#include <linux/platform_device.h>
#include <linux/reset.h>
#include <linux/types.h>
#include <linux/mutex.h>

#include "fon_dma.h"
#include "fon_tdm.h"

/*
 * IPQ4019 ADSS/MBOX register offsets.  Addresses come exclusively from
 * device-tree resources; only offsets are constants.
 */
#define FON_ADSS_GLB_AUDIO_MODE_REG       0x30
#define FON_ADSS_GLB_TDM_CTRL_REG         0x1c
#define FON_ADSS_GLB_CLK_I2S_CTRL_REG     0x18
#define FON_ADSS_GLB_I2S_RST_REG          0x14
#define FON_ADSS_GLB_I2S_RESET_VAL_4019   0xf

#define FON_ADSS_STEREO_CONFIG_REG        0x00

#define FON_MBOX_DMA_POLICY_REG           0x10
#define FON_MBOX_DMA_RX_DESC_BASE_REG     0x18
#define FON_MBOX_DMA_RX_CONTROL_REG       0x1c
#define FON_MBOX_DMA_TX_DESC_BASE_REG     0x20
#define FON_MBOX_DMA_TX_CONTROL_REG       0x24
#define FON_MBOX_FIFO_RESET_REG           0x58
#define FON_MBOX_INT_STATUS_REG           0x44
#define FON_MBOX_INT_ENABLE_REG           0x4c

#define FON_MBOX_INT_TX_DMA_COMPLETE      BIT(6)
#define FON_MBOX_INT_RX_DMA_COMPLETE      BIT(10)
#define FON_MBOX_FIFO_RESET_TX_INIT       BIT(0)
#define FON_MBOX_FIFO_RESET_RX_INIT       BIT(2)

/* ADSS_MBOXn_MBOX_DMA_POLICY_REG fields used by AVM's source. */
#define FON_MBOX_DMA_POLICY_SW_RESET      BIT(31)
#define FON_MBOX_DMA_POLICY_TX_INT_TYPE   BIT(17)
#define FON_MBOX_DMA_POLICY_RX_INT_TYPE   BIT(16)
#define FON_MBOX_DMA_POLICY_SRAM_AC(x)    ((((x) >> 28) & 0xf) << 12)
#define FON_MBOX_DMA_POLICY_TX_FIFO_THRESHOLD(x) (((x) & 0xf) << 4)

#define FON_MBOX_DMA_RX_CONTROL_STOP      BIT(0)
#define FON_MBOX_DMA_RX_CONTROL_START     BIT(1)
#define FON_MBOX_DMA_RX_CONTROL_RESUME    BIT(2)
#define FON_MBOX_DMA_TX_CONTROL_STOP      BIT(0)
#define FON_MBOX_DMA_TX_CONTROL_START     BIT(1)
#define FON_MBOX_DMA_TX_CONTROL_RESUME    BIT(2)

/*
 * The hardware descriptor format is defined in fon_dma.h.  The hardware
 * descriptor stride is the cache-aligned sizeof(struct fon_mbox_desc), as in
 * AVM's mbox_get_desc_size().
 */
#define FON_DMA_DESC_STRIDE       ALIGN(sizeof(struct fon_mbox_desc), L1_CACHE_BYTES)

enum fon_tdm_stage {
	FON_STAGE_PLATFORM   = BIT(0),
	FON_STAGE_RESOURCES  = BIT(1),
	FON_STAGE_REGS       = BIT(2),
	FON_STAGE_TDM        = BIT(3),
	FON_STAGE_DMA_READY  = BIT(4),
	FON_STAGE_PROBE_ONLY = BIT(5),
};

#define FON_RESOURCE_COUNT 6

struct fon_dma_ring {
	struct fon_mbox_desc *desc;
	dma_addr_t desc_dma;
	u8 *buf[2];
	dma_addr_t buf_dma[2];
	size_t buf_size;
	unsigned int desc_count;
};

struct fon_tdm_dev {
	struct device *dev;
	bool probe_only;
	bool dt_overlap;
	unsigned int resource_mask;
	unsigned int clock_refs;
	unsigned int reset_refs;
	bool pinctrl_ref;
	struct resource *dt_res[FON_RESOURCE_COUNT];

	void __iomem *adss;
	void __iomem *pcm;
	void __iomem *mbox_tx;
	void __iomem *mbox_rx;
	void __iomem *stereo_tx;
	void __iomem *stereo_rx;

	struct clk *clks[4];
	struct reset_control *rst;
	struct pinctrl *pinctrl;
	int irq;
	u32 irq_spi[2];
	u32 irq_intid[2];

	struct mutex lock;
	enum fon_tdm_state state;
	bool removing;
	bool diag_valid;

	unsigned int slots;
	unsigned int adss_tx_slots;
	unsigned int adss_rx_slots;
	unsigned int stage;

	struct fon_dma_ring tx;
	struct fon_dma_ring rx;

	u32 audio_mode;
	u32 tdm_ctrl;
	u32 clk_ctrl;
	u32 i2s_rst;
	u32 stereo_tx_cfg;
	u32 stereo_rx_cfg;

	/* Control-only dry-run diagnostics; all start at zero. */
	u32 tx_frames;
	u32 rx_frames;
	u32 tx_frame_errors;
	u32 rx_frame_errors;
	enum fon_tdm_header_08 header08;
	u16 control_word;
};

#endif /* FON_HW_H */
