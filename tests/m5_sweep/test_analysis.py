"""Test timing boundaries and lossless accounting without hardware or fixtures."""
import unittest
from scripts.analyze_m5_sweep import summarize, csv_text, stats


def full(name, delivered, count, continuation):
    return dict(trial=dict(id=name, kind='full', case='story', new_tokens=count, role='test'),
                status='PASS', case_elapsed_seconds=delivered+2, bound_exceeded=False,
                result=dict(generated_tokens=list(range(count)), prompt_tokens=[1]*13,
                    firmware_seconds=delivered-1, request_through_delivery_seconds=delivered,
                    ttft_seconds=delivered-1-sum(continuation), prefill_forward_seconds=10,
                    decode_seconds=continuation, work_high_water=100, tensor_bytes_read=1000,
                    tensor_bytes_written=500, transfers=20))


class Analysis(unittest.TestCase):
    def test_distinct_boundaries_and_weighted_rate(self):
        campaign = dict(clock_hz=91000000, provision_seconds=20, elapsed_seconds=200,
                        trials=[full('a', 20, 4, [2, 3, 4]), full('b', 40, 4, [3, 4, 5])])
        report = summarize(campaign)
        self.assertEqual(report['full_request_aggregate_tokens_per_second'], 8/60)
        self.assertEqual(report['fully_charged_campaign_full_tokens_per_second'], 8/200)
        self.assertEqual(report['groups']['full:story:g4']['aggregate_delivered_tokens_per_second'], 8/60)
        self.assertEqual(report['rows'][0]['continuation_tokens_per_second'], 3/9)
        self.assertEqual(report['rows'][0]['model_first_token_seconds'], 10)
        self.assertEqual(report['rows'][0]['prefill_tokens_per_second'], 13/10)

    def test_failure_and_skip_are_not_discarded(self):
        campaign = dict(clock_hz=91000000, provision_seconds=20, elapsed_seconds=200,
                        trials=[dict(trial=dict(id='failure', kind='full', role='test'),
                                     status='FAIL', error='watchdog', case_elapsed_seconds=100,
                                     bound_exceeded=True),
                                dict(trial=dict(id='skipped', kind='cached', role='test'),
                                     status='SKIP', reason='budget')])
        report = summarize(campaign)
        self.assertIsNone(report['full_request_aggregate_tokens_per_second'])
        self.assertEqual(report['fail_count'], 1)
        self.assertEqual(report['skip_count'], 1)
        self.assertEqual(report['pass_count'], 0)
        self.assertIn('watchdog', csv_text(report))
        self.assertIn('100', csv_text(report))

    def test_single_sample_is_descriptive_not_confidence_interval(self):
        self.assertEqual(stats([3]), dict(n=1, mean=3, median=3, min=3, max=3, population_stddev=0))


if __name__ == '__main__':
    unittest.main()
