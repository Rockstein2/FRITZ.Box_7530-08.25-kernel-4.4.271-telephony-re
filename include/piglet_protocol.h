/*
 * Reconstructed FRITZ!Box 7530 Piglet_noemif / DECT loader constants.
 *
 * Source: Piglet_noemif.ko, FRITZ.OS 08.25, ARMv7, kernel 4.4.271.
 *
 * The DECT wire protocol below is recovered from dect14488_loader.c code
 * paths and strings. Names are descriptive because the original binary has
 * no exported protocol header.
 *
 * Values written to the DECT UART are bytes. Multi-byte firmware/image fields
 * are big-endian, as produced by ihex2bin().
 */

#ifndef FRITZ_PIGLET_PROTOCOL_H
#define FRITZ_PIGLET_PROTOCOL_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* DECT UART control bytes observed in dect_loader(). */
#define PIGLET_UART_SOH             0x01U
#define PIGLET_UART_STX             0x02U
#define PIGLET_UART_ACK             0x06U
#define PIGLET_UART_NACK            0x15U
#define PIGLET_UART_NO_CHAR         0xFFFFFFFFU /* internal -EAGAIN marker */

#define PIGLET_HELLO_STRING         "HELLO DCX81"
#define PIGLET_HELLO_STRING_LEN     11U
#define PIGLET_HELLO_REPLY_0        0x11U
#define PIGLET_HELLO_REPLY_1        0xBAU
#define PIGLET_HELLO_REPLY_2        0x5EU
#define PIGLET_HELLO_REPLY_3        0xBAU

/* Poll/retry bounds observed in the state machine. */
#define PIGLET_CHAR_POLL_LIMIT      0x7EU  /* 126 character polls */
#define PIGLET_RETRY_LIMIT          0x0BU  /* 11 retries */
#define PIGLET_FIRST_RETRY_LIMIT    0x10U  /* first-level reset loop */
#define PIGLET_SECOND_RETRY_LIMIT   0x05U  /* second-level reset loop */
#define PIGLET_CRC_SETTLE_MS        10U

/* Baud rates passed to msm_dectuart_init(). */
#define PIGLET_BAUD_9600            0x2580U
#define PIGLET_BAUD_19200           0x4B00U
#define PIGLET_BAUD_115200          0x1C200U
#define PIGLET_BAUD_230400          0x38400U
#define PIGLET_BAUD_460800          0x70800U

/* Intel HEX record types accepted by ihex2bin(). */
enum piglet_hex_record_type {
    PIGLET_HEX_DATA              = 0x00,
    PIGLET_HEX_EOF               = 0x01,
    PIGLET_HEX_EXT_SEGMENT       = 0x02,
    PIGLET_HEX_EXT_LINEAR        = 0x04
};

/*
 * ihex2bin() output is a sequence of contiguous blocks. Each block starts
 * with an 8-byte big-endian {address, length} header.
 */
struct piglet_hex_block_header {
    uint32_t address_be;
    uint32_t length_be;
} __attribute__((packed));

#define PIGLET_BLOCK_HEADER_SIZE    8U
#define PIGLET_HEX_BUFFER_SIZE      0x30005U
#define PIGLET_HEX_MAX_CONTENT      0x2FFFFU

/*
 * Outer firmware framing produced by ihex2bin().
 *
 * First-level image (ihex2bin mode 0):
 *   u16be payload_length
 *   blocks...
 *   u8   xor checksum
 *   total = payload_length + 3
 *
 * Second-level image (ihex2bin mode 1):
 *   u32be payload_length
 *   blocks...
 *   u8   xor checksum
 *   total = payload_length + 5
 *
 * The DECT loader sends the length header first, then payload bytes. The last
 * byte is a checksum that the loader compares with the checksum returned by
 * the DECT side in the slow path.
 */
#define PIGLET_FW_FIRST_HEADER_SIZE 2U
#define PIGLET_FW_SECOND_HEADER_SIZE 4U
#define PIGLET_FW_CHECKSUM_SIZE     1U

/*
 * Logical GPIO names looked up by get_profile() in the AVM hardware-config
 * table. The table entries are 0x20 bytes and contain {name, value}.
 */
#define PIGLET_GPIO_DATA            "gpio_avm_piglet_noemif_data"
#define PIGLET_GPIO_DONE            "gpio_avm_piglet_noemif_done"
#define PIGLET_GPIO_CLK             "gpio_avm_piglet_noemif_clk"
#define PIGLET_GPIO_PROG            "gpio_avm_piglet_noemif_prog"
#define PIGLET_GPIO_FPGAOK           "gpio_avm_piglet_noemif_fpgaok"
#define PIGLET_GPIO_CLOCKOUT         "gpio_avm_piglet_clockout"
#define PIGLET_GPIO_DECT_RESET       "gpio_avm_dect_reset"
#define PIGLET_GPIO_DECT_RD          "gpio_avm_dect_rd"
#define PIGLET_GPIO_DECT_TX          "gpio_avm_dect_tx"
#define PIGLET_GPIO_TDM_FSC          "gpio_avm_pcmlink_fsc"
#define PIGLET_GPIO_TDM_DCL          "gpio_avm_pcmlink_dcl"

/* Sentinel used by the AVM profile/hw-config tables. */
#define PIGLET_GPIO_ABSENT           0xFFFFFFFFU

/*
 * Profile-list field offsets recovered from get_profile().
 * The default profile in this module is named "235".
 */
enum piglet_profile_offset {
    PIGLET_PROFILE_NAME          = 0x00,
    PIGLET_PROFILE_GPIO_DATA     = 0x04,
    PIGLET_PROFILE_GPIO_DONE     = 0x08,
    PIGLET_PROFILE_GPIO_CLK      = 0x0C,
    PIGLET_PROFILE_GPIO_PROG     = 0x10,
    PIGLET_PROFILE_GPIO_FPGAOK   = 0x14,
    PIGLET_PROFILE_GPIO_CLOCKOUT = 0x18,
    PIGLET_PROFILE_DECT_MODE     = 0x24,
    PIGLET_PROFILE_GPIO_DECT_RESET = 0x28,
    PIGLET_PROFILE_GPIO_DECT_RD  = 0x2C,
    PIGLET_PROFILE_GPIO_DECT_TX  = 0x30
};

#define PIGLET_DEFAULT_PROFILE_NAME  "235"
#define PIGLET_DEFAULT_DECT_MODE     0x105U
#define PIGLET_DEFAULT_GPIO_RESET    18U
#define PIGLET_DEFAULT_GPIO_RD       16U

/*
 * TLV tags patched by patch_dectfw() in the converted firmware payload.
 * Tag 1 carries a 5-byte RFPI with the existing "0270" marker; tag 7 carries
 * one dectmode byte; tag 9 carries a 22-byte stub-version record.
 */
#define PIGLET_TAG_RFPI              1U
#define PIGLET_TAG_DECT_MODE         7U
#define PIGLET_TAG_STUB_VERSION      9U
#define PIGLET_RFPI_LEN              5U
#define PIGLET_STUB_VERSION_LEN      22U
#define PIGLET_DECT_CONFIG_MAX       0x40U

/* Default 7-byte RFPI patch template from .rodata+0x4e. */
#define PIGLET_RFPI_PATCH_TEMPLATE   { 0x01, 0x05, '0', '2', '7', '0', 0x50 }

/* Optional Piglet FPGA bitfile path (not used when all Piglet GPIOs are -1). */
#define PIGLET_BITFILE_DEFAULT       "/var/bitfile.bit"
#define PIGLET_BITFILE_POTS_DEFAULT  "/var/bitfile_pots.bit"
#define PIGLET_XBIT_CHUNK            0x80U

#ifdef __cplusplus
}
#endif

#endif /* FRITZ_PIGLET_PROTOCOL_H */
