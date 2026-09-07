"""Negative evidence gates: exact outputs, timing, firmware, scope and cleanup."""
import copy
import json
import unittest

from scripts.audit_m5_tenth import ROOT, validate, statistics_for


class Evidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = json.loads((ROOT/'docs/m5_tenth_evidence.json').read_text())

    def test_complete_evidence(self):
        validate(self.evidence)

    def test_negative_gates(self):
        mutations = [
            lambda e: e['reports']['measurement']['runs'].pop(),
            lambda e: e['reports']['measurement']['runs'][2].update(logits_sha256='wrong'),
            lambda e: e['reports']['measurement']['runs'][2].update(kv_sha256='wrong'),
            lambda e: e['reports']['measurement']['runs'][2].update(token=0),
            lambda e: e['reports']['measurement']['runs'][2].update(firmware_sha256='wrong'),
            lambda e: e['reports']['measurement']['runs'][2].update(workspace_high_water=1),
            lambda e: e['reports']['measurement']['runs'][2].update(model_cycles=1),
            lambda e: e['reports']['measurement']['runs'][0].update(service_seconds=.01),
            lambda e: e['reports']['measurement']['runs'][0]['phases'][0].update(gemm_cycles=2**60),
            lambda e: e['reports']['measurement']['sha256'].update({'m5_pynq.bit': 'wrong'}),
            lambda e: e['reports']['measurement']['dma_after_return'].update(owner=1),
            lambda e: e['reports']['complete']['runs'][0].update(generated_tokens=[0, 0]),
            lambda e: e['reports']['complete']['runs'][0].update(work_high_water=1),
            lambda e: e['reports']['complete'].update(clock_hz=100000000),
            lambda e: e['reports']['complete']['boundary_rejection'].update(state=4),
            lambda e: e['reports']['campaign'].update(status='FAIL'),
            lambda e: e['reports']['release']['info_after_close_reopen'].update(pte_dma=1),
            lambda e: e['statistics']['final']['model_seconds'].update(mean=.1),
            lambda e: e['decisions'].update(round='REJECT'),
            lambda e: e['target'].update(tokens_per_second=0.09),
            lambda e: e['target'].update(achieved=False),
            lambda e: e['target'].update(boundary='model only'),
            lambda e: e['measured_configurations'].append('hidden'),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                changed = copy.deepcopy(self.evidence); mutate(changed)
                with self.assertRaises((ValueError, KeyError)):
                    validate(changed, check_files=False)
        changed = copy.deepcopy(self.evidence)
        changed['sources'].pop(next(iter(changed['sources'])))
        with self.assertRaises(ValueError): validate(changed)

    def test_consistent_but_below_target_is_not_achievement(self):
        changed = copy.deepcopy(self.evidence)
        for run in changed['reports']['measurement']['runs']:
            if run['role'].startswith('unprofiled_measured_'):
                run['host_request_through_delivery_seconds'] += 0.1
        changed['statistics']['final'] = statistics_for(changed['reports']['measurement'])
        changed['target']['achieved'] = False
        with self.assertRaisesRegex(ValueError, 'target not attained'):
            validate(changed, check_files=False)


if __name__ == '__main__':
    unittest.main()
