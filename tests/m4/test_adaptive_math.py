import unittest
from collections import Counter
import numpy as np
from ref.gpt2_scaled import ScaledGPT2
from ref.gpt2_adaptive import AdaptiveGPT2


class AdaptiveMathTests(unittest.TestCase):
    def make_model(self):
        model = AdaptiveGPT2.__new__(AdaptiveGPT2)
        model.stats, model.maxima = Counter(), {}
        model.smoothing = {'test': np.array([.001, .1, 10.0])}
        model.linears = {'test': (np.array([[1, 2], [3, 4], [5, 6]], dtype=np.float64), np.array([.2, .3]), np.array([1., -1.]))}
        return model

    def test_nonoverflow_exact_v2(self):
        model = self.make_model()
        x = np.array([[1, 2, 3], [-2, 3, 4]], dtype=np.int16)
        actual, exponent = model.smooth(x, 'test')
        expected = ScaledGPT2.smooth(model, x, 'test')
        np.testing.assert_array_equal(actual, expected)
        np.testing.assert_array_equal(exponent, [0, 0])
        got = model.wide_linear((actual, exponent), 'test')
        expected_linear = ScaledGPT2.wide_linear(model, expected, 'test')
        for a, e in zip(got, expected_linear):
            np.testing.assert_array_equal(a, e)

    def test_overflow_uses_units_not_clipping(self):
        model = self.make_model()
        x = np.array([[30000, 20, -30], [1, 2, 3]], dtype=np.int16)
        actual, exponent = model.smooth(x, 'test')
        self.assertGreater(exponent[0], 0)
        self.assertEqual(exponent[1], 0)
        expected_logical = x.astype(np.float64) / model.smoothing['test'] / 256
        actual_logical = actual * 2.0 ** exponent[:, None] / 256
        self.assertTrue(np.all(np.abs(expected_logical - actual_logical) <= 2.0 ** exponent[:, None] / 512 + 1e-9))
        self.assertFalse(any(v for k, v in model.stats.items() if k.endswith('.clipped')))
        sums, scales, bias = model.wide_linear((actual, exponent), 'test')
        base_sums, base_scales, base_bias = ScaledGPT2.wide_linear(model, actual, 'test')
        np.testing.assert_array_equal(sums, base_sums)
        np.testing.assert_array_equal(scales, base_scales * 2.0 ** exponent[:, None])
        np.testing.assert_array_equal(bias, base_bias)


if __name__ == '__main__':
    unittest.main()
