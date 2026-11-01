import unittest

from pcmlink_mock import (
    PCMLINK_ACTIVITY_MASK,
    PCMLINK_DECTCTRL_DEFAULT_COUNT,
    PCMLINK_DECTCTRL_DEFAULT_SLOT_COUNT,
    PCMLINK_DECTCTRL_DEFAULT_START,
    PcmlinkError,
    PcmlinkInvalidArgument,
    PcmlinkMock,
)


class PcmlinkMockTests(unittest.TestCase):
    def setUp(self):
        self.pcm = PcmlinkMock()

    def test_register_requires_started_isdn(self):
        with self.assertRaises(PcmlinkError):
            self.pcm.register_dectcontrol(lambda data: None)

    def test_dect_control_lifecycle(self):
        self.pcm.start_isdn()
        received = []
        handle, slots = self.pcm.register_dectcontrol(received.append)
        self.assertEqual(slots, PCMLINK_DECTCTRL_DEFAULT_SLOT_COUNT)
        self.assertEqual(len(self.pcm.status_calls), 4)
        self.assertEqual([s for _, s, _ in self.pcm.status_calls], [12, 13, 14, 15])

        self.pcm.config_dectcontrol(handle)
        ctl = self.pcm.dect_control
        self.assertEqual(ctl.start, PCMLINK_DECTCTRL_DEFAULT_START)
        self.assertEqual(ctl.count, PCMLINK_DECTCTRL_DEFAULT_COUNT)
        self.assertTrue(ctl.configured)

        self.assertTrue(self.pcm.notify_dect_control(b"\xAA\x01"))
        self.assertEqual(received, [b"\xAA\x01"])
        self.pcm.release_dectcontrol(handle)
        self.assertIsNone(self.pcm.dect_control)
        self.assertFalse(self.pcm.notify_dect_control(b"x"))

    def test_config_requires_registration_and_is_one_shot(self):
        self.pcm.start_isdn()
        handle, _ = self.pcm.register_dectcontrol(lambda data: None)
        self.pcm.config_dectcontrol(handle)
        with self.assertRaises(PcmlinkError):
            self.pcm.config_dectcontrol(handle)
        with self.assertRaises(PcmlinkError):
            self.pcm.config_dectcontrol(handle + 1)

    def test_audio_slot_linkmask_validation(self):
        self.pcm.start_isdn()
        for bad in (0, 0x01, 0x100, 0x1FE):
            with self.assertRaises(PcmlinkInvalidArgument):
                self.pcm.openslots(bad, lambda data: None)
        for good, bits in ((0x02, 1), (0x80, 1), (0xFE, 7)):
            handle = self.pcm.openslots(good, lambda data: None)
            self.assertEqual(self.pcm.audio_slots[handle].linkmask, good)
            self.pcm.closeslots(handle)
            self.assertNotIn(handle, self.pcm.audio_slots)
            self.assertEqual(bits, good.bit_count())

    def test_audio_slot_data_and_close(self):
        self.pcm.start_isdn()
        received = []
        handle = self.pcm.openslots(0x02, received.append)
        self.assertTrue(self.pcm.notify_slot_data(handle, b"pcm"))
        self.assertEqual(received, [b"pcm"])
        self.pcm.closeslots(handle)
        self.assertFalse(self.pcm.notify_slot_data(handle, b"pcm"))
        with self.assertRaises(PcmlinkError):
            self.pcm.closeslots(handle)

    def test_activity_is_recorded(self):
        self.pcm.activity(0, PCMLINK_ACTIVITY_MASK, 1)
        self.assertEqual(self.pcm.activity_calls,
                         [(0, PCMLINK_ACTIVITY_MASK, 1)])


if __name__ == "__main__":
    unittest.main()
