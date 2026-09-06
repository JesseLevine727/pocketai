"""Packing domain tests; the quality runner checks every candidate weight."""
import unittest
import numpy as np
from tests.m5_opt.evaluate_precision import pack, unpack


class PackingTests(unittest.TestCase):
    def test_all_signed_pairs(self):
        pairs = np.asarray([(a, b) for a in range(-7, 8) for b in range(-7, 8)], dtype=np.int8)
        np.testing.assert_array_equal(unpack(pack(pairs)), pairs.reshape(-1))

    def test_nibble_order(self):
        self.assertEqual(pack(np.asarray([-7, 7], dtype=np.int8)).tolist(), [0x79])

    def test_rejects_bad_domain(self):
        for values in ([1], [-8, 0], [0, 8]):
            with self.assertRaises(ValueError):
                pack(np.asarray(values, dtype=np.int8))


if __name__ == '__main__':
    unittest.main()
