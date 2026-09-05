import unittest
import numpy as np
from tests.m4.evaluate_scaled import metrics, aggregate
from tests.m4.qualify_scaled_quality import check_limits


class QualityMetricTests(unittest.TestCase):
    def test_identical_distribution_and_common_offset(self):
        f = np.zeros((3, 50257))
        f[0, 12], f[1, 50000] = 5, 7
        result = aggregate([metrics(f, f + np.array([[10], [-20], [1000]]), np.array([12, 15, 3]))])
        self.assertAlmostEqual(result['perplexity_ratio'], 1)
        self.assertEqual(result['top1_agreement'], 1)
        self.assertEqual(result['top5_inclusion'], 1)
        self.assertAlmostEqual(result['mean_forward_kl_nats'], 0)
        self.assertAlmostEqual(result['centered_logit_rmse'], 0)

    def test_lowest_id_ties_and_nonfinite_rejection(self):
        f = np.zeros((2, 50257)); q = np.zeros_like(f)
        f[0, 4], f[1, 5] = 1, 1
        result = metrics(f, q, np.array([0, 0]))
        self.assertEqual(result['top1_matches'], 0)
        self.assertEqual(result['float_top1_in_quantized_top5'], 1)
        q[0, 0] = np.nan
        with self.assertRaises(ValueError):
            metrics(f, q, np.array([0, 0]))

    def test_gate_boundaries(self):
        limits = {'maximum_perplexity_ratio': 1.1, 'minimum_teacher_forced_top1_agreement': .85,
                  'minimum_float_top1_in_quantized_top5': .97, 'maximum_mean_forward_kl_nats': .05}
        result = {'perplexity_ratio': 1.1, 'top1_agreement': .85, 'top5_inclusion': .97, 'mean_forward_kl_nats': .05}
        self.assertTrue(all(check_limits(result, limits).values()))
        result['perplexity_ratio'] = 1.10001
        self.assertFalse(all(check_limits(result, limits).values()))


if __name__ == '__main__':
    unittest.main()
