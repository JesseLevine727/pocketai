"""Counter parsing rejects missing coverage and impossible nested timings."""
import importlib
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'zynq'))
runner = importlib.import_module('m5_startup_run')


class Measurement(unittest.TestCase):
    def setUp(self):
        self.trace = bytearray(0x2b040)
        struct.pack_into('<4I', self.trace, 0x2a000, 0x37545350, 1, 14, 0)
        self.record(0, 100, 144)
        for index in range(1, 5): self.record(index, 10, 144)
        self.record(13, 120, 12)
        words = [0x36585443, 1, 9]
        for i in range(9): words += [12 if i == 0 else 144*8, 100, 0]
        struct.pack_into('<30I', self.trace, 0x28000, *words)
        self.phases = [dict(name='attention', cycles=1000)]

    def record(self, index, cycles, calls, reserved=0):
        struct.pack_into('<QII', self.trace, 0x2a010+index*16, cycles, calls, reserved)

    def call(self): return runner.details(self.trace, 8, self.phases)

    def test_complete_prepare_coverage(self):
        result = self.call()
        self.assertEqual(result['startup_detail'][-1]['name'], 'complete_cache_preparation')
        self.assertEqual(result['attention_unassigned_cycles'], 100)

    def test_old_thirteen_counter_evidence_remains_readable(self):
        struct.pack_into('<I', self.trace, 0x2a008, 13)
        self.assertEqual(len(self.call()['startup_detail']), 13)

    def test_rejects_header(self):
        for offset, value in ((0x2a000, 1), (0x2a004, 2), (0x2a008, 12), (0x2a00c, 1)):
            with self.subTest(offset=offset):
                before = bytes(self.trace); struct.pack_into('<I', self.trace, offset, value)
                with self.assertRaises(ValueError): self.call()
                self.trace[:] = before

    def test_rejects_reserved_record(self):
        self.record(1, 10, 144, 1)
        with self.assertRaises(ValueError): self.call()

    def test_rejects_cycles_without_calls(self):
        self.record(1, 10, 0)
        with self.assertRaises(ValueError): self.call()

    def test_rejects_subintervals_exceeding_heads(self):
        self.record(1, 101, 144)
        with self.assertRaises(ValueError): self.call()

    def test_rejects_heads_exceeding_complete_prepare(self):
        self.record(13, 99, 12)
        with self.assertRaises(ValueError): self.call()

    def test_rejects_missing_layer_coverage(self):
        self.record(13, 120, 11)
        with self.assertRaises(ValueError): self.call()

    def test_rejects_missing_attention_rows(self):
        struct.pack_into('<I', self.trace, 0x28000+6*4, 144)
        with self.assertRaises(ValueError): self.call()

    def test_rejects_attention_exceeding_phase(self):
        self.phases[0]['cycles'] = 899
        with self.assertRaises(ValueError): self.call()

    def lazy(self):
        struct.pack_into('<I', self.trace, 0x2a008, 16)
        self.record(14, 20, 144); self.record(15, 30, 144*8)

    def test_lazy_initialization_includes_first_demand(self):
        self.lazy()
        self.assertAlmostEqual(self.call()['initial_required_derived_seconds'], 140/runner.m.FABRIC_HZ)

    def test_lazy_warm_has_no_initial_demand(self):
        self.lazy(); self.record(14, 0, 0)
        self.assertAlmostEqual(self.call()['initial_required_derived_seconds'], 120/runner.m.FABRIC_HZ)

    def test_rejects_bad_lazy_coverage(self):
        self.lazy()
        before = bytes(self.trace)
        for index, cycles, calls in ((14, 31, 144), (14, 20, 143), (15, 30, 144)):
            self.trace[:] = before; self.record(index, cycles, calls)
            with self.assertRaises(ValueError): self.call()

    def test_first_use_coverage_matches_actual_request(self):
        self.lazy()
        result = self.call(); result['derived_cache'] = dict(version=2)
        for role in ('cold_initialization_in_model', 'actual_prompt_prefill'):
            runner.check_initial_coverage(result, role, 8)
        with self.assertRaises(ValueError): runner.check_initial_coverage(result, 'warm_last_slot', 8)
        result['startup_detail'][0]['calls'] = 0
        result['startup_detail'][14]['calls'] = 0
        runner.check_initial_coverage(result, 'warm_last_slot', 8)
        with self.assertRaises(ValueError): runner.check_initial_coverage(result, 'cold_initialization_in_model', 8)
        with self.assertRaises(ValueError): runner.check_initial_coverage(result, 'warm_last_slot', 1)

    def leaf(self):
        struct.pack_into('<4I', self.trace, 0x2b000, 0x3746504c, 1, 2, 0)
        for worker in range(2):
            struct.pack_into('<QQII', self.trace, 0x2b010+worker*24, 700, 100, 385, 0)

    def test_leaf_ipc_is_separate_from_wall_timing(self):
        self.leaf()
        parsed = self.call()
        self.assertEqual(parsed['projection_leaf_diagnostic'][1]['cycles_per_instruction'], 7)
        self.assertEqual(parsed['attention_unassigned_cycles'], 100)

    def test_rejects_leaf_header_and_coverage(self):
        self.leaf(); before = bytes(self.trace)
        for offset, fmt, value in ((0x2b004, '<I', 2), (0x2b008, '<I', 3),
                (0x2b00c, '<I', 1), (0x2b018, '<Q', 0),
                (0x2b020, '<I', 0), (0x2b024, '<I', 1)):
            self.trace[:] = before; struct.pack_into(fmt, self.trace, offset, value)
            with self.assertRaises(ValueError): self.call()


if __name__ == '__main__': unittest.main()
