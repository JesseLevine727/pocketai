import unittest

from scripts.m6_electrical_screen import interpolate, named_group, output_screen, table


class ElectricalScreenTest(unittest.TestCase):
    def test_bilinear_interpolation_and_no_extrapolation(self):
        sample = ([0.1, 0.2], [0.01, 0.03], [[1., 3.], [2., 4.]])
        self.assertAlmostEqual(interpolate(sample, 0.15, 0.02), 2.5)
        for x, y in ((0.09, 0.02), (0.15, 0.04)):
            with self.assertRaises(ValueError):
                interpolate(sample, x, y)

    def test_table_dimensions_fail_closed(self):
        with self.assertRaises(ValueError):
            table('index_1("1,2"); index_2("3,4"); values("5,6,7");')

    def test_exact_named_group(self):
        text = 'pin(clk2) {capacitance: 9;} pin("clk") {capacitance: 2;}'
        self.assertEqual(named_group(text, "pin", "clk").strip(), "capacitance: 2;")
        with self.assertRaises(ValueError):
            named_group(text, "pin", "missing")

    def fixture(self, override=""):
        return '''time_unit: "1ns"; capacitive_load_unit(1,pf);
          default_max_transition: 0.04;
          slew_lower_threshold_pct_rise: 10; slew_upper_threshold_pct_rise: 90;
          slew_lower_threshold_pct_fall: 10; slew_upper_threshold_pct_fall: 90;
          bus(dout) {direction: output; ''' + override + '''
            rise_transition(t) {index_1("0.1,0.2"); index_2("0.01,0.02");
              values("0.21,0.3", "0.22,0.4");}
            fall_transition(t) {index_1("0.1,0.2"); index_2("0.01,0.02");
              values("0.16,0.3", "0.18,0.4");}
          }'''

    def test_default_conflict_is_not_physical_defect_claim(self):
        result = output_screen(self.fixture())
        self.assertFalse(result["any_characterized_output_transition_meets_default"])
        self.assertEqual(result["minimum_characterized_output_transition_ns"], 0.16)
        self.assertIsNone(result["physical_timing_pass"])

    def test_unreviewed_override_and_missing_units_rejected(self):
        for text in (self.fixture("max_transition: 0.5;"),
                     self.fixture().replace('"1ns"', '"1ps"'),
                     self.fixture().replace('capacitive_load_unit(1,pf);', '')):
            with self.assertRaises(ValueError):
                output_screen(text)


if __name__ == "__main__":
    unittest.main()
