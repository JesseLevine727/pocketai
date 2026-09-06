"""Positive and mutation tests of the completed local optimization evidence."""
import copy
import json
import unittest
from scripts.audit_m5_opt import ROOT, validate


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = json.loads((ROOT/'docs/m5_opt_evidence.json').read_text())

    def test_qualified(self):
        validate(self.evidence)

    def test_rejects_mutated_gates(self):
        mutations = [
            lambda e: e.update(status='FAIL'),
            lambda e: e['sources'].update({'runtime/m5_opt/pa_m5_metadata_opt.c': '0'*64}),
            lambda e: e['decode']['reuse']['runs'].pop(),
            lambda e: e['decode']['reuse']['runs'][1].update(token=0),
            lambda e: e['decode']['reuse']['runs'][0]['phases'][0].update(service_cycles=2**63),
            lambda e: e['decode']['reuse']['dma_after_return'].update(owner=1),
            lambda e: e['statistics']['reuse']['model_seconds'].update(mean=1.),
            lambda e: e['complete']['runs'][0].update(generated_tokens=[0, 0]),
            lambda e: e['complete']['runs'][0].update(traces=[]),
            lambda e: e['complete']['boundary_rejection'].update(output_sentinel_unchanged=False),
            lambda e: e['release']['info_after_close_reopen'].update(allocated_pages=1),
            lambda e: e['precision'].update(status='SCREEN_PASS_NOT_QUALIFIED'),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                candidate = copy.deepcopy(self.evidence)
                mutate(candidate)
                with self.assertRaises(ValueError):
                    validate(candidate)


if __name__ == '__main__':
    unittest.main()
