import copy
import unittest
from scripts.summarize_m4_performance import analyze_group, paired_ratios, memory_fields


def observation(iteration, seconds, backend='cpu', workload='prefill_first_token'):
    return {'iteration': iteration, 'seconds': seconds, 'backend': backend, 'workload': workload,
            'model_before_greedy_seconds': seconds / 2,
            'wall_profile': {'gemm_seconds': seconds / 4, 'sfpu_seconds': seconds / 4,
                             'host_remainder_seconds': seconds / 2}, 'counts': {'gemm_macs': 100}}


class PerformanceAnalysisTests(unittest.TestCase):
    def test_rates_and_ratio_direction_not_reciprocal_latency_percentiles(self):
        cpu = [observation(i, t) for i, t in enumerate([1., 2., 8.])]
        fpga = [observation(i, t, 'fpga') for i, t in enumerate([2., 4., 16.])]
        result = analyze_group(cpu)
        self.assertEqual(result['latency_seconds']['median'], 2)
        self.assertEqual(result['prefill_input_tokens_per_second']['median'], 13)
        self.assertEqual(result['delivered_tokens_per_second']['median'], .5)
        self.assertEqual(result['profile_fraction_of_total_wall']['host_remainder_seconds'], .5)
        self.assertEqual(paired_ratios(cpu, fpga)['median'], .5)  # FPGA slower
        with self.assertRaises(ValueError):
            paired_ratios(cpu, fpga[:-1])

    def test_generation_is_three_chains_not_sixty_independent_trials(self):
        rows = []
        for i in range(3):
            row = observation(i, 3., workload='generation_20_tokens')
            row.pop('model_before_greedy_seconds')
            times = [.5] + [.1] * 19
            row.update(tokens=[1] * 20, token_delivery_seconds=times, first_token_seconds=times[0],
                       cached_decode_seconds=sum(times[1:]))
            rows.append(row)
        result = analyze_group(rows)
        self.assertEqual(result['independent_chain_trials'], 3)
        self.assertEqual(result['latency_seconds']['n'], 3)
        self.assertEqual(result['cached_decode_latency_seconds_pooled']['n'], 57)
        self.assertAlmostEqual(result['cached_decode_tokens_per_second_per_chain']['median'], 10.)
        self.assertAlmostEqual(result['delivered_tokens_per_second']['median'], 20 / 3)
        wrong = copy.deepcopy(rows)
        wrong[0]['seconds'] = .1
        with self.assertRaises(ValueError):
            analyze_group(wrong)

    def test_memory_keeps_process_units_and_threads_explicit(self):
        snapshot = {'max_rss_kib': 200,
                    '/proc/self/status': 'VmRSS:\t100 kB\nVmHWM:\t200 kB\nVmSwap:\t0 kB\nThreads:\t1\n',
                    '/proc/self/smaps_rollup': 'Rss: 100 kB\nPss: 75 kB\nSwap: 0 kB\nSwapPss: 0 kB\n'}
        result = memory_fields(snapshot)
        self.assertEqual(result['Pss_kib'], 75)
        self.assertEqual(result['Threads'], 1)
        self.assertEqual(result['max_rss_kib'], 200)
        with self.assertRaises(ValueError):
            memory_fields(dict(snapshot, **{'/proc/self/smaps_rollup': ''}))


if __name__ == '__main__':
    unittest.main()
