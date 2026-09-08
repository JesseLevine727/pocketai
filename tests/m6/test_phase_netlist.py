import unittest

from scripts.m6_check_phase_netlist import check


def fixture():
    def cell(kind, ports, outputs):
        return dict(type="sky130_fd_sc_hd__" + kind,
                    connections={name: [bit] for name, bit in ports.items()},
                    port_directions={name: "output" if name in outputs else "input"
                                     for name in ports})
    cells = {
        "u_clock.inv_clk": cell("inv_2", dict(A=1, Y=4), {"Y"}),
        "u_clock.inv_d": cell("inv_2", dict(A=3, Y=5), {"Y"}),
        "u_clock.ff": cell("dfrtp_2", dict(CLK=4, D=5, Q=3, RESET_B=2), {"Q"}),
        "phase_inv_d": cell("inv_2", dict(A=6, Y=7), {"Y"}),
        "phase_ff": cell("dfstp_1", dict(CLK=4, D=7, Q=6, SET_B=2), {"Q"}),
    }
    for index in range(292):
        cells[f"ram{index}"] = dict(type="sram22_512x32m4w8",
            connections=dict(we=[6]), port_directions=dict(we="input"))
    return dict(modules=dict(pa_m6_soc=dict(cells=cells, ports=dict(
        clk_mem_i=dict(bits=[1]), s_axi_aresetn=dict(bits=[2])))))


class PhaseNetlistTests(unittest.TestCase):
    def test_separate_complementary_state(self):
        result = check(fixture())
        self.assertEqual(result["macros"], 292)
        self.assertEqual(result["independent_phase_registers"], 1)
        self.assertFalse(result["macro_write_enable_is_clock"])

    def test_clock_reuse_rejected(self):
        design = fixture()
        design["modules"]["pa_m6_soc"]["cells"]["ram0"]["connections"]["we"] = [3]
        with self.assertRaisesRegex(AssertionError, "merged"):
            check(design)

    def test_missing_macro_rejected(self):
        design = fixture()
        del design["modules"]["pa_m6_soc"]["cells"]["ram0"]
        with self.assertRaisesRegex(AssertionError, "capacity"):
            check(design)

    def test_wrong_reset_or_clock_rejected(self):
        for port in ("SET_B", "CLK", "D"):
            design = fixture()
            design["modules"]["pa_m6_soc"]["cells"]["phase_ff"]["connections"][port] = [5]
            with self.assertRaises(AssertionError):
                check(design)


if __name__ == "__main__":
    unittest.main()
