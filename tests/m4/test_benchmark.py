import hashlib
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from zynq.m4_benchmark import (POLICY_SHA, ProfiledBackend, statistics, snapshot_cache,
                               restore_cache, measure, fixed_action, generation_action,
                               summarize, paired_order, scalar_bridge)
from zynq.m4_offload import Runtime, CpuBackend


class BenchmarkTests(unittest.TestCase):
    def test_policy_pin(self):
        path = Path(__file__).with_name('performance_policy.json')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), POLICY_SHA)

    def test_statistics_all_samples_no_trimming(self):
        values = [1, 2, 3, 100]
        result = statistics(values)
        self.assertEqual(result['n'], 4)
        self.assertEqual(result['median'], 2.5)
        self.assertAlmostEqual(result['p95_linear'], 85.45)
        rows = [{'workload': 'a', 'backend': 'cpu', 'warmup': i == 0, 'seconds': x}
                for i, x in enumerate(values)]
        self.assertEqual(summarize(rows)['a:cpu']['n'], 3)
        for bad in ([], [-1], [float('nan')]):
            with self.assertRaises(ValueError):
                statistics(bad)

    def test_profile_is_disjoint_and_inside_wall(self):
        actual = SimpleNamespace(counts=Counter(), gemm=lambda *args: 5, sfpu=lambda *args: 7)
        backend = ProfiledBackend(actual)
        with patch('zynq.m4_benchmark.time.perf_counter', side_effect=[0., 1., 3., 4., 5., 10.]):
            result, row = measure(backend, lambda: (backend.gemm(None, None, 1), backend.sfpu(None, None)))
        self.assertEqual(result, (5, 7))
        self.assertEqual(row['seconds'], 10)
        self.assertEqual(row['wall_profile'], {'gemm_seconds': 2., 'sfpu_seconds': 1., 'host_remainder_seconds': 7.})

    def test_snapshot_includes_derived_cache_and_rejects_failed_hardware(self):
        runtime = SimpleNamespace(length=2, capacity=4, failed=False,
                                  backend=SimpleNamespace(failed=False))
        for key, shape in (('k', (2, 3, 4, 2)), ('v', (2, 3, 4, 2)),
                           ('k8', (2, 3, 4, 2)), ('kunits', (2, 3, 4))):
            setattr(runtime, key, np.arange(np.prod(shape)).reshape(shape).copy())
        saved = snapshot_cache(runtime)
        runtime.k.fill(-1)
        runtime.k8.fill(-1)
        runtime.kunits.fill(-1)
        runtime.length = 4
        restore_cache(runtime, saved)
        self.assertEqual(runtime.length, 2)
        for key in ('k', 'v', 'k8', 'kunits'):
            np.testing.assert_array_equal(getattr(runtime, key)[:, :, :2], saved[key])
        self.assertTrue(np.all(runtime.k[:, :, 2:] == -1))
        runtime.backend.failed = True
        with self.assertRaises(RuntimeError):
            restore_cache(runtime, saved)

    def test_actions_include_reset_prefill_greedy_delivery(self):
        events = []
        logits = np.array([[0., 2., 2.]])
        runtime = SimpleNamespace(reset=lambda: events.append('reset'),
                                  prefill=lambda tokens: (events.append(('prefill', tokens)) or logits),
                                  step=lambda tokens: (events.append(('step', tokens)) or logits))
        _, tokens, _ = fixed_action(runtime, [3, 4], 1, 'prefill_first_token')()
        self.assertEqual(tokens, [1])  # lowest-ID tie, no reference selection
        self.assertEqual(events, ['reset', ('prefill', [3, 4])])
        events.clear()
        result, outputs, latencies = generation_action(runtime, [3], 20)()
        self.assertEqual(result, [1] * 20)
        self.assertEqual(len(outputs), 20)
        self.assertEqual(len(latencies), 20)
        self.assertEqual(events.count('reset'), 1)
        self.assertEqual(events.count(('step', [1])), 19)

    def test_scalar_vs_batched_measurement_inputs_identical(self):
        root = Path(__file__).resolve().parents[2]
        runtime = Runtime.__new__(Runtime)
        runtime.backend = ProfiledBackend(CpuBackend(root / 'build/m4_cpu_gemm_host.so', root / 'build/m4_cpu_sfpu_host.so'))
        runtime.metadata_counts = Counter()
        raw = np.random.default_rng(121).integers(-32768, 32768, (13, 64), dtype=np.int32)
        raw[:, 0] = 0
        before = raw.copy()
        scalar, _ = measure(runtime.backend, lambda: scalar_bridge(runtime, raw))
        batched, _ = measure(runtime.backend, lambda: runtime.requant_columns(raw, 1 / 256))
        np.testing.assert_array_equal(scalar[0], batched[0])
        np.testing.assert_array_equal(scalar[1], batched[1])
        np.testing.assert_array_equal(raw, before)

    def test_paired_order_is_repeatable_and_contains_both(self):
        import random
        one, two = random.Random(5), random.Random(5)
        for _ in range(20):
            a, b = paired_order(one), paired_order(two)
            self.assertEqual(a, b)
            self.assertEqual(sorted(a), ['cpu', 'fpga'])


if __name__ == '__main__':
    unittest.main()
