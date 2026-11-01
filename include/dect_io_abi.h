/*
 * Reconstructed ABI for the AVM FRITZ!Box 7530 /dev/dect_io character device.
 *
 * Source: dect_io.ko from FRITZ.OS 08.25, ARMv7, kernel 4.4.271.
 * This file documents the observed interface. It is not a claim that the
 * original driver can be loaded on an OpenWrt 6.12 kernel.
 *
 * All multi-byte fields are little-endian.
 */

#ifndef FRITZ_DECT_IO_ABI_H
#define FRITZ_DECT_IO_ABI_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ioctl commands. Names are descriptive; the original binary has no names. */
#define DECT_IO_IOCTL_GET_TIME       1U
#define DECT_IO_IOCTL_DEBUG_PRINT    2U

/* Time result returned by DECT_IO_IOCTL_GET_TIME. */
struct dect_io_time {
    uint32_t jiffies;   /* value of jiffies at the ioctl call */
    uint32_t hz;        /* observed constant 250 */
} __attribute__((packed));

#define DECT_IO_TIME_HZ_OBSERVED     250U
#define DECT_IO_DEBUG_BUFFER_SIZE    256U

/*
 * Observed userspace-to-DECT frame.
 *
 * The kernel driver checks only:
 *     header.length + 4 == write_count
 *
 * It then passes bytes starting at offset 4 to avm_dect_if_tx() with
 * length == header.length. The 0x8052 tag and 0x14 channel are therefore
 * part of the payload seen by the AVM DECT stack, not validated by dect_io.
 */
#define DECT_IO_WRITE_TAG            0x8052U
#define DECT_IO_WRITE_CHANNEL        0x14U
#define DECT_IO_WRITE_PREFIX_SIZE    7U   /* length, tag, channel, primitive */
#define DECT_IO_MIN_WRITE_SIZE       7U
#define DECT_IO_MAX_WRITE_SIZE       0x3040U

struct dect_io_write_header {
    uint16_t length;     /* 3 + payload length; total write = length + 4 */
    uint16_t tag;        /* observed 0x8052; ignored by dect_io */
    uint8_t  channel;    /* observed 0x14; passed to avm_dect_if_tx */
    uint16_t primitive;  /* AVM DECT primitive */
    uint8_t  payload[];  /* payload bytes */
} __attribute__((packed));

/*
 * Observed DECT-to-userspace frame.
 *
 * dect_io constructs this from every message received via
 * avm_dect_if_init()'s callback. The kernel-side entry contains:
 *
 *     [0..1]  length = original_message_length + 1
 *     [2..3]  0x8053
 *     [4]     status (always 0 in this implementation)
 *     [5..]   original message: u16 primitive + payload
 *
 * A userspace read first obtains 4 bytes {length, tag}, then reads exactly
 * 'length' bytes. The length includes the status byte and the original
 * message.
 */
#define DECT_IO_READ_TAG             0x8053U
#define DECT_IO_READ_PREFIX_SIZE     5U   /* length, tag, status */

struct dect_io_read_header {
    uint16_t length;     /* 1 + message length; bytes after this 4-byte header */
    uint16_t tag;        /* observed 0x8053 */
    uint8_t  status;     /* observed 0 */
    uint8_t  message[];  /* u16 primitive + payload */
} __attribute__((packed));

/* Kernel dect_io's own header: only {length, tag} is visible to userspace
 * as the first read. It does not validate the tag at offset 2. */
#define DECT_IO_KERNEL_WRITE_HDR     4U

#ifdef __cplusplus
}
#endif

#endif /* FRITZ_DECT_IO_ABI_H */
