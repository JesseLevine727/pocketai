"""Reject dishonest boundaries, incomplete checks, and pooled performance misses."""
from copy import deepcopy
import unittest

from scripts.audit_m5_startup import read, validate_campaign, validate_final, validate_references, hardware_from_reports


class Integrity(unittest.TestCase):
    def setUp(self):
        stage = 'build/m5_startup_split_fixed_diag_v1/'
        self.report = read(stage+'campaign.json')
        self.refs = read(stage+'references/manifest.json')

    def test_retained_actual_campaign(self):
        validate_campaign(self.report, self.refs)

    def test_oracles_cannot_be_replaced_to_match_a_bad_result(self):
        validate_references(self.refs)
        for section in ('seed', 'full', 'prefill'):
            refs = deepcopy(self.refs)
            if section == 'seed': refs['seeds']['1022']['expected']['token'] += 1
            elif section == 'full': refs['cases']['science']['steps'][0]['logits_sha256'] = 'changed'
            else: refs['seeds']['0']['prefill_tokens'] = [1]
            with self.subTest(section=section), self.assertRaises((ValueError, RuntimeError, AssertionError)):
                validate_references(refs)

    def test_positive_setup_slack_below_margin_is_still_rejected(self):
        # Actual retained +0.149-ns implementation: meeting zero slack alone
        # does not satisfy this goal's explicitly retained +0.250-ns margin.
        with self.assertRaisesRegex((ValueError, RuntimeError, AssertionError), 'hardware timing/resource gate'):
            hardware_from_reports('build/m5_startup_fetch_polish_v1', reset_count=6)

    def test_new_async_bram_control_findings_are_not_waived(self):
        with self.assertRaisesRegex((ValueError, RuntimeError, AssertionError), 'unreviewed DRC/methodology finding'):
            hardware_from_reports('build/m5_startup_fetch_prefetch_pynq_v1', reset_count=8)

    def test_extra_data_bank_must_be_physically_proven(self):
        old = 'build/m5_startup_fetch_sync_pynq_v2'
        self.assertEqual(hardware_from_reports(old, reset_count=7)['bram36'], 111.5)
        with self.assertRaisesRegex((ValueError, RuntimeError, AssertionError), 'hardware timing/resource gate'):
            hardware_from_reports(old, reset_count=7, data_read_mirror=True)

    def test_negative_boundaries(self):
        mutations = [
            lambda d: d.update(normal_unload=False),
            lambda d: d['info_after_close_reopen'].update(allocated_pages=1),
            lambda d: d['boundary_rejection'].update(output_sentinel_unchanged=False),
            lambda d: d.update(elapsed_seconds=3601),
            lambda d: d['trials'].pop(),
            lambda d: d['trials'][0]['result'].update(logits_sha256='changed'),
            lambda d: d['trials'][0]['result'].update(kv_sha256='changed'),
            lambda d: d['trials'][0]['result'].update(initial_required_derived_seconds=0.0),
            lambda d: d['trials'][0]['result']['startup_detail'][14].update(calls=0),
            lambda d: d['trials'][1]['result']['derived_cache'].update(appended_vectors=144),
            lambda d: d['trials'][2]['result'].update(input_tokens=[1]),
            lambda d: d['trials'][4]['result'].update(prompt_tokens=[1]),
            lambda d: d['trials'][4]['result'].update(execution_image='m5_trace.bin'),
            lambda d: d['trials'][3]['result']['traces'].pop(),
        ]
        for mutate in mutations:
            d = deepcopy(self.report); mutate(d)
            with self.subTest(mutate=mutate), self.assertRaises((ValueError, RuntimeError, AssertionError)):
                validate_campaign(d, self.refs)

    def final_fixture(self):
        # Synthetic passing timings test the validator only. Never measured or
        # stored as physical evidence. Exactness is independently tested above.
        p = self.report['policy']['pinned']
        binaries = {n: p[n] for n in ('m5_runtime.bin', 'm5_profile.bin', 'm5_trace.bin')}
        binaries['m5_detail.bin'] = p['m5_profile.bin']
        overlay = {n: p[n] for n in ('m5_pynq.bit', 'm5_pynq.hwh')}
        report = deepcopy(self.report)
        report['trials'] = [deepcopy(x) for _ in range(3) for x in report['trials']]
        for x in report['trials']:
            if x['trial']['kind'] == 'cached':
                x['trial']['profile'] = False
                x['result']['host_request_through_delivery_seconds'] = 9.5
            else:
                x['result']['request_through_delivery_seconds'] = 9.5*x['trial']['new_tokens']
        reports = {'final_story': deepcopy(report), 'final_science': deepcopy(report),
                   'diagnostic_story': deepcopy(self.report), 'diagnostic_science': deepcopy(self.report)}
        refs = {k: dict(case=k.split('_')[-1]) for k in reports}
        return reports, refs, {k: k for k in reports}, binaries, overlay

    def test_synthetic_final_and_no_average_waiver(self):
        args = self.final_fixture(); validate_final(*args)
        reports = args[0]
        original = deepcopy(reports)
        mutations = [
            lambda: reports['final_story']['trials'][5]['result'].update(request_through_delivery_seconds=10.001),
            lambda: reports['final_science']['trials'][1]['result'].update(host_request_through_delivery_seconds=10.001),
            lambda: reports['final_story']['trials'][0]['result'].update(host_request_through_delivery_seconds=20.001),
            lambda: reports['diagnostic_science']['trials'][0]['result'].update(initial_required_derived_seconds=10.001),
            lambda: reports['final_science']['trials'][1]['trial'].update(profile=True),
            lambda: reports['final_story']['policy']['pinned'].update({'m5_pynq.bit': 'changed'}),
        ]
        for mutate in mutations:
            reports.clear(); reports.update(deepcopy(original)); mutate()
            with self.subTest(mutate=mutate), self.assertRaises((ValueError, RuntimeError, AssertionError)):
                validate_final(*args)


if __name__ == '__main__': unittest.main()
