/*
 * Reconstructed pcmlink shared-memory layout.
 *
 * Source: modules/ubik2/pcmlink.ko, FRITZ.OS 08.25, ARM EABI5, kernel 4.4.271.
 *
 * This header records offsets recovered from the module disassembly. It is a
 * layout description, not a compilable driver header. All offsets are relative
 * to the object named in the corresponding PCMLINK_*_OFFSET macro.
 *
 * The two objects are distinct:
 *
 *   gPcmroute        .bss+0xd780, 0xf8e8 bytes  (host-side router state)
 *   gPcmrouteKernel  .bss+0x280c0, 0x8f4 bytes  (upper-layer manager)
 *
 * pcmroute_getsharedmem() returns gPcmroute. It does NOT return the DSP
 * shared-memory descriptor; that descriptor comes from
 * pcmlink_ll_sharedmemory() and is stored in gPcmrouteKernel+0x234.
 */

#ifndef FRITZ_PCMLINK_SHAREDMEM_H
#define FRITZ_PCMLINK_SHAREDMEM_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ---- object identities ------------------------------------------------ */
#define PCMLINK_PCMROUTE_BSS_OFFSET      0x0000D780U
#define PCMLINK_PCMROUTE_SIZE            0x0000F8E8U
#define PCMLINK_PCMROUTE_ZERO_SIZE       0x0000EAACU
#define PCMLINK_PCMROUTE_MAGIC           0xC0AFD54CU

#define PCMLINK_PCMROUTE_KERNEL_BSS      0x000280C0U
#define PCMLINK_PCMROUTE_KERNEL_SIZE     0x000008F4U
#define PCMLINK_PCMROUTE_KERNEL_MAGIC    0x53428431U

#define PCMLINK_SHAREDMEMORY_BSS         0x0000CB0CU
#define PCMLINK_SHAREDMEMORY_SIZE        0x000002DCU
#define PCMLINK_SHAREDMEMORY_FPGA_BSS    0x0000CDE8U

/* ---- gPcmroute: header and command ring ------------------------------- */
#define PCMLINK_PCMROUTE_MAGIC_OFF       0x0000U  /* u32 = 0xC0AFD54C        */
#define PCMLINK_PCMROUTE_DERIVED_OFF     0x0004U  /* u32, derived from magic */
#define PCMLINK_PCMROUTE_CMD_HEAD_OFF    0x0008U  /* u16 ring head           */
#define PCMLINK_PCMROUTE_CMD_TAIL_OFF    0x000AU  /* u16 ring tail           */
#define PCMLINK_PCMROUTE_CMD_QUEUE_OFF   0x000CU  /* first 0x28-byte entry   */
#define PCMLINK_PCMROUTE_CMD_COUNT       0x0104U  /* 260 entries             */
#define PCMLINK_PCMROUTE_CMD_ENTRY_SIZE  0x0028U
#define PCMLINK_PCMROUTE_CMD_END_OFF     0x288CU  /* 0x0c + 0x104*0x28      */

/* One command-queue entry (observed at pcmroute_enqueue_torouter). */
struct pcmlink_pcmroute_cmd {
    uint32_t fn;                 /* +0x00 callback/context word             */
    uint8_t  slot;               /* +0x04 slot/channel byte                 */
    uint8_t  reserved05[3];      /* +0x05                                   */
    uint8_t  payload[0x20];      /* +0x08 caller payload                    */
} __attribute__((packed));

/* ---- gPcmroute: control block at +0x2000 ------------------------------ */
/* These fields are absolute gPcmroute offsets, not +0x2000-relative. */
#define PCMLINK_PCMROUTE_CTRL_OFF        0x2000U
#define PCMLINK_PCMROUTE_CTRL_28D0       0x28D0U  /* u32, read by sink path  */
#define PCMLINK_PCMROUTE_CTRL_28E0       0x28E0U  /* u8 min channel          */
#define PCMLINK_PCMROUTE_CTRL_28E1       0x28E1U  /* u8 max channel          */

/* ---- gPcmroute: slot-table descriptor and tables ---------------------- */
#define PCMLINK_PCMROUTE_SLOT_DESC_OFF   0x29ACU  /* 0x18-byte descriptor    */
#define PCMLINK_PCMROUTE_SLOT_COUNT_OFF  0x29B0U  /* u16, descriptor+0x04    */
#define PCMLINK_PCMROUTE_SLOT_TABLE_OFF  0x29B4U  /* u32, descriptor+0x08    */
#define PCMLINK_PCMROUTE_CONN_LIMIT_OFF  0x29B8U  /* u16, descriptor+0x0c    */
#define PCMLINK_PCMROUTE_CONN_STORE_OFF  0x29BCU  /* u32, descriptor+0x10    */
#define PCMLINK_PCMROUTE_CONN_FLAGS_OFF  0x29C0U  /* u32, descriptor+0x14    */
#define PCMLINK_PCMROUTE_CONN_ARRAY_OFF  0x29C4U  /* first 0x10-byte entry   */
#define PCMLINK_PCMROUTE_SLOT_TABLE_BASE 0x3284U  /* pointer target          */
#define PCMLINK_PCMROUTE_SLOT_ENTRY_SIZE 0x0198U
#define PCMLINK_PCMROUTE_CONN_LIMIT      0x008CU  /* 140 connections         */
#define PCMLINK_PCMROUTE_CONN_ENTRY_SIZE 0x0010U

/* A slot-table descriptor (partial; matches pcmroute_slotconnectionlist_init). */
struct pcmlink_slot_table_desc {
    uint32_t state;              /* +0x00, used as connection-list head    */
    uint16_t slot_count;         /* +0x04                                   */
    uint16_t reserved06;         /* +0x06                                   */
    uint32_t slot_table;         /* +0x08 -> +0x3284 in the normal layout   */
    uint16_t conn_limit;         /* +0x0c, observed 0x8c = 140              */
    uint16_t reserved0e;         /* +0x0e                                   */
    uint32_t conn_storage;       /* +0x10 -> +0x29c4                        */
    uint32_t flags;              /* +0x14                                   */
} __attribute__((packed));

/*
 * One 0x10-byte connection-list entry in the array at CONN_STORE_OFF.
 * The list is linked through +0x08; the descriptor state is the head.
 */
struct pcmlink_conn_entry {
    uint8_t  endpoint0;          /* +0x00 source endpoint                   */
    uint8_t  endpoint1;          /* +0x01 source endpoint                   */
    uint8_t  sink;               /* +0x02 sink key checked by findslot       */
    uint8_t  endpoint3;          /* +0x03 multi-source alternate            */
    uint8_t  endpoint4;          /* +0x04 checked by findslot_as_source     */
    uint8_t  reserved05[3];      /* +0x05                                   */
    uint32_t next;               /* +0x08, next connection or 0             */
    uint8_t  used;               /* +0x0c                                   */
    uint8_t  reserved0d[3];      /* +0x0d                                   */
} __attribute__((packed));

/*
 * One 0x198-byte slot descriptor in the table at SLOT_TABLE_BASE.
 * Only fields with direct disassembly evidence are named.
 */
#define PCMLINK_SLOT_FLAGS_OFF          0x0004U  /* u32                      */
#define PCMLINK_SLOT_F08_OFF            0x0008U  /* u32                      */
#define PCMLINK_SLOT_F0C_OFF            0x000CU  /* u32                      */
#define PCMLINK_SLOT_F10_OFF            0x0010U  /* u32, checked non-zero    */
#define PCMLINK_SLOT_CB14_OFF           0x0014U  /* u32 callback             */
#define PCMLINK_SLOT_CB18_OFF           0x0018U  /* u32 callback             */
#define PCMLINK_SLOT_F26_OFF            0x0026U  /* u8                       */
#define PCMLINK_SLOT_ECIDX_OFF          0x0028U  /* u8                       */
#define PCMLINK_SLOT_ECSLOT_OFF         0x0029U  /* u8, 1-based index        */
#define PCMLINK_SLOT_F2D_OFF            0x002DU  /* u8                       */
#define PCMLINK_SLOT_F2E_OFF            0x002EU  /* u8                       */
#define PCMLINK_SLOT_DTMF_OFF           0x0190U  /* u8 DTMF generator active */
#define PCMLINK_SLOT_F191_OFF           0x0191U  /* u8 flags                 */
#define PCMLINK_SLOT_F11C_OFF           0x011CU  /* u32 G.722 state pointer  */
#define PCMLINK_SLOT_F18C_OFF           0x018CU  /* u32 codec state pointer  */
#define PCMLINK_SLOT_SUB30_OFF          0x0030U  /* 0x8c-byte substructure   */
#define PCMLINK_SLOT_SUB30_SIZE         0x008CU

/* ---- gPcmroute: connection-struct pool -------------------------------- */
#define PCMLINK_PCMROUTE_CSTRUCT_OFF     0x28ACU  /* 4 * 0x40 bytes           */
#define PCMLINK_PCMROUTE_CSTRUCT_SIZE    0x0040U
#define PCMLINK_PCMROUTE_CSTRUCT_USED    0x003FU  /* used flag inside entry   */
#define PCMLINK_PCMROUTE_CSTRUCT_COUNT   4U

/* ---- gPcmroute: echo-canceller state ---------------------------------- */
#define PCMLINK_PCMROUTE_EC_OFF          0xDD98U
#define PCMLINK_PCMROUTE_EC_COUNT        5U
#define PCMLINK_PCMROUTE_EC_ENTRY_SIZE   0x0094U

struct pcmlink_ec_state {
    uint8_t  active;              /* +0x00                                  */
    uint8_t  slot;                /* +0x01, cleared to 0xff by ecinit       */
    uint8_t  ec_channel;          /* +0x02                                  */
    uint8_t  flags;               /* +0x03                                  */
    uint32_t type;                /* +0x04, 0xff when free                  */
    uint32_t sequence;            /* +0x08                                  */
    uint32_t config;              /* +0x0c, -1 when free                    */
    uint32_t field10;             /* +0x10, not written by ecinit           */
    uint8_t  reserved[0x80];      /* +0x14..+0x93                           */
} __attribute__((packed));

/* ---- gPcmroute: codec table ------------------------------------------- */
#define PCMLINK_PCMROUTE_CODEC_OFF       0xE76CU
#define PCMLINK_PCMROUTE_CODEC_COUNT     3U
#define PCMLINK_PCMROUTE_CODEC_ENTRY_SIZE 0x0024U

struct pcmlink_codec_entry {
    uint32_t id;                  /* +0x00, observed codec ids 1..3         */
    uint32_t callback[8];         /* +0x04..+0x23                           */
} __attribute__((packed));

/* ---- gPcmroute: per-slot echo-canceller/channel state ----------------- */
#define PCMLINK_PCMROUTE_ECSLOT_OFF      0xE828U
#define PCMLINK_PCMROUTE_ECSLOT_SIZE     0x0044U
#define PCMLINK_PCMROUTE_ECSLOT_F00      0x0000U  /* u32, compared with 0x10 */

#define PCMLINK_PCMROUTE_CONTEXT_OFF     0xEAA8U  /* u16 PCMRoute context    */

/* ---- gPcmroute: channel state array ----------------------------------- */
#define PCMLINK_PCMROUTE_CHANNEL_OFF     0xEBACU
#define PCMLINK_PCMROUTE_CHANNEL_SIZE    0x0018U
#define PCMLINK_PCMROUTE_CHANNEL_F00     0x0000U  /* u32                     */
#define PCMLINK_PCMROUTE_CHANNEL_F04     0x0004U  /* u32                     */
#define PCMLINK_PCMROUTE_CHANNEL_F08     0x0008U  /* u32                     */
#define PCMLINK_PCMROUTE_CHANNEL_F0C     0x000CU  /* u16                     */
#define PCMLINK_PCMROUTE_CHANNEL_F10     0x0010U  /* u32                     */
#define PCMLINK_PCMROUTE_CHANNEL_F14     0x0014U  /* u8                      */

/* ---- gPcmroute: status block at +0xF000 ------------------------------- */
#define PCMLINK_PCMROUTE_STATUS_OFF      0xF000U
#define PCMLINK_PCMROUTE_STATUS_SIZE     0x08E8U
#define PCMLINK_PCMROUTE_STATUS_F8CC     0x08CCU  /* u32                     */
#define PCMLINK_PCMROUTE_STATUS_F8D0     0x08D0U  /* u32                     */
#define PCMLINK_PCMROUTE_STATUS_F8D8     0x08D8U  /* u32                     */
#define PCMLINK_PCMROUTE_STATUS_F8DC     0x08DCU  /* u32                     */
#define PCMLINK_PCMROUTE_STATUS_MINCH    0x08E0U  /* u8                      */
#define PCMLINK_PCMROUTE_STATUS_MAXCH    0x08E1U  /* u8                      */

/* ---- gPcmrouteKernel: upper-layer manager ----------------------------- */
#define PCMLINK_UL_MANAGER_CLEAR_SIZE    0x0300U  /* cleared by register    */
#define PCMLINK_UL_MAGIC_OFF             0x0000U  /* u32 = 0x53428431        */
#define PCMLINK_UL_LL_HANDLE_OFF         0x0004U  /* u32                     */
#define PCMLINK_UL_REGNOEMIF_OFF         0x0008U  /* u32                     */
#define PCMLINK_UL_WAITQ_OFF             0x0218U  /* wait_queue_head_t       */
#define PCMLINK_UL_DSP_24_OFF            0x0224U  /* host address of +0x24   */
#define PCMLINK_UL_DSP_38_OFF            0x0228U  /* host address of +0x38   */
#define PCMLINK_UL_DSP_3C_OFF            0x022CU  /* host address of +0x3C   */
#define PCMLINK_UL_DSP_28_OFF            0x0230U  /* host address of +0x28   */
#define PCMLINK_UL_SHARED_OFF            0x0234U  /* descriptor pointer      */
#define PCMLINK_UL_PCMROUTER_ARG_OFF     0x0238U  /* callback argument       */
#define PCMLINK_UL_DEBUG_OFF             0x02B4U  /* debug handle            */
#define PCMLINK_UL_PM_OFF                0x02B8U  /* power-management handle */

/* ---- link/DSP shared-memory descriptor -------------------------------- */
#define PCMLINK_SHARED_24_OFF            0x0024U  /* 0x20-entry slot table    */
#define PCMLINK_SHARED_28_OFF            0x0028U  /* control/receive buffer   */
#define PCMLINK_SHARED_2C_OFF            0x002CU  /* current received length  */
#define PCMLINK_SHARED_30_OFF            0x0030U  /* link state (3 = active)  */
#define PCMLINK_SHARED_34_OFF            0x0034U  /* status/command word      */
#define PCMLINK_SHARED_38_OFF            0x0038U  /* buffer base A (TX alloc) */
#define PCMLINK_SHARED_3C_OFF            0x003CU  /* buffer base B (RX get)   */
#define PCMLINK_SHARED_44_OFF            0x0044U  /* observed bitmask         */
#define PCMLINK_SHARED_48_OFF            0x0048U  /* observed bitmask         */
#define PCMLINK_SHARED_4C_OFF            0x004CU  /* observed value           */
#define PCMLINK_SHARED_50_OFF            0x0050U  /* observed value           */
#define PCMLINK_SHARED_58_OFF            0x0058U  /* observed bitmask         */
#define PCMLINK_SHARED_60_OFF            0x0060U  /* TX slot bitmask          */
#define PCMLINK_SHARED_64_OFF            0x0064U  /* RX release/status        */
#define PCMLINK_SHARED_68_OFF            0x0068U  /* regnoemif descriptor     */

#define PCMLINK_DSP_ENTRY_SIZE           0x0014U
#define PCMLINK_DSP_ENTRY_COUNT          0x0020U

/*
 * One entry of the descriptor+0x24 table. Entries are indexed by the audio
 * slot number (0..0x1f). +0x08 is an offset into the buffer selected by the
 * caller: +0x38 for TX allocation and +0x3c for RX retrieval.
 */
struct pcmlink_dsp_entry {
    uint32_t slot;               /* +0x00, observed <= 0x1f                 */
    uint32_t length;             /* +0x04, used as u16; sometimes doubled   */
    uint32_t offset;             /* +0x08                                   */
    uint32_t field0c;            /* +0x0c                                   */
    uint32_t field10;            /* +0x10                                   */
} __attribute__((packed));

#ifdef __cplusplus
}
#endif

#endif /* FRITZ_PCMLINK_SHAREDMEM_H */
