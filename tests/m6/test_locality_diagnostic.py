import copy
import unittest

from scripts.m6_locality_diagnostic import classify_constant_resets
from scripts.m6_report_contract_boundary import CORNERS


class ConstantResetTests(unittest.TestCase):
    def fixture(self):
        pins = [f"memory[{i}]/rstb" for i in range(8)]
        rows = [{"corner": corner, "pin": pin, "direction": "input",
                 **{key: "0" for key in ("rise_min_ns", "rise_max_ns",
                                          "fall_min_ns", "fall_max_ns")}}
                for corner in CORNERS for pin in pins]
        neighbours = [{"macro": f"memory\\[{i}\\]", "port": "rstb",
                       "master": "sky130_fd_sc_hd__conb_1", "neighbour_port": "HI",
                       "neighbour_direction": "OUTPUT", "external_ports": "0",
                       "pg": "VPWR=vdd,VPB=vdd,VGND=vss,VNB=vss"} for i in range(8)]
        summary = {corner: {"input_slew_outside_domain": [*pins, "memory[0]/clk"]}
                   for corner in CORNERS}
        return rows, neighbours, summary

    def test_raw_evidence_preserved_dynamic_clock_not_hidden(self):
        rows, neighbours, summary = self.fixture()
        original = copy.deepcopy(summary)
        result = classify_constant_resets(rows, neighbours, summary)
        for corner in CORNERS:
            self.assertEqual(result[corner]["input_slew_outside_domain"],
                             original[corner]["input_slew_outside_domain"])
            self.assertEqual(result[corner]["dynamic_input_slew_outside_domain"], ["memory[0]/clk"])
            self.assertEqual(len(result[corner]["constant_non_switching_reset_pins"]), 8)

    def test_zero_slew_does_not_prove_constant(self):
        for key, value in (("master", "sky130_fd_sc_hd__buf_1"),
                           ("neighbour_port", "LO"), ("neighbour_direction", "INPUT"),
                           ("external_ports", "1"), ("pg", "VPWR=MISSING")):
            with self.subTest(key=key):
                rows, neighbours, summary = self.fixture()
                neighbours[0][key] = value
                with self.assertRaises(ValueError):
                    classify_constant_resets(rows, neighbours, summary)

    def test_missing_corner_switching_or_additional_driver_rejected(self):
        for mutation in (lambda r, n: r.pop(),
                         lambda r, n: r[0].update(rise_max_ns="0.1"),
                         lambda r, n: n.append(n[0]),
                         lambda r, n: n.pop()):
            rows, neighbours, summary = self.fixture()
            mutation(rows, neighbours)
            with self.assertRaises(ValueError):
                classify_constant_resets(rows, neighbours, summary)


if __name__ == "__main__":
    unittest.main()
