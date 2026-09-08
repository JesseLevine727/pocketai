import unittest

from scripts.m6_sram_contract import derive_envelope, patch_outputs, verify_patch


class ContractTests(unittest.TestCase):
    def test_characterized_grid_not_extrapolated_limit(self):
        tables = [([0.002, 0.351], [0.007, 0.013, 0.033],
                   [[0.20, 0.26, 0.44], [0.21, 0.27, 0.45]])]
        result = derive_envelope(tables, 0.35)
        self.assertEqual(result["output_load_max_pf"], 0.013)
        self.assertEqual(result["output_load_min_pf"], 0.007)
        self.assertEqual(result["worst_characterized_transition_ns"], 0.27)
        with self.assertRaises(ValueError):
            derive_envelope(tables, 0.04)

    def test_all_corners_and_both_edges_contribute(self):
        fast = ([0.002, 0.351], [0.007, 0.013, 0.033], [[0.1, 0.2, 0.3]]*2)
        slow = ([0.002, 0.351], [0.007, 0.013, 0.033], [[0.2, 0.4, 0.5]]*2)
        self.assertEqual(derive_envelope([fast, slow], 0.35)["output_load_max_pf"], 0.007)

    def fixture(self):
        return 'default_max_transition: 0.04; bus(dout) {direction: output;\n' + ''.join(
            f'pin(dout[{i}]) {{ max_capacitance : 0.52; }}\n' for i in range(32)) + 'timing() {cell_rise(t) {values("9");}}}'

    def test_only_output_metadata_changes(self):
        original = self.fixture()
        updated = patch_outputs(original, 0.35, 0.007, 0.013)
        verify_patch(original, updated, 0.35, 0.007, 0.013)
        self.assertIn('default_max_transition: 0.04;', updated)
        self.assertEqual(updated.count('max_transition : 0.35;'), 32)
        with self.assertRaises(ValueError):
            verify_patch(original, updated.replace('values("9")', 'values("8")'), 0.35, 0.007, 0.013)

    def test_changed_pin_count_rejected(self):
        with self.assertRaises(ValueError):
            patch_outputs(self.fixture().replace('pin(dout[31])', 'pin(unreviewed)'), 0.35, 0.007, 0.013)


if __name__ == "__main__":
    unittest.main()
