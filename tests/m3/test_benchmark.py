"""Host tests for the board benchmark, independent of PYNQ/Vivado."""
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np
from ref.gemm_ref import Descriptor, pack_input_words
from zynq.m3_benchmark import load_cpu, pack_projection, qualify_cpu, summary

ROOT = Path(__file__).resolve().parents[2]


class BenchmarkTests(unittest.TestCase):
    def test_packing_matches_legacy(self):
        rng = np.random.default_rng(42)
        b = rng.integers(-128, 128, (768, 768), dtype=np.int8)
        for m in (1, 16):
            a = rng.integers(-128, 128, (m, 768), dtype=np.int8)
            d = Descriptor(m, 16, 768)
            packed = np.empty((48, d.input_words), dtype=np.uint32)
            pack_projection(a, b, packed)
            for t in (0, 1, 23, 47):
                expected = pack_input_words(d, a, b[:, t * 16:(t + 1) * 16])
                np.testing.assert_array_equal(packed[t], expected)

    def test_statistics(self):
        result = summary([1.0, 2.0, 3.0], 2_000_000_000)
        self.assertEqual(result["median_ms"], 2000)
        self.assertEqual(result["delivered_gmac_s"], 1)
        self.assertAlmostEqual(result["p95_ms"], 2900)
        for values in ([], [0], [-1], [float("nan")], [float("inf")]):
            with self.assertRaises(ValueError):
                summary(values, 1)

    def test_native_cpu(self):
        with tempfile.TemporaryDirectory(prefix="pocketai-m3-cpu-") as directory:
            library = Path(directory) / "cpu.so"
            subprocess.run(["gcc", "-O3", "-Wall", "-Wextra", "-Werror", "-shared",
                            "-fPIC", str(ROOT / "zynq/m3_cpu_gemm.c"),
                            "-o", str(library)], check=True)
            lib, fn = load_cpu(library)
            self.assertEqual(qualify_cpu(fn), 20)
            self.assertIn(b"single-thread", lib.pa_cpu_backend())


if __name__ == "__main__":
    unittest.main()
