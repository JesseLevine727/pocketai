"""Decode evidence regressions runnable before full-request closure."""
import copy
import json
import unittest

from scripts.audit_m5_iterate import ROOT, FINAL, VARIANTS, validate_decode


class Decode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads((ROOT/'tests/m5_iterate/performance_policy.json').read_text())
        cls.seed = json.loads((ROOT/'build/m5_opt_seed_v1/manifest.json').read_text())
        cls.report = json.loads((ROOT/FINAL/'measurement.json').read_text())

    def test_all_original_passed_diagnostics(self):
        for name, directory in VARIANTS.items():
            with self.subTest(cycle=name):
                validate_decode(json.loads((ROOT/directory/'diagnostic.json').read_text()),
                                directory, self.policy, self.seed)
        validate_decode(self.report, FINAL, self.policy, self.seed, measured=True)

    def test_missing_samples_changed_hashes_and_clock_accounting_rejected(self):
        mutations = [lambda r: r['runs'].pop(),
                     lambda r: r['sha256'].__setitem__('m5_pynq.bit', 'wrong'),
                     lambda r: r['runs'][2].update(token=0),
                     lambda r: r['runs'][2].update(logits_sha256='wrong'),
                     lambda r: r['runs'][2].update(kv_sha256='wrong'),
                     lambda r: r['runs'][0].update(service_seconds=.01),
                     lambda r: r['runs'][0]['phases'][0].update(gemm_cycles=2**60),
                     lambda r: r['runs'][2].update(model_cycles=1),
                     lambda r: r['runs'][2].update(profile_enabled=True),
                     lambda r: r['runs'][2].update(jobs=0),
                     lambda r: r['runs'][2].update(workspace_high_water=0),
                     lambda r: r['dma_after_return'].update(owner=1)]
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                candidate = copy.deepcopy(self.report)
                mutate(candidate)
                with self.assertRaises(ValueError):
                    validate_decode(candidate, FINAL, self.policy, self.seed, measured=True)


if __name__ == '__main__':
    unittest.main()
