"""Negative closure tests validate gates, not merely the report's PASS label."""
import copy
import json
import unittest

from scripts.audit_m5_fast import ROOT, validate


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = json.loads((ROOT/'docs/m5_fast_evidence.json').read_text())

    def test_qualified_evidence(self):
        validate(self.evidence)

    def test_reject_changed_gate_or_physical_result(self):
        mutations = [
            lambda e: e.update(status='ACTIVE'),
            lambda e: e['gates'].update(F5='PENDING'),
            lambda e: e['hardware'].update(wns=.184),
            lambda e: e['hardware'].update(dsp=1),
            lambda e: e['policy']['hardware'].update(slow_multiplier_fallback_allowed=True),
            lambda e: e['reports']['fast_only']['sha256'].__setitem__('m5_profile.bin', 'wrong'),
            lambda e: e['reports']['fast_only']['runs'].pop(),
            lambda e: e['reports']['requant']['runs'][2].update(token=0),
            lambda e: e['reports']['requant']['runs'][2].update(logits_sha256='wrong'),
            lambda e: e['reports']['requant']['runs'][2].update(kv_sha256='wrong'),
            lambda e: e['reports']['requant']['runs'][2].update(profile_enabled=True),
            lambda e: e['reports']['requant']['runs'][0].update(jobs=9652),
            lambda e: e['reports']['requant']['runs'][0]['phases'][0].update(service_cycles=2**63),
            lambda e: e['reports']['fine_final']['runs'][0]['fine'].pop(),
            lambda e: e['statistics']['requant']['model_seconds'].update(mean=1),
            lambda e: e['reports']['complete'].update(allocated_bytes=1024),
            lambda e: e['reports']['complete']['runs'][0].update(traces=[]),
            lambda e: e['reports']['complete']['runs'][0].update(generated_tokens=[257]),
            lambda e: e['reports']['complete']['boundary_rejection'].update(output_sentinel_unchanged=False),
            lambda e: e['reports']['complete']['dma'].update(owner=1),
            lambda e: e['reports']['release']['info_after_close_reopen'].update(allocated_pages=1),
            lambda e: e['reports']['campaign'].update(elapsed_seconds=1201),
            lambda e: e['reports']['requant_probe']['records'][1].update(checksum=0),
            lambda e: e['decisions'].update(requant8='UNTESTED'),
        ]
        for ordinal, mutate in enumerate(mutations):
            with self.subTest(mutation=ordinal):
                evidence = copy.deepcopy(self.evidence)
                mutate(evidence)
                with self.assertRaises((ValueError, KeyError)):
                    validate(evidence, check_files=False)

    def test_missing_source_pin_rejected(self):
        evidence = copy.deepcopy(self.evidence)
        del evidence['sources']['rtl/m5_fast/pipelined_kernel.sv.inc']
        with self.assertRaisesRegex(ValueError, 'manifest'):
            validate(evidence)


if __name__ == '__main__':
    unittest.main()
