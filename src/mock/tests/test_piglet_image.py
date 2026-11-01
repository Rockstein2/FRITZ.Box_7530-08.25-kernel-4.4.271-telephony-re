import struct
import unittest
from pathlib import Path

from piglet_image import build_image


ROOT = Path(__file__).resolve().parents[3]
FW = ROOT / "firmware"


class PigletImageTests(unittest.TestCase):
    def test_first_level(self):
        image, meta = build_image(FW / "dectfw_firstlevel_441_slow.hex", 0)
        self.assertEqual(len(image), 0x275)
        self.assertEqual(struct.unpack_from(">H", image, 0)[0], 0x0272)
        self.assertEqual(meta["blocks"][0][0], 0x10080)
        self.assertEqual(len(meta["blocks"]), 1)
        payload = image[2:-1]
        self.assertEqual(struct.unpack_from(">II", payload, 0), (0x10080, 0x26A))
        checksum = 0
        for b in payload:
            checksum ^= b
        self.assertEqual(image[-1], checksum)

    def test_second_level(self):
        image, meta = build_image(FW / "dectfw_secondlevel_441.hex", 1)
        self.assertEqual(len(image), 0xD36C)
        self.assertEqual(struct.unpack_from(">I", image, 0)[0], 0xD367)
        self.assertEqual(len(meta["blocks"]), 9)
        self.assertEqual(meta["blocks"][0][0], 0)
        checksum = 0
        for b in image[4:-1]:
            checksum ^= b
        self.assertEqual(image[-1], checksum)

    def test_p2test(self):
        image, meta = build_image(FW / "dectfw_secondlevel_441p2test.hex", 1)
        self.assertEqual(len(image), 0xC28D)
        self.assertEqual(struct.unpack_from(">I", image, 0)[0], 0xC288)
        self.assertEqual(len(meta["blocks"]), 8)


if __name__ == "__main__":
    unittest.main()
