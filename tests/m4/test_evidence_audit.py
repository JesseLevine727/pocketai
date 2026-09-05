import copy
import json
from pathlib import Path
import unittest
from scripts.audit_m4 import check_benchmark_rows, assert_no_process_swap, check_frozen
from zynq.m4_benchmark import summarize


def synthetic_inventory(policy):
    names = ['gemm_down_projection_tile', 'gemm_vocabulary_tail']
    names += ['sfpu_' + name for name in ('gelu', 'layernorm', 'softmax', 'affine', 'requant8', 'affine_gelu', 'add')]
    names += [f'v_bridge_{length}x64_{method}' for length in (13, 32, 1024) for method in ('scalar', 'batched')]
    names += policy['fixed_workloads']
    rows = []
    def row(workload, backend, iteration, warmup):
        return {'workload': workload, 'backend': backend, 'iteration': iteration,
                'warmup': warmup, 'status': 'EXACT_PASS', 'seconds': 3.,
                'counts': {'dma_input_bytes': 8, 'dma_output_bytes': 4} if backend == 'fpga' else {},
                'wall_profile': {'gemm_seconds': 1., 'sfpu_seconds': 1., 'host_remainder_seconds': 1.}}
    for name in names:
        for backend in ('cpu', 'fpga'):
            for i in range(policy['warmups'] + policy['fixed_workload_trials']):
                rows.append(row(name, backend, i, i < policy['warmups']))
    for backend in ('cpu', 'fpga'):
        for i in range(policy['warmups']):
            rows.append(row('generation_two_token_warmup', backend, i, True))
        for i in range(policy['full_generation_trials']):
            rows.append(row('generation_20_tokens', backend, i, False))
    return {'trials': rows, 'summary_seconds': summarize(rows)}


class EvidenceAuditTests(unittest.TestCase):
    def test_full_sampling_inventory_rejects_missing_duplicate_and_wrong_boundary(self):
        policy = json.loads(Path(__file__).with_name('performance_policy.json').read_text())
        report = synthetic_inventory(policy)
        self.assertEqual(len(report['trials']), 794)
        check_benchmark_rows(report, policy)
        missing = copy.deepcopy(report)
        missing['trials'].pop()
        with self.assertRaises(ValueError):
            check_benchmark_rows(missing, policy)
        duplicate = copy.deepcopy(report)
        duplicate['trials'].append(duplicate['trials'][0])
        with self.assertRaises(ValueError):
            check_benchmark_rows(duplicate, policy)
        overlap = copy.deepcopy(report)
        overlap['trials'][0]['wall_profile']['host_remainder_seconds'] = 2.
        with self.assertRaises(ValueError):
            check_benchmark_rows(overlap, policy)
        fake_summary = copy.deepcopy(report)
        fake_summary['summary_seconds'] = {}
        with self.assertRaises(ValueError):
            check_benchmark_rows(fake_summary, policy)
        mismatch = copy.deepcopy(report)
        mismatch['trials'][0]['counts']['gemm_macs'] = 1
        with self.assertRaises(ValueError):
            check_benchmark_rows(mismatch, policy)

    def test_process_swap_is_not_global_swap_and_missing_measurement_fails(self):
        memory = {'/proc/self/status': 'Name:\tpython3\nVmSwap:\t       0 kB\n',
                  '/proc/meminfo': 'SwapFree: 12 kB\n', 'max_rss_kib': 5}
        assert_no_process_swap(memory)
        for status in ('VmSwap:\t 1 kB\n', 'Name:\tpython3\n'):
            with self.assertRaises(ValueError):
                assert_no_process_swap(dict(memory, **{'/proc/self/status': status}))

    def test_frozen_quality_uses_empty_clipping_dictionary_schema(self):
        # This also checks that the audit reads the real pinned evidence, not
        # replacement numerical expectations fabricated by the audit itself.
        self.assertGreater(len(check_frozen()), 5)


if __name__ == '__main__':
    unittest.main()
