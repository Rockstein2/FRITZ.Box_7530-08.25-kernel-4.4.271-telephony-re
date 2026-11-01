/*
 * Reconstructed AVM DECT / pcmlink boundary constants.
 *
 * Source: avm_dect.ko + pcmlink.ko from FRITZ.OS 08.25, ARMv7, kernel 4.4.271.
 * This documents observed interfaces and sizes; it is not a compilable driver.
 */

#ifndef FRITZ_AVM_DECT_BOUNDARY_H
#define FRITZ_AVM_DECT_BOUNDARY_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* gDectMemPool: simplemempool created by avm_dect_init(). */
#define AVM_DECT_MEMPOOL_SIZE          0x40000U

/* avm_dect_init() allocates this control-channel buffer. */
#define AVM_DECT_CONTROL_BUFFER_SIZE   0x1000U

/* FpUI per-handset UOTA state allocation. */
#define AVM_DECT_UOTA_BUFFER_SIZE      0x1450U

/* pcmlink DECT-control slot configuration observed in avm_dect_init(). */
#define AVM_DECT_DECTCTRL_SLOT_START   0x1000U
#define AVM_DECT_DECTCTRL_SLOT_COUNT   0x1000U

/* pcmlink activity call from pcm_Task/FpUI. */
#define AVM_DECT_ACTIVITY_MASK         0x100000U

/* AVM DECT PCM mail/channel limits. */
#define AVM_DECT_PCM_MAIL_MIN          8U
#define AVM_DECT_PCM_MAIL_MAX          0xFCU
#define AVM_DECT_FRAME_SYNC            0xAAU
#define AVM_DECT_MAX_AUDIO_SLOTS       7U
#define AVM_DECT_PCM_SLOT_ENTRY_SIZE   0x4FU
#define AVM_DECT_PCM_TABLE_OFFSET      0x3971U
#define AVM_DECT_CHECKSUM_PREFIX       4U

/* Special primitive handled by avm_dect_if_tx(). */
#define AVM_DECT_PRIMITIVE_SPECIAL     0x2FBAU

/*
 * avm_dect_if_tx() byte layout as delivered by dect_io:
 *   [u8 channel][u16le primitive][payload...]
 * The channel byte is stripped before SendMailFromUpper().
 */
#define AVM_DECT_TX_CHANNEL            0x14U
#define AVM_DECT_TX_PREFIX_SIZE        3U

/* Outbound UICP mail callback registered by dect_io. */
#define AVM_DECT_IF_HANDLER_OFFSET     0xED4U
#define AVM_DECT_AUDIO_HANDLER_OFFSET  0xED8U

/* pcmlink PCM-route shared state. */
#define AVM_DECT_PCMROUTE_SIZE         0xF8E8U
#define AVM_DECT_PCMROUTE_ZERO_SIZE    0xEAACU
#define AVM_DECT_PCMROUTE_MAGIC        0xC0AFD54CU
#define AVM_DECT_PCMROUTE_EC_OFFSET    0xDD98U

/*
 * PCM mailbox framing observed in pcmdrv.c/pcm.c and AllocateMailPacket2():
 *
 *   +0x00  u16le payload length
 *   +0x02  u8    source task
 *   +0x03  u8    route/task selector (exact name not proven)
 *   +0x04  payload; first u16le is the message primitive
 *
 * total = payload length + 4; pcmdrv_enqueue_tx rejects total > 0xfc.
 * The checksum is over frame[0 .. length+3], stored at frame[length+4].
 */
#define AVM_DECT_PCM_HEADER_SIZE       4U

struct avm_dect_pcm_header {
    uint16_t length;        /* payload length, not total frame length */
    uint8_t  source_task;
    uint8_t  route;
} __attribute__((packed));

#define AVM_DECT_PCM_PRIM_PCM_STATUS   0xF625U
#define AVM_DECT_PCM_PRIM_PCM_TX       0xF626U
#define AVM_DECT_PCM_PRIM_REMOTE_STAT  0xFFF1U
#define AVM_DECT_PCM_PRIM_ACTIVITY     0x0158U
#define AVM_DECT_PCM_PRIM_TEST_CFM     0x0242U
#define AVM_DECT_PCM_PRIM_SPECIAL      0x2FBAU

#ifdef __cplusplus
}
#endif

#endif /* FRITZ_AVM_DECT_BOUNDARY_H */
