import unittest

from scripts.m6_contract_evidence import check_95_constraints


class ClockContractTests(unittest.TestCase):
    original = "# historical\ncreate_clock -name sys_clk -period 10 [get_ports clk]\nset_max_transition 0.35 [current_design]\n"

    def candidate(self):
        return self.original.replace("-period 10 ", "-period 10.526315789474 ")

    def test_only_period_changes(self):
        check_95_constraints(self.original, self.candidate())

    def test_electrical_relaxation_rejected(self):
        with self.assertRaises(ValueError):
            check_95_constraints(self.original, self.candidate().replace("0.35", "0.5"))

    def test_missing_or_different_clock_rejected(self):
        for candidate in ("", self.original, self.candidate().replace("10.526315789474", "11")):
            with self.assertRaises(ValueError):
                check_95_constraints(self.original, candidate)


if __name__ == "__main__":
    unittest.main()
