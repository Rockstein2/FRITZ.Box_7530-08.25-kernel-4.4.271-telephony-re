/*
 * Reconstructed hardware-facing constants for AVM pcmlink.ko.
 *
 * Source: pcmlink.ko, FRITZ.OS 08.25, ARMv7, kernel 4.4.271.
 * This header documents the TDM/PCM boundary; it is not a compilable driver.
 */

#ifndef FRITZ_PCMLINK_BOUNDARY_H
#define FRITZ_PCMLINK_BOUNDARY_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* TDM/PCM slot limits observed in ipq40xxtdm_linkinit/openslots. */
#define PCMLINK_SLOT_SIZE            16U
#define PCMLINK_MAX_AUDIO_CHANNELS   7U
#define PCMLINK_DMA_DESCRIPTORS      16U
#define PCMLINK_UL_MANAGER_SIZE      0x300U
#define PCMLINK_LL_MAGIC             0x01012014U

/* GPIO resource table: six TDM pins in this order. */
#define PCMLINK_TDM_PIN_COUNT        6U
#define PCMLINK_TDM_PIN_FSC          0U
#define PCMLINK_TDM_PIN_FSC_2        1U
#define PCMLINK_TDM_PIN_DCL          2U
#define PCMLINK_TDM_PIN_DCL_2        3U
#define PCMLINK_TDM_PIN_DI           4U
#define PCMLINK_TDM_PIN_DO           5U

/* Logical names looked up in avm_get_hw_config_table(). */
#define PCMLINK_GPIO_FSC             "gpio_avm_pcmlink_fsc"
#define PCMLINK_GPIO_FSC_2           "gpio_avm_pcmlink_fsc_2"
#define PCMLINK_GPIO_DCL             "gpio_avm_pcmlink_dcl"
#define PCMLINK_GPIO_DCL_2           "gpio_avm_pcmlink_dcl_2"
#define PCMLINK_GPIO_DI              "gpio_avm_pcmlink_di"
#define PCMLINK_GPIO_DO              "gpio_avm_pcmlink_do"
#define PCMLINK_GPIO_ABSENT          0xFFFFFFFFU

/* Per-pin table layout in pcmlinktdm_gpioconfig (.data+0xd4, 6*0x2c). */
struct pcmlink_tdm_pin_config {
    uint32_t resource_start;      /* +0x00, request_resource() range */
    uint32_t resource_end;        /* +0x04 */
    uint32_t name;                /* +0x08, 32-bit pointer in the module */
    uint32_t flags;               /* +0x0c, observed 0x100 */
    uint32_t reserved10;          /* +0x10 */
    uint32_t reserved14;          /* +0x14 */
    uint32_t reserved18;          /* +0x18 */
    uint32_t pinconfig_a;         /* +0x1c */
    uint32_t pinconfig_b;         /* +0x20 */
    uint32_t pinconfig_hw;        /* +0x24 */
    uint32_t flags28;             /* +0x28 */
} __attribute__((packed));

#define PCMLINK_TDM_PIN_CONFIG_SIZE  0x2CU

/* DMA stall/reinit poll uses jiffies with a 0x7d comparison. */
#define PCMLINK_DMA_STALL_JIFFIES    0x7DU

/*
 * Observed vendor TDM call boundary (argument roles are inferred from
 * ipq40xxtdm_linkinit/activate; the real prototypes are not exported):
 *
 *   tdm_if_config_init(slot_size, tx_slots, rx_slots, config)
 *   tdm_if_dma_init(handle, tx_cb, rx_cb, 1, descriptor_count,
 *                   slot_size, slot_ratio, 16)
 *   tdm_if_dma_start(handle)
 *   tdm_if_dma_stop(handle)
 *   tdm_if_dma_irqcnt(handle, &rx, &tx)
 *   tdm_if_dma_irqcnt_reset(handle)
 *   tdm_if_dma_exit(handle)
 *   tdm_if_config_exit()
 *   tdm_if_print_status()
 */
#define PCMLINK_TDM_TX_CALLBACK      "ipq40xxtdm_TxData"
#define PCMLINK_TDM_RX_CALLBACK      "ipq40xxtdm_RxData"

/* DECT audio/control API names exported by pcmlink.ko. */
#define PCMLINK_UL_REGISTER_ROUTER   "pcmlink_ul_register_pcmrouter"
#define PCMLINK_UL_UNREGISTER_ROUTER "pcmlink_ul_release_pcmrouter"
#define PCMLINK_UL_OPEN_SLOTS        "pcmlink_ul_openslots"
#define PCMLINK_UL_CLOSE_SLOTS       "pcmlink_ul_closeslots"
#define PCMLINK_UL_RXGET             "pcmlink_ul_rxget_slotdata_pcmrouter"
#define PCMLINK_UL_TXPUT             "pcmlink_ul_txput_slotdata_pcmrouter"
#define PCMLINK_UL_TXALLOC           "pcmlink_ul_txalloc_slotdata_pcmrouter"
#define PCMLINK_UL_RXFREE            "pcmlink_ul_rxfree_slotdata_pcmrouter"
#define PCMLINK_UL_SETSLOTPARAM      "pcmlink_ul_setslotparam_pcmrouter"
#define PCMLINK_UL_REGISTER_DECTCTRL "pcmlink_ul_register_dectcontrol"
#define PCMLINK_UL_CONFIG_DECTCTRL   "pcmlink_ul_config_dectcontrol"
#define PCMLINK_UL_RELEASE_DECTCTRL  "pcmlink_ul_release_dectcontrol"

#ifdef __cplusplus
}
#endif

#endif /* FRITZ_PCMLINK_BOUNDARY_H */
