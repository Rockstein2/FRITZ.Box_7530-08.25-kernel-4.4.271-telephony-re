import errno
import struct
import unittest

from avm_dect_mock import (
    AVM_DECT_CONTROL_BUFFER_SIZE,
    AVM_DECT_PCM_MAIL_MAX,
    AVM_DECT_PRIMITIVE_SPECIAL,
    AvmDectMock,
    PcmMail,
)
from pcmlink_mock import PcmlinkMock


def pcm_frame(primitive, payload=b"", source_task=0x23, route=0x22):
    return PcmMail(source_task=source_task, route=route,
                   payload=struct.pack("<H", primitive) + payload).to_bytes()


def frame_with_checksum(primitive, payload=b""):
    body = struct.pack("<H", primitive) + payload
    mail = PcmMail(source_task=0x23, route=0x22, payload=body)
    frame = mail.to_bytes()
    checksum = sum(frame) & 0xFFFF
    return frame + struct.pack("<H", checksum)


class AvmDectMockTests(unittest.TestCase):
    def setUp(self):
        self.pcm = PcmlinkMock()
        self.dect = AvmDectMock(self.pcm)
        self.host = []
        self.dect.if_init(self.host.append)

    def test_tx_requires_handler(self):
        self.dect.if_deinit()
        with self.assertRaises(OSError) as cm:
            self.dect.if_tx(b"\x14\x7d\x2f")
        self.assertEqual(cm.exception.errno, errno.EIO)

    def test_tx_strips_channel_and_forwards(self):
        frame = bytes([0x14]) + struct.pack("<H", 0x2F7D) + b"abc"
        self.assertEqual(self.dect.if_tx(frame), 0)
        self.assertEqual(self.dect.upper_tx, [(0x14, 0x2F7D, b"abc")])
        self.assertEqual(self.dect.thread_wakeups, 1)

    def test_tx_special_primitive_uses_mempool(self):
        frame = bytes([0x14]) + struct.pack("<H", AVM_DECT_PRIMITIVE_SPECIAL) + b"xyz"
        self.dect.if_tx(frame)
        self.assertEqual(self.dect.special_allocations, [b"xyz"])
        self.assertEqual(self.dect.mempool_used, 3 + 5)  # special + mail packet
        self.assertEqual(self.dect.upper_tx[-1],
                         (0x14, AVM_DECT_PRIMITIVE_SPECIAL, b"xyz"))

    def test_host_to_dect_callback_and_free(self):
        self.dect.uicp_send_mail_to_host(b"\x82\x2fhello")
        self.assertEqual(self.host, [b"\x82\x2fhello"])
        self.assertEqual(self.dect.freed_messages, [b"\x82\x2fhello"])

    def test_rxtx_callback_control_buffer(self):
        self.assertFalse(self.dect.rxtx_callback(b"\xAA"))
        self.dect.control_active = True
        data = b"\xAA\x01\x02"
        self.assertTrue(self.dect.rxtx_callback(data))
        self.assertEqual(bytes(self.dect.control_buffer[:len(data)]), data)
        self.assertEqual(self.dect.control_streams, [data])

        big = b"\xAA" + b"x" * (AVM_DECT_CONTROL_BUFFER_SIZE + 10)
        self.assertTrue(self.dect.rxtx_callback(big))
        self.assertTrue(self.dect.control_truncated)
        self.assertEqual(len(self.dect.control_buffer), AVM_DECT_CONTROL_BUFFER_SIZE)

    def test_init_registers_and_cleanup_releases_dect_control(self):
        self.dect.init()
        self.assertTrue(self.dect.initialized)
        self.assertIsNotNone(self.dect.dect_handle)
        self.assertEqual(self.dect.dect_slot_count, 0x1000)
        self.assertTrue(self.pcm.dect_control.configured)
        handle = self.dect.dect_handle
        self.dect.cleanup()
        self.assertFalse(self.dect.initialized)
        self.assertIsNone(self.pcm.dect_control)
        self.assertIsNotNone(handle)

    def test_pcm_task_activity_and_queue(self):
        ok = self.dect.pcm_task(pcm_frame(0x158, b"payload"))
        self.assertTrue(ok)
        self.assertEqual(self.pcm.activity_calls, [(0, 0x100000, 1)])
        self.assertEqual(len(self.dect.pcm.tx_queue), 1)
        self.assertEqual(self.dect.pcm.tx_queue[0].primitive, 0x158)

    def test_pcm_task_rejects_bad_length_route_and_size(self):
        self.assertFalse(self.dect.pcm_task(b"\x01\x02"))
        self.assertFalse(self.dect.pcm_task(pcm_frame(0x158, b"x", route=0x99)))
        oversized = pcm_frame(0x158, b"x" * AVM_DECT_PCM_MAIL_MAX)
        self.assertFalse(self.dect.pcm_task(oversized))

    def test_pcm_task_drops_remote_status_until_enabled(self):
        frame = pcm_frame(0xFFF1, b"status")
        self.assertFalse(self.dect.pcm_task(frame))
        self.dect.pcm.remote_status_enabled = True
        self.assertTrue(self.dect.pcm_task(frame))

    def test_pcm_rx_dispatch(self):
        self.assertEqual(self.dect.pcm.check_rx(pcm_frame(0xF625, b"x" * 0x30)),
                         "pcm_status")
        self.assertEqual(self.dect.pcm.check_rx(pcm_frame(0xFFF1, b"x" * 0x10)),
                         "remote_status")
        self.assertEqual(self.dect.pcm.check_rx(pcm_frame(0x242, b"x" * 0x10)),
                         "test_cfm")
        self.assertEqual(self.dect.pcm.check_rx(pcm_frame(0x1234, b"x" * 0x10)),
                         "raw")
        self.assertEqual(self.dect.pcm.check_rx(b"\x01\x02"), "drop")

    def test_pcm_checksum(self):
        good = frame_with_checksum(0x158, b"payload")
        self.assertTrue(self.dect.pcm.checksum_valid(good))
        bad = good[:-2] + struct.pack("<H", 0)
        self.assertFalse(self.dect.pcm.checksum_valid(bad))
        self.assertFalse(self.dect.pcm.checksum_valid(b"\x00"))

    def test_uota_slot_lifecycle(self):
        self.dect.init()
        received = []
        handle = self.dect.open_uota_slot(3, received.append)
        self.assertIn(handle, self.pcm.audio_slots)
        self.assertEqual(self.pcm.audio_slots[handle].linkmask, 1 << 3)
        self.assertTrue(self.pcm.notify_slot_data(handle, b"audio"))
        self.assertEqual(received, [b"audio"])
        self.dect.close_uota_slot(3)
        self.assertNotIn(handle, self.pcm.audio_slots)

    def test_uota_slot_limits(self):
        self.dect.init()
        for slot in (0, 8):
            with self.assertRaises(Exception):
                self.dect.open_uota_slot(slot, lambda data: None)
        with self.assertRaises(Exception):
            self.dect.close_uota_slot(1)


if __name__ == "__main__":
    unittest.main()
