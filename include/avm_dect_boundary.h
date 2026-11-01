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
 * PCM mailbox framing observed in pcmdrv.c/pcm.c:
 *   u16 little-endian length
 *   mail task/primitive bytes
 *   payload
 *   checksum within the pcmdrv frame (see pcmdrv_checksum_valid)
 * The exact task/primitive offsets are documented in
 * reports/avm_dect-pcm-frames.txt; they are not claimed as a public ABI.
 */

#ifdef __cplusplus
}
#endif

#endif /* FRITZ_AVM_DECT_BOUNDARY_H */
