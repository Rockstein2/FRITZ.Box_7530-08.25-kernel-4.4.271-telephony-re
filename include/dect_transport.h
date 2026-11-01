/*
 * Clean transport boundary for a Linux 6.12 reimplementation of the
 * FRITZ!Box 7530 DECT stack.
 *
 * This is not a copy of the AVM ABI. It describes the smallest interface that
 * the observed dect_io -> avm_dect -> pcmlink chain needs:
 *
 *   userspace  --/dev/dect_io-->  dect_io shim
 *                                   |
 *                                   |  tx(channel, primitive, payload)
 *                                   v
 *                              avm_dect transport
 *                                   |
 *                                   |  control bytes / PCM mail
 *                                   v
 *                              pcmlink TDM backend
 *
 * The reverse direction carries [u16 primitive][payload] only. The original
 * avm_dect -> dect_io callback has exactly that shape; the channel byte is a
 * userspace-to-DECT transport selector and is not part of the callback.
 *
 * Source facts:
 *   notes/dect_io.md
 *   notes/avm_dect.md
 *   notes/avm_dect_boundary.md
 *   notes/pcmlink.md
 */

#ifndef FRITZ_DECT_TRANSPORT_H
#define FRITZ_DECT_TRANSPORT_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* The only channel value observed in dect_manager frames. */
#define DECT_TRANSPORT_CHANNEL_AVM      0x14U

/* Special primitive that avm_dect_if_tx() handles before SendMailFromUpper(). */
#define DECT_TRANSPORT_PRIMITIVE_SPECIAL 0x2FBAU

/*
 * Userspace -> DECT direction.
 *
 * The original byte layout received by avm_dect_if_tx() is:
 *
 *   [u8 channel][u16le primitive][payload...]
 *
 * A clean implementation should pass the three fields separately rather than
 * relying on a packed structure.
 */
struct dect_transport_ops {
    /*
     * Return 0 on success, a negative errno on failure. The original
     * dect_io write path logs but does not propagate this error.
     */
    int (*tx)(void *ctx, uint8_t channel, uint16_t primitive,
              const void *payload, size_t payload_len);
};

/*
 * DECT -> userspace direction.
 *
 * The original callback receives [u16le primitive][payload...]. It is called
 * from the avm_dect receive path, not from a userspace context.
 */
struct dect_host_ops {
    void (*rx)(void *ctx, uint16_t primitive,
               const void *payload, size_t payload_len);
};

#ifdef __cplusplus
}
#endif

#endif /* FRITZ_DECT_TRANSPORT_H */
