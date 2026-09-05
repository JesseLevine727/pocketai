import unittest
import numpy as np
from ref import sfpu_ref as sf
from ref.gpt2_quantized import rne_shift, dynamic_columns, affine_metadata


class QuantizedMathTests(unittest.TestCase):
    def test_signed_rne(self):
        rng = np.random.default_rng(0x4d34514e)
        values = np.concatenate((rng.integers(-(1 << 60), 1 << 60, size=1000, dtype=np.int64),
                                 np.arange(-65, 66, dtype=np.int64)))
        for shift in range(32):
            expected = [sf.rne_div(int(x), 1 << shift) for x in values]
            np.testing.assert_array_equal(rne_shift(values, shift), expected)

    def test_dynamic_columns(self):
        raw = np.array([[-32768, 0, 32768], [32767, 0, 13], [0, 0, 19]], dtype=np.int64)
        got, scales = dynamic_columns(raw, 1 / 256)
        for i in range(3):
            mult, shift = sf.dynamic_int8_parameters(raw[:, i])
            np.testing.assert_array_equal(got[:, i], sf.requantize_int8(raw[:, i], mult, shift))
            self.assertEqual(scales[i], (1 << 24) / mult / 256 if mult else 1)

    def test_affine_and_wide_matmul(self):
        rng = np.random.default_rng(0x4d34574d)
        a = rng.integers(-128, 128, (3, 3072), dtype=np.int64)
        b = rng.integers(-128, 128, (3072, 17), dtype=np.int64)
        np.testing.assert_array_equal((a.astype(np.float64) @ b.astype(np.float64)).astype(np.int64), a @ b)
        a.fill(-128); b.fill(-128)
        np.testing.assert_array_equal((a.astype(np.float64) @ b.astype(np.float64)).astype(np.int64), a @ b)
        scales = rng.uniform(0, 4, 17)
        mult, shift = affine_metadata(scales)
        bias = rng.integers(-100000, 100000, 17, dtype=np.int64)
        actual = np.clip(rne_shift((a @ b)[0] * mult, shift) + bias, -32768, 32767)
        np.testing.assert_array_equal(actual, sf.affine_int((a @ b)[0], mult, bias, shift))
        with self.assertRaises(ValueError):
            affine_metadata([1e-30])


if __name__ == '__main__':
    unittest.main()
