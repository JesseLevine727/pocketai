import unittest
from scripts.m6_check_1x_consumers import instrument


class ConsumerInstrumentationTests(unittest.TestCase):
    def source(self):
        return "\n".join(f"module {name}();\nwire marker;\nendmodule" for name in
                         ("pa_m5_axi_burst", "pa_m6_cluster_core", "pa_gemm", "pa_sfpu"))

    def test_all_required_targets_instrumented_once(self):
        original = self.source()
        modified, found = instrument(original)
        self.assertEqual(len(found), 4)
        self.assertEqual(modified.count("wire marker;"), 4)
        self.assertEqual(modified.count("always @(posedge"), 4)
        self.assertIn("assert (!(mem_we && mem_re))", modified)

    def test_missing_target_fails_closed(self):
        with self.assertRaises(ValueError):
            instrument(self.source().replace("pa_sfpu", "unused_sfpu"))

    def test_duplicate_target_fails_closed(self):
        with self.assertRaises(ValueError):
            instrument(self.source()+"\nmodule pa_gemm();\nendmodule")

    def test_unrelated_module_is_unchanged(self):
        extra = "module pa_gemm_extra();\nwire untouched;\nendmodule"
        result, _ = instrument(self.source()+"\n"+extra)
        self.assertIn(extra, result)


if __name__ == "__main__":
    unittest.main()
