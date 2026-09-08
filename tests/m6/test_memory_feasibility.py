import unittest

from scripts.m6_memory_feasibility import groups, inspect_liberty, screen, values


class LibertyScreenTest(unittest.TestCase):
    def test_balanced_groups_and_quoted_braces(self):
        text = 'timing () { comment : "}"; x() {a: 1;} } timing () {a: 2;}'
        self.assertEqual(len(list(groups(text, "timing"))), 2)

    def test_values_ignore_index_and_accept_negative_exponent(self):
        body = 'rise_constraint(t) {index_1("99,100"); values("-0.25, 2e-3", "1.5,0");}'
        self.assertEqual(values(body, ("rise_constraint",)),
                         {"min": -0.25, "max": 1.5, "entries": 4})

    def test_missing_or_wrong_units_fail_closed(self):
        for text in ('time_unit: "1ps";', 'time_unit: "1ns";'):
            with self.assertRaises(ValueError):
                inspect_liberty(text)

    def test_period_screen_is_not_full_timing_pass(self):
        libs = {"ss": {"minimum_period": {"max": 5.51622}},
                "tt": {"minimum_period": {"max": 4.0}}}
        result = screen(libs, 5.0)
        self.assertFalse(result["period_only_pass"])
        self.assertIsNone(result["full_timing_pass"])
        self.assertTrue(screen(libs, 10.0)["period_only_pass"])

    def test_unclosed_groups_rejected(self):
        with self.assertRaises(ValueError):
            list(groups('timing() { inner() {}', "timing"))


if __name__ == "__main__":
    unittest.main()
