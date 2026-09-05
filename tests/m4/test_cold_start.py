import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from zynq.m4_cold_start import measure_process, completed_prerequisites, policy_at, sha


class ColdStartTests(unittest.TestCase):
    def test_first_token_delivery_precedes_acknowledged_validation(self):
        program = """
import json, sys, time
time.sleep(.02)
print('M4_COLD_EVENT ' + json.dumps({'event':'first_token','token':257}), flush=True)
assert sys.stdin.readline() == 'DELIVERY_RECORDED\\n'
time.sleep(.25)
print('M4_COLD_EVENT ' + json.dumps({'event':'result','token':257,'status':'EXACT_FIRST_TOKEN_LOGIT_KV_PASS'}), flush=True)
"""
        result = measure_process([sys.executable, '-c', program], '.', dict(os.environ), timeout=5)
        self.assertEqual(result['token'], 257)
        self.assertEqual(result['exit_code'], 0)
        self.assertGreater(result['full_process_completion_seconds'] - result['first_token_seconds'], .2)
        self.assertEqual(len(result['raw_child_lines']), 2)

    def test_invalid_token_event_aborts_without_accepted_observation(self):
        program = """
import json, sys
print('M4_COLD_EVENT ' + json.dumps({'event':'first_token','token':True}), flush=True)
sys.stdin.readline()
"""
        with self.assertRaises(RuntimeError) as raised:
            measure_process([sys.executable, '-c', program], '.', dict(os.environ), timeout=5)
        self.assertIsNone(raised.exception.observation['token'])
        self.assertNotIn('active_child_pid', raised.exception.observation)

    def test_timeout_requests_graceful_abort_not_force_kill(self):
        with self.assertRaises(TimeoutError) as raised:
            measure_process([sys.executable, '-c', 'import time; time.sleep(10)'], '.', dict(os.environ), timeout=.05)
        self.assertNotIn('active_child_pid', raised.exception.observation)
        self.assertIsNotNone(raised.exception.observation['exit_code'])

    def test_prerequisites_and_frozen_policy_prevent_competing_work(self):
        policy = policy_at(Path(__file__).with_name('cold_start_policy.json'))
        self.assertEqual(policy['observations_per_backend'], 1)
        self.assertEqual(policy['backend_order'], ['cpu', 'fpga'])
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            (stage / 'manifest.json').write_text('{}')
            identity = sha(stage / 'manifest.json')
            benchmark = {'status': 'RUNNING', 'phase': 'all', 'stage_manifest_sha256': identity}
            (stage / 'benchmark_all.json').write_text(json.dumps(benchmark))
            with self.assertRaises(ValueError):
                completed_prerequisites(stage)
            benchmark['status'] = 'BENCHMARK_SELECTED_PHASES_EXACT_PASS'
            (stage / 'benchmark_all.json').write_text(json.dumps(benchmark))
            with self.assertRaises(FileNotFoundError):
                completed_prerequisites(stage)
            for backend in ('cpu', 'fpga'):
                result = {'status': 'RUNTIME_CORRECTNESS_PASS_NOT_PERFORMANCE_OR_M4_CLOSURE',
                          'boundary': 'EXACT_1024_PASS_OVERFLOW_REJECTED', 'backend': backend,
                          'stage_manifest_sha256': identity}
                (stage / f'runtime_{backend}_boundary.json').write_text(json.dumps(result))
            completed_prerequisites(stage)
            (stage / 'manifest.json').write_text('{"changed":true}')
            with self.assertRaises(ValueError):
                completed_prerequisites(stage)


if __name__ == '__main__':
    unittest.main()
