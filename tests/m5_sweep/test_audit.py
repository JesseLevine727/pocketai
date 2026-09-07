"""Negative evidence tests; require the collected sweep, never access the board."""
import copy
import json
from pathlib import Path
import unittest

from scripts.audit_m5_sweep import validate
from scripts.analyze_m5_sweep import summarize


class Evidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path('docs/m5_sweep_evidence.json')
        if not path.exists():
            raise unittest.SkipTest('collect board evidence before negative audit tests')
        cls.evidence = json.loads(path.read_text())

    def rejected(self, change):
        evidence = copy.deepcopy(self.evidence)
        change(evidence)
        with self.assertRaises((ValueError, KeyError)):
            validate(evidence, files=False)

    def test_accepts_unmodified_evidence(self):
        validate(self.evidence, files=False)

    def test_rejects_over_budget(self):
        self.rejected(lambda e: e['campaign'].update(elapsed_seconds=3601))

    def test_rejects_missing_sample(self):
        self.rejected(lambda e: e['campaign']['trials'].pop())

    def test_rejects_failed_sample(self):
        self.rejected(lambda e: e['campaign']['trials'][0].update(status='FAIL'))

    def test_rejects_wrong_token(self):
        self.rejected(lambda e: e['campaign']['trials'][0]['result']['generated_tokens'].__setitem__(0, 0))

    def test_rejects_wrong_all_logits(self):
        self.rejected(lambda e: e['campaign']['trials'][0]['result'].update(logits_sha256='0'*64))

    def test_rejects_wrong_complete_kv(self):
        self.rejected(lambda e: e['campaign']['trials'][0]['result'].update(kv_sha256='0'*64))

    def test_rejects_retained_dma(self):
        self.rejected(lambda e: e['campaign']['info_after_close_reopen'].update(pte_dma=4096))

    def test_rejects_no_normal_unload(self):
        self.rejected(lambda e: e['campaign'].update(normal_unload=False))

    def test_rejects_changed_binary(self):
        self.rejected(lambda e: e['campaign']['sha256'].update({'m5_runtime.bin': '0'*64}))

    def test_rejects_inadmissible_case(self):
        self.rejected(lambda e: e['campaign']['trials'][0].update(started_campaign_seconds=3500))

    def test_rejects_falsified_statistics(self):
        self.rejected(lambda e: e['summary'].update(full_request_aggregate_tokens_per_second=1.0))

    def test_rejects_profile_double_counting(self):
        def change(e):
            r = next(i['result'] for i in e['campaign']['trials'] if i['trial'].get('profile'))
            r['phases'][0]['service_cycles'] = r['phases'][0]['cycles']+1
        self.rejected(change)

    def test_slowest_sample_contributes_to_summary(self):
        evidence = copy.deepcopy(self.evidence)
        case = next(i for i in evidence['campaign']['trials']
                    if i['trial']['kind'] == 'cached' and i['trial']['past'] == 13 and not i['trial']['profile'])
        case['result']['host_request_through_delivery_seconds'] = 100
        summary = summarize(evidence['campaign'])
        self.assertEqual(summary['groups']['cached:p13:plain']['delivered_seconds']['max'], 100)
        self.assertEqual(summary['groups']['cached:p13:plain']['delivered_seconds']['n'], 3)


if __name__ == '__main__':
    unittest.main()
