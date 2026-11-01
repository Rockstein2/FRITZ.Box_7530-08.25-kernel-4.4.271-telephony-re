import errno
import os
import struct
import unittest

from dect_io_mock import (
    DectIoMock, DECT_IO_HZ, DECT_IO_READ_TAG, DECT_IO_WRITE_TAG,
    DECT_IO_MAX_WRITE, POLL_DATA, POLL_EMPTY,
)


class DectIoMockTests(unittest.TestCase):
    def setUp(self):
        self.dev = DectIoMock()
        self.dev.open(os.O_RDWR)

    def test_single_open_and_append(self):
        with self.assertRaises(OSError) as cm:
            self.dev.open(os.O_RDWR)
        self.assertEqual(cm.exception.errno, errno.EBUSY)
        self.dev.close()
        with self.assertRaises(OSError) as cm:
            self.dev.open(os.O_RDWR | os.O_APPEND)
        self.assertEqual(cm.exception.errno, errno.EFAULT)

    def test_write_forwards_channel_primitive_payload(self):
        payload = b"\x01\x02\x03"
        frame = self.dev.make_write_frame(0x2F7D, payload)
        self.assertEqual(self.dev.write(frame), len(frame))
        self.assertEqual(self.dev.tx_frames[-1], bytes([0x14]) + struct.pack("<H", 0x2F7D) + payload)

    def test_write_rejects_lengths(self):
        with self.assertRaises(OSError) as cm:
            self.dev.write(b"\x00\x00\x00")
        self.assertEqual(cm.exception.errno, errno.EIO)
        with self.assertRaises(OSError) as cm:
            self.dev.write(b"\x00" * (DECT_IO_MAX_WRITE + 1))
        self.assertEqual(cm.exception.errno, errno.EIO)
        bad = struct.pack("<HH", 1, DECT_IO_WRITE_TAG) + b"\x14\x00\x00"
        with self.assertRaises(OSError) as cm:
            self.dev.write(bad)
        self.assertEqual(cm.exception.errno, errno.EIO)

    def test_read_header_and_message(self):
        message = struct.pack("<H", 0x2F82) + b"hello"
        self.dev.transport_rx(message)
        hdr = self.dev.read(4)
        length, tag = struct.unpack("<HH", hdr)
        self.assertEqual(tag, DECT_IO_READ_TAG)
        self.assertEqual(length, len(message) + 1)
        self.assertEqual(self.dev.read(length), b"\x00" + message)
        self.assertEqual(self.dev.poll(), POLL_EMPTY)

    def test_partial_read(self):
        message = b"\x34\x12" + b"abcdef"
        self.dev.transport_rx(message)
        self.assertEqual(self.dev.read(2), b"\x09\x00")
        self.assertEqual(self.dev.read(3), struct.pack("<H", DECT_IO_READ_TAG) + b"\x00")
        self.assertEqual(self.dev.read(4), message[:4])
        self.assertEqual(self.dev.read(100), message[4:])
        self.assertEqual(self.dev.ppos, 0)

    def test_nonblock_empty(self):
        with self.assertRaises(BlockingIOError) as cm:
            self.dev.read(4, block=False)
        self.assertEqual(cm.exception.errno, errno.EAGAIN)
        self.assertEqual(self.dev.poll(), POLL_EMPTY)

    def test_ioctl_time_and_debug(self):
        self.dev.jiffies = 1234
        self.assertEqual(self.dev.ioctl(1), struct.pack("<II", 1234, DECT_IO_HZ))
        self.assertEqual(self.dev.ioctl(2, b"hello"), 0)
        self.assertEqual(self.dev.debug_prints[-1], "hello")
        with self.assertRaises(OSError) as cm:
            self.dev.ioctl(3)
        self.assertEqual(cm.exception.errno, errno.EFAULT)

    def test_debug_truncation(self):
        self.dev.ioctl(2, b"A" * 256)
        self.assertTrue(self.dev.debug_prints[-1].endswith(".."))
        self.assertLessEqual(len(self.dev.debug_prints[-1]), 255)


if __name__ == "__main__":
    unittest.main()
