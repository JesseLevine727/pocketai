import unittest
from scripts.m6_100mhz_evidence import CORNERS, physical_summary


class PhysicalEvidenceTests(unittest.TestCase):
    def metrics(self):
        names = ("timing__setup__ws", "timing__setup__tns", "timing__hold__ws",
                 "timing__hold__tns", "design__max_slew_violation__count",
                 "design__max_cap_violation__count")
        result = {n: 0 for n in names}
        result.update({n+"__corner:"+c: 0 for c in CORNERS for n in names})
        result.update({n: 0 for n in ("route__drc_errors", "design__power_grid_violation__count",
                      "antenna__violating__nets", "antenna__violating__pins",
                      "timing__unannotated_net_filtered__count")})
        return result

    def test_missing_corner_is_not_pass(self):
        metrics = self.metrics()
        del metrics["timing__setup__ws__corner:"+CORNERS[2]]
        with self.assertRaises(KeyError):
            physical_summary(metrics)

    def test_missing_antenna_check_is_not_zero(self):
        metrics = self.metrics()
        del metrics["antenna__violating__nets"]
        with self.assertRaises(KeyError):
            physical_summary(metrics)

    def test_violations_are_preserved(self):
        metrics = self.metrics()
        metrics["timing__setup__ws"] = -0.282
        metrics["design__max_slew_violation__count"] = 3610
        result = physical_summary(metrics)
        self.assertEqual(result["timing__setup__ws"], -0.282)
        self.assertEqual(result["design__max_slew_violation__count"], 3610)

    def test_clean_probe_numbers_do_not_certify_system(self):
        self.assertEqual(physical_summary(self.metrics())["qualification"],
                         "UNQUALIFIED_PROBE_NOT_FULL_SYSTEM")


if __name__ == "__main__":
    unittest.main()
