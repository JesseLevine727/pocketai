"""Reject hidden/future cache preparation and retain safe frozen ownership paths."""
import importlib
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'zynq'))
runner = importlib.import_module('m5_context_ready_run')


class Campaign(unittest.TestCase):
    def setUp(self):
        runner.previous = None
        self.arena = SimpleNamespace(maps={'trace': bytearray(8*1024*1024)})
        self.seed = dict(context_role='warm_last_slot', past=1023, input_token=7, prefill_kv_sha256='expected')
        self.previous = dict(cache_valid=1023, token=7, kv_sha256='expected')
        struct.pack_into('<144I', self.arena.maps['trace'], 0x60008, *((1023,)*144))

    def call(self): runner.restore_or_continue(self.arena, Path('.'), self.seed)

    def test_warm_requires_real_previous_forward(self):
        with self.assertRaises(ValueError): self.call()

    def test_warm_rejects_wrong_previous_token(self):
        runner.previous = dict(self.previous, token=8)
        with self.assertRaises(ValueError): self.call()

    def test_warm_rechecks_entire_prefix(self):
        runner.previous = self.previous
        with patch.object(runner.profiler.m, 'cache_digest', return_value='changed'):
            with self.assertRaises(ValueError): self.call()

    def test_warm_rejects_future_derived_cache(self):
        runner.previous = self.previous
        struct.pack_into('<I', self.arena.maps['trace'], 0x60008, 1024)
        with patch.object(runner.profiler.m, 'cache_digest', return_value='expected'):
            with self.assertRaises(ValueError): self.call()

    def test_warm_does_not_restore_or_prepare(self):
        runner.previous = self.previous
        before = bytes(self.arena.maps['trace'])
        with patch.object(runner.profiler.m, 'cache_digest', return_value='expected'), patch.object(runner, 'restore') as restore:
            self.call(); restore.assert_not_called()
        self.assertEqual(before, bytes(self.arena.maps['trace']))

    def test_cold_only_invalidates_marker(self):
        self.seed['context_role'] = 'cold_initialization_in_model'
        self.arena.maps['trace'][0x60000:0x60008] = b'12345678'
        expected = bytearray(self.arena.maps['trace']); expected[0x60000:0x60008] = bytes(8)
        with patch.object(runner, 'restore') as restore:
            self.call(); restore.assert_called_once()
        self.assertEqual(expected, self.arena.maps['trace'])

    def test_original_baseline_still_checks_full_kv(self):
        self.seed['context_baseline'] = True
        runner.previous = self.previous
        with patch.object(runner.profiler.m, 'cache_digest', return_value='changed'):
            with self.assertRaises(ValueError): self.call()

    def test_original_baseline_never_uses_detail_instrumentation(self):
        self.seed['context_baseline'] = True
        with self.assertRaises(ValueError):
            runner.ready_run(self.arena, None, None, self.seed, True)


if __name__ == '__main__': unittest.main()
