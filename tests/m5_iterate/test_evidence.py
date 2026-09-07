"""Gate-negative checks: exactness, all samples, truthful clocks, lifecycle."""
import copy
import json
import unittest

from scripts.audit_m5_iterate import ROOT, validate
from scripts.collect_m5_iterate_evidence import collect


class Evidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT/'docs/m5_iterate_evidence.json'
        cls.evidence = json.loads(path.read_text()) if path.exists() else collect()

    def test_qualified(self):
        validate(self.evidence)

    def test_negative_gates(self):
        mutations = [
            lambda e: e.update(status='ACTIVE'),
            lambda e: e['gates'].update(cycle3='PENDING'),
            lambda e: e['policy'].update(cycles=2),
            lambda e: e['hardware'].update(wns=.184),
            lambda e: e['hardware'].update(dsp=1),
            lambda e: e['reports']['cycle1']['sha256'].update(m5_profile_bin='wrong'),
            lambda e: e['reports']['cycle2']['runs'][1].update(token=0),
            lambda e: e['reports']['cycle3']['runs'][1].update(logits_sha256='wrong'),
            lambda e: e['reports']['cycle3']['runs'][1].update(kv_sha256='wrong'),
            lambda e: e['reports']['measurement']['runs'].pop(),
            lambda e: e['reports']['measurement']['runs'][2].update(profile_enabled=True),
            lambda e: e['reports']['measurement']['runs'][2].update(model_seconds=.1),
            lambda e: e['reports']['measurement']['runs'][0].update(service_seconds=0),
            lambda e: e['reports']['measurement']['runs'][0]['phases'][0].update(service_cycles=2**63),
            lambda e: e['reports']['measurement']['runs'][0].update(mover_input_bytes=0),
            lambda e: e['reports']['rejected_clock'].update(status='PASS'),
            lambda e: e['statistics']['final']['model_seconds'].update(mean=1),
            lambda e: e['reports']['complete'].update(allocated_bytes=1024),
            lambda e: e['reports']['complete']['runs'][0].update(traces=[]),
            lambda e: e['reports']['complete']['runs'][0].update(generated_tokens=[257]),
            lambda e: e['reports']['complete']['boundary_rejection'].update(output_sentinel_unchanged=False),
            lambda e: e['reports']['complete']['dma'].update(owner=1),
            lambda e: e['reports']['campaign'].update(elapsed_seconds=1201),
            lambda e: e['reports']['release']['info_after_close_reopen'].update(allocated_pages=1),
            lambda e: e['reports']['release']['info_after_close_reopen'].update(pte_dma=1),
            lambda e: e['decisions'].update(cycle2_hart1_sleep='RETAIN'),
        ]
        for ordinal, mutate in enumerate(mutations):
            with self.subTest(mutation=ordinal):
                candidate = copy.deepcopy(self.evidence)
                mutate(candidate)
                with self.assertRaises((ValueError, KeyError)):
                    validate(candidate, check_files=False)

    def test_missing_source_pin(self):
        candidate = copy.deepcopy(self.evidence)
        del candidate['sources']['runtime/m5_iterate/project_range.c.inc']
        with self.assertRaisesRegex(ValueError, 'manifest'):
            validate(candidate)

    def test_changed_original_report(self):
        candidate = copy.deepcopy(self.evidence)
        candidate['reports']['cycle1']['memory_before']['MemFree'] += 1
        with self.assertRaisesRegex(ValueError, 'embedded'):
            validate(candidate)


if __name__ == '__main__':
    unittest.main()
