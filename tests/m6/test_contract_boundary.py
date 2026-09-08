import unittest

from scripts.m6_report_contract_boundary import CORNERS, evaluate_rows


class BoundaryTests(unittest.TestCase):
    def fixture(self):
        return [{"corner": corner, "pin": f"pin_{i}", "direction": "input" if i < 392 else "output",
                 "rise_min_ns": "0.1", "rise_max_ns": "0.1", "fall_min_ns": "0.1", "fall_max_ns": "0.1",
                 "load_min_pf": "0.01", "load_max_pf": "0.01"}
                for corner in CORNERS for i in range(648)]

    envelope = {"input_slew_min_ns": 0.002, "input_slew_max_ns": 0.351,
                "output_load_min_pf": 0.007, "output_load_max_pf": 0.013, "design_transition_limit_ns": 0.35}

    def test_complete_valid_fixture(self):
        result = evaluate_rows(self.fixture(), self.envelope)
        self.assertTrue(all(not r["input_slew_outside_domain"] and not r["output_load_outside_domain"] for r in result.values()))

    def test_missing_duplicate_or_nonfinite_cannot_pass(self):
        for mutation in (lambda r: r.pop(), lambda r: r.__setitem__(0, r[1]),
                         lambda r: r[0].__setitem__("rise_max_ns", "nan")):
            rows = self.fixture()
            mutation(rows)
            with self.assertRaises(ValueError):
                evaluate_rows(rows, self.envelope)

    def test_lower_load_and_input_upper_bound_checked(self):
        rows = self.fixture()
        rows[0]["rise_max_ns"] = "0.36"
        rows[392]["load_min_pf"] = "0.006"
        result = evaluate_rows(rows, self.envelope)[CORNERS[0]]
        self.assertEqual(result["input_slew_outside_domain"], ["pin_0"])
        self.assertEqual(result["output_load_outside_domain"], ["pin_392"])

    def test_output_slew_checked_independently(self):
        rows = self.fixture()
        rows[392]["rise_max_ns"] = "0.36"
        self.assertEqual(evaluate_rows(rows, self.envelope)[CORNERS[0]]["output_slew_violations"], ["pin_392"])


if __name__ == "__main__":
    unittest.main()
