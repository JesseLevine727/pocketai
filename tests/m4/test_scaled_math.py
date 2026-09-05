import unittest
import numpy as np
from ref import sfpu_ref as sf
from ref.gpt2_scaled import epsilon_correction, storage_exponent, channel_balance, ScaledGPT2
from collections import Counter


class ScaledMathTests(unittest.TestCase):
    def test_range_selection(self):
        x = np.array([0, 127, 128, 256, 3028, 5000])
        e = storage_exponent(x)
        self.assertTrue(np.all(x * 256 / 2.0 ** e <= 32700))
        self.assertTrue(np.all((e == 0) | (x * 256 / 2.0 ** (e - 1) > 32700)))
        with self.assertRaises(ValueError):
            storage_exponent([np.inf])

    def test_epsilon_compensation(self):
        for row in (np.zeros(768), np.ones(768), np.arange(768) % 2,
                    np.arange(768) - 384, np.arange(768) % 3 + 32765):
            row = row.astype(np.int16)
            z = row.astype(np.float64) / 256
            for e in (0, 1, 5, 10):
                c = epsilon_correction(row, e)
                lhs = (z - z.mean()) / np.sqrt(z.var() + 1e-5) * c
                x = z * 2.0 ** e
                rhs = (x - x.mean()) / np.sqrt(x.var() + 1e-5)
                np.testing.assert_allclose(lhs, rhs, atol=1e-12, rtol=1e-12)

    def test_balancing_identity(self):
        rng = np.random.default_rng(234)
        x = rng.normal(size=(4, 20))
        w = rng.normal(size=(20, 33))
        for alpha in (0, 0.5, 0.75, 1):
            s = channel_balance(np.abs(x).max(axis=0), w, alpha)
            np.testing.assert_allclose((x / s) @ (w * s[:, None]), x @ w, atol=1e-13)
            self.assertTrue(np.all(s > 0))

    def test_norm_matches_m3_at_unit_scale(self):
        model = ScaledGPT2.__new__(ScaledGPT2)
        model.stats, model.maxima = Counter(), {}
        rng = np.random.default_rng(434)
        gain = rng.integers(-4096, 4096, 768, dtype=np.int16)
        bias = rng.integers(-256, 256, 768, dtype=np.int16)
        model.norms = {'test': (gain.astype(np.float64) / 4096, bias.astype(np.float64) / 256)}
        x = rng.integers(-32000, 32000, (4, 768), dtype=np.int16)
        got = model.norm(x, np.zeros(4, dtype=np.int32), 'test')
        for row, actual in zip(x, got):
            np.testing.assert_array_equal(actual, sf.layernorm_int(row, gain, bias))

    def test_score_centering_before_saturation(self):
        model = ScaledGPT2.__new__(ScaledGPT2)
        model.stats, model.maxima = Counter(), {}
        # Without pre-centering, both large scores saturate to the same 32767.
        raw = np.array([200000, 200001, -1000000, 199500], dtype=np.int64)
        scores = model.scores(raw, np.ones(4), 'test')
        np.testing.assert_array_equal(scores, [-1, 0, -32768, -501])
        np.testing.assert_array_equal(scores, sf.affine_int(raw, [1] * 4, [-200001] * 4, 0))
        np.testing.assert_array_equal(sf.softmax_int(scores, np.ones(4, dtype=bool)),
                                      sf.softmax_int([-1, 0, -4096, -501], np.ones(4, dtype=bool)))
        self.assertEqual(model.stats['test.intentional_zero_tail_clamps'], 1)

    def test_norm_bias_precedes_saturation(self):
        model = ScaledGPT2.__new__(ScaledGPT2)
        model.stats, model.maxima = Counter(), {}
        x = np.zeros((1, 768), dtype=np.int16); x[0, 0] = 32000
        gain = np.full(768, 30000, dtype=np.int16)
        bias = np.full(768, -30000, dtype=np.int16)
        model.norms = {'test': (gain.astype(np.float64) / 4096, bias.astype(np.float64) / 256)}
        got = model.norm(x, [0], 'test')
        np.testing.assert_array_equal(got[0], sf.layernorm_int(x[0], gain, bias))


if __name__ == '__main__':
    unittest.main()
