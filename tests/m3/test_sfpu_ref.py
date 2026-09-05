import unittest
import numpy as np
from ref.sfpu_ref import (affine_int, dynamic_int8_parameters, gelu_int,
                         layernorm_int, requantize_int8, rne_div, softmax_int)


class SfpuReferenceTests(unittest.TestCase):
    def test_rounding_ties_and_sign(self):
        self.assertEqual([rne_div(v, 2) for v in range(-7, 8)],
                         [-4, -3, -2, -2, -2, -1, 0, 0, 0, 1, 2, 2, 2, 3, 4])
        with self.assertRaises(ValueError):
            rne_div(1, 0)

    def test_gelu_tail(self):
        np.testing.assert_array_equal(gelu_int([-32768, -2048, 0, 2048, 32767]),
                                      [0, 0, 0, 2048, 32767])

    def test_constant_layernorm(self):
        np.testing.assert_array_equal(layernorm_int([32767] * 3, [4096] * 3,
                                                    [-32768, 0, 32767]),
                                      [-32768, 0, 32767])

    def test_softmax_masks_mass(self):
        np.testing.assert_array_equal(softmax_int([0] * 3, [True] * 3),
                                      [10923, 10923, 10922])
        np.testing.assert_array_equal(softmax_int([32767, -32768], [False, True]),
                                      [0, 32768])
        np.testing.assert_array_equal(softmax_int([0, 1], [False, False]), [0, 0])

    def test_affine_bias_after_round_and_saturation(self):
        np.testing.assert_array_equal(affine_int([1, 3, -1, -3], [1] * 4,
                                                 [1] * 4, 1), [1, 3, 1, -1])
        np.testing.assert_array_equal(affine_int([2147483647, -2147483648],
                                                 [2147483647] * 2, [0] * 2, 0),
                                      [32767, -32768])

    def test_requantization(self):
        self.assertEqual(dynamic_int8_parameters([0, 0]), (0, 24))
        multiplier, shift = dynamic_int8_parameters([-32768, 0, 32767])
        np.testing.assert_array_equal(requantize_int8([-32768, 0, 32767], multiplier, shift),
                                      [-127, 0, 127])
        np.testing.assert_array_equal(requantize_int8([-32768, 32767], 1, 0), [-128, 127])
        multiplier, shift = dynamic_int8_parameters([0, 32768])
        np.testing.assert_array_equal(requantize_int8([0, 32768], multiplier, shift), [0, 127])
        multiplier, shift = dynamic_int8_parameters([32] * 1024)
        np.testing.assert_array_equal(requantize_int8([32] * 1024, multiplier, shift), [127] * 1024)

    def test_invalid_domains(self):
        for values in ([], [32768], [-32769]):
            with self.assertRaises(ValueError):
                gelu_int(values)
        with self.assertRaises(TypeError):
            gelu_int([0.5])
        with self.assertRaises(ValueError):
            softmax_int([0], [1])
        with self.assertRaises(ValueError):
            layernorm_int([0], [4096, 4096], [0])


if __name__ == "__main__":
    unittest.main()
