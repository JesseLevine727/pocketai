"""Host-side harness checks; these are NOT physical-board acceptance."""
import unittest
import numpy as np
from ref.m3_packets import Packet
from zynq.m3_run import Driver, statistics


class Registers:
    def __init__(self, contents):
        self.contents = contents

    def read(self, offset):
        return self.contents.get(offset, 0)


class BoardHarnessTests(unittest.TestCase):
    def test_completion_checks_unsigned_probability_and_word_counts(self):
        result = np.array([32768, 0], dtype="<u4")
        packet = Packet(1, (3, 2, 0, 0), 77, result, result, 167)
        regs = Registers({0x20: 77, 0x24: 167, 0x28: 2, 0x2c: 2, 0x30: 2, 0x34: 5})
        driver = Driver.__new__(Driver)
        driver.engines = [None, regs]
        driver.check(packet, result.copy(), 5)
        for offset, wrong in ((4, 2), (0x20, 78), (0x24, 166), (0x28, 3),
                              (0x2c, 3), (0x30, 1), (0x34, 4), (0x38, 8)):
            old = regs.contents.get(offset, 0)
            regs.contents[offset] = wrong
            with self.assertRaises(AssertionError):
                driver.check(packet, result.copy(), 5)
            regs.contents[offset] = old
        with self.assertRaises(AssertionError):
            driver.check(packet, np.array([0xffff8000, 0], dtype="<u4"), 5)

    def test_latency_statistics_are_not_compute_throughput(self):
        stats = statistics([0.001, 0.002, 0.003])
        self.assertEqual((stats["median_ms"], stats["min_ms"], stats["max_ms"]), (2, 1, 3))
        self.assertAlmostEqual(stats["p95_ms"], 2.9)
        self.assertNotIn("gmac_s", stats)


if __name__ == "__main__":
    unittest.main()
