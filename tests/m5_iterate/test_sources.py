"""Fail-closed source derivation and the WFI timing regression at its call site."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import m5_iterate_sources as sources


class Derivation(unittest.TestCase):
    def test_original_snapshots_reproduce(self):
        for variant, directory in (('cycle1', 'build/m5_iterate_c1_v1'),
                                   ('cycle2', 'build/m5_iterate_c2_v1'),
                                   ('cycle2_hart1', 'build/m5_iterate_c2_hart1_v1'),
                                   ('cycle3', 'build/m5_iterate_c3_v1')):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary)/'generated'
                sources.generate(target, variant)
                for name in ('ops.c', 'numerics.c', 'profile.c', 'hardware.c'):
                    self.assertEqual((target/name).read_bytes(),
                                     (sources.ROOT/directory/'generated'/name).read_bytes())

    def test_changed_baseline_pin_rejected(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(sources, 'BASE_GENERATOR', '0'*64):
            with self.assertRaises(RuntimeError):
                sources.generate(Path(temporary)/'generated', 'cycle1')

    def test_changed_generated_pin_rejected(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(sources, 'BASE_OPS', '0'*64):
            with self.assertRaises(RuntimeError):
                sources.generate(Path(temporary)/'generated', 'cycle1')

    def test_unknown_variant_and_existing_target_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)/'generated'
            with self.assertRaises(ValueError): sources.generate(target, 'wrong')
            with self.assertRaises(FileExistsError): sources.generate(target, 'cycle1')

    def test_ambiguous_marker_refused(self):
        for source in ('abcabc', 'xyz'):
            with self.assertRaises(ValueError): sources.once(source, 'abc', 'def')

    def test_only_hart1_may_sleep_during_model(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)/'generated'
            sources.generate(target, 'cycle2_hart1')
            hardware = (target/'hardware.c').read_text()
            self.assertIn('while (!(REG(PA_M5_MBOX, 8) & 2u)) __asm__ volatile("nop");', hardware)
            self.assertNotIn('pa_iter_wait_mailbox(2)', hardware)
            self.assertEqual(hardware.count('pa_iter_wait_mailbox(1)'), 1)
            # Function definition plus the service-hart entry, never prepare_hart0.
            self.assertEqual(hardware.count('pa_iter_enable_mailbox_wait();'), 1)
            self.assertIn('csrc mstatus', hardware)
            self.assertNotIn('csrs mstatus', hardware)
            self.assertIn('"r"(2048u)', hardware)

    def test_release_rejects_unretained_wait_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)/'generated'
            sources.generate(target, 'cycle3')
            self.assertEqual((target/'hardware.c').read_bytes(),
                             (sources.ROOT/'runtime/m5/pa_m5_hw.c').read_bytes())
            self.assertIn('pa_iter_range_max', (target/'ops.c').read_text())


if __name__ == '__main__':
    unittest.main()
