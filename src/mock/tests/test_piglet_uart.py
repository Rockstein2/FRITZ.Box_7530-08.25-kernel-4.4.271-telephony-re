import unittest
from pathlib import Path

from piglet_image import build_image
from piglet_uart_mock import PigletUploadHostModel, UartProtocolError


ROOT = Path(__file__).resolve().parents[3]
FW = ROOT / "firmware"


class PigletUartTests(unittest.TestCase):
    def test_slow_first_level(self):
        image, _ = build_image(FW / "dectfw_firstlevel_441_slow.hex", 0)
        result = PigletUploadHostModel().upload(image, header_len=2)
        self.assertTrue(result.ok)
        self.assertEqual(result.checksum, image[-1])
        self.assertEqual(result.chip_state, "done")

    def test_slow_second_level(self):
        image, _ = build_image(FW / "dectfw_secondlevel_441.hex", 1)
        result = PigletUploadHostModel().upload(image, header_len=4)
        self.assertTrue(result.ok)

    def test_fast_second_level(self):
        image, _ = build_image(FW / "dectfw_secondlevel_441.hex", 1)
        result = PigletUploadHostModel(fast=True).upload(image, header_len=4)
        self.assertTrue(result.ok)

    def test_bad_checksum_rejected(self):
        image, _ = build_image(FW / "dectfw_firstlevel_441_slow.hex", 0)
        broken = image[:-1] + bytes([image[-1] ^ 0xFF])
        result = PigletUploadHostModel().upload(broken, header_len=2)
        self.assertFalse(result.ok)
        self.assertEqual(result.chip_state, "error")

    def test_hello_mismatch(self):
        from piglet_uart_mock import DectChipUartModel
        chip = DectChipUartModel(header_len=4, fast=True)
        chip.reset()
        with self.assertRaises(UartProtocolError):
            chip.feed(b"HELLO WRONG")


if __name__ == "__main__":
    unittest.main()
