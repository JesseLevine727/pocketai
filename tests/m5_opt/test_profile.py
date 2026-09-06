import unittest

from zynq.m5_opt_profile import parse_profile, PROFILE_MAGIC, LOGITS_OFFSET, RECORD_OFFSET, RECORD


class ProfileTests(unittest.TestCase):
    def fixture(self, enabled=True):
        order = [(1, 0)] + [(kind, layer) for layer in range(12) for kind in range(2, 10)]
        order += [(10, 0), (11, 0), (12, 0)]
        raw = b''.join(RECORD.pack(kind, layer, 100, 30, 10, 5, 1, 2, 3, 0)
                       for kind, layer in order) if enabled else b''
        count = len(order) if enabled else 0
        header = [PROFILE_MAGIC, 1, LOGITS_OFFSET, 50257, 0, count, RECORD_OFFSET, RECORD.size]
        header += [5, 0, 10010, 0, count, count*2, count*3, 100]
        header += [count*30, 0, count*10, 0, count*5, 0, count*15]
        header += [0] * (64 - len(header))
        return header, raw

    def test_nested_accounting(self):
        h, raw = self.fixture()
        result = parse_profile(tuple(h), raw, True, 100)
        self.assertEqual(len(result['phases']), 100)
        self.assertEqual(result['service_seconds'], 30)
        self.assertEqual(result['cpu_remainder_seconds'], 70.05)
        self.assertEqual(result['unassigned_profile_tail_cycles'], 5)

    def test_disabled_has_no_fake_profile(self):
        h, raw = self.fixture(False)
        self.assertIsNone(parse_profile(tuple(h), raw, False, 100)['service_seconds'])

    def test_missing_phase_rejected(self):
        h, raw = self.fixture()
        h[5] -= 1
        with self.assertRaisesRegex(ValueError, 'coverage'):
            parse_profile(tuple(h), raw[:-RECORD.size], True, 100)

    def test_nested_compute_cannot_exceed_service(self):
        h, raw = self.fixture()
        bad = RECORD.pack(1, 0, 100, 30, 31, 0, 1, 2, 3, 0)
        with self.assertRaisesRegex(ValueError, 'nested'):
            parse_profile(tuple(h), bad + raw[RECORD.size:], True, 100)

    def test_wrapped_clock_high_word(self):
        h, raw = self.fixture(False)
        h[8], h[9], h[10], h[11] = 0xfffffffe, 5, 100, 6
        self.assertEqual(parse_profile(tuple(h), raw, False, 100)['model_cycles'], 102)


if __name__ == '__main__':
    unittest.main()
