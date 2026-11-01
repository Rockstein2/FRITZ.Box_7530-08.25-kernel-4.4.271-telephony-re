import struct
import unittest

from avm_dect_mock import PcmMail
from dect_stack import DectStackMock


class DectStackMockTests(unittest.TestCase):
    def setUp(self):
        self.stack = DectStackMock()
        self.stack.start()

    def tearDown(self):
        if self.stack.started:
            self.stack.stop()

    def test_userspace_to_dect(self):
        self.assertEqual(self.stack.userspace_write(0x2F7D, b"abc"), 7 + 3)
        self.assertEqual(self.stack.dect.upper_tx[-1], (0x14, 0x2F7D, b"abc"))
        self.assertEqual(self.stack.dect.thread_wakeups, 1)

    def test_dect_to_userspace(self):
        self.stack.dect_to_userspace(0x2F82, b"hello")
        header = self.stack.userspace_read(4)
        length, tag = struct.unpack("<HH", header)
        self.assertEqual(tag, 0x8053)
        self.assertEqual(length, 1 + 2 + 5)
        body = self.stack.userspace_read(length)
        self.assertEqual(body[0], 0)
        self.assertEqual(body[1:3], struct.pack("<H", 0x2F82))
        self.assertEqual(body[3:], b"hello")

    def test_pcmlink_control_reaches_avm_dect(self):
        data = b"\xAA\x22\x01"
        self.assertTrue(self.stack.pcmlink.notify_dect_control(data))
        self.assertEqual(bytes(self.stack.dect.control_buffer[:len(data)]), data)
        self.assertEqual(self.stack.dect.control_streams, [data])

    def test_pcm_activity_reaches_pcmlink(self):
        encoded = PcmMail(source_task=0x23, route=0x22,
                          payload=struct.pack("<H", 0x158) + b"x").to_bytes()
        self.assertTrue(self.stack.dect.pcm_task(encoded))
        self.assertEqual(self.stack.pcmlink.activity_calls, [(0, 0x100000, 1)])

    def test_uota_slot_uses_pcmlink(self):
        received = []
        handle = self.stack.dect.open_uota_slot(2, received.append)
        self.assertTrue(self.stack.pcmlink.notify_slot_data(handle, b"pcm"))
        self.assertEqual(received, [b"pcm"])
        self.stack.dect.close_uota_slot(2)


if __name__ == "__main__":
    unittest.main()
