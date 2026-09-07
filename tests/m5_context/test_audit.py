"""Reject misleading throughput, hidden cache reuse and failed safety gates."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from scripts.audit_m5_context import validate


class Evidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = json.loads(Path('docs/m5_context_evidence.json').read_text())

    def test_accepts_closed_evidence(self): validate(self.evidence, files=False)

    def test_rejects_gate_mutations(self):
        changes = (
            lambda e: e.update(m6_started=True),
            lambda e: e['reports']['final_story']['trials'].pop(),
            lambda e: e['reports']['final_story'].update(normal_unload=False),
            lambda e: e['reports']['final_science']['info_after_close_reopen'].update(allocated_pages=1),
            lambda e: e['reports']['final_story']['trials'][1].update(status='FAIL'),
            lambda e: e['reports']['final_story']['trials'][1]['result'].update(host_request_through_delivery_seconds=10.001),
            lambda e: e['reports']['final_story']['trials'][1]['result'].update(logits_sha256='wrong'),
            lambda e: e['reports']['final_story']['trials'][1]['result'].update(kv_sha256='wrong'),
            lambda e: e['reports']['final_story']['trials'][1]['result'].update(token=0),
            lambda e: e['reports']['final_story']['trials'][1]['result']['derived_cache'].update(appended_vectors=432),
            lambda e: [i['result'].pop('derived_cache', None) for i in e['reports']['final_story']['trials']],
            lambda e: e['references']['final_story']['seeds']['1023'].update(input_token=0),
            lambda e: e['reports']['final_story'].update(elapsed_seconds=3601),
            lambda e: e['summary']['final_story']['warm_delivered'].update(mean=1),
            lambda e: e['reports']['direct']['trials'][1]['result']['attention_detail'][0].update(seconds=0),
            lambda e: e['reports']['final_story']['boundary_rejection'].update(output_sentinel_unchanged=False),
            lambda e: e['reports']['final_science']['trials'][1]['result'].update(profile_enabled=True),
            lambda e: e['reports']['final_science']['trials'][1]['result'].update(matched_original_baseline=True),
        )
        for change in changes:
            evidence = deepcopy(self.evidence); change(evidence)
            with self.assertRaises((ValueError, KeyError)): validate(evidence, files=False)


if __name__ == '__main__': unittest.main()
