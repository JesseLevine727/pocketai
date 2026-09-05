import unittest
import numpy as np
from ref.gemm_v3_ref import (M3GemmDescriptor, WIDE_RESULT_V1, gemm_wide_int32,
                             pack_input_v3, pack_output_v3)
from ref.gemm_ref import pack_input_words


class WideGemmReferenceTests(unittest.TestCase):
    def test_legacy_rejections_unchanged(self):
        for flags, k in ((0, 769), (1, 768), (0x101, 768), (WIDE_RESULT_V1, 3073)):
            with self.assertRaises(ValueError):
                M3GemmDescriptor(16, 16, k, flags=flags).validate()

    def test_dimensions_word_counts(self):
        d = M3GemmDescriptor(16, 16, 3072, flags=WIDE_RESULT_V1)
        d.validate()
        self.assertEqual(d.input_words, 24576)
        self.assertEqual(d.output_words, 256)
        self.assertEqual(M3GemmDescriptor(16, 16, 768).output_words, 128)

    def test_stream_packing(self):
        rng = np.random.default_rng(123)
        a = rng.integers(-128, 128, (3, 767), dtype=np.int16).astype(np.int8)
        b = rng.integers(-128, 128, (767, 5), dtype=np.int16).astype(np.int8)
        legacy = M3GemmDescriptor(3, 5, 767)
        wide = M3GemmDescriptor(3, 5, 767, flags=WIDE_RESULT_V1)
        np.testing.assert_array_equal(pack_input_v3(wide, a, b), pack_input_words(legacy, a, b))
        result = gemm_wide_int32(a, b)
        unpacked = pack_output_v3(wide, result).view("<i4").reshape(3, 16)
        np.testing.assert_array_equal(unpacked[:, :5], result)
        np.testing.assert_array_equal(unpacked[:, 5:], 0)

    def test_maximum_sum(self):
        a = np.full((16, 3072), -128, dtype=np.int8)
        b = np.full((3072, 16), -128, dtype=np.int8)
        result = gemm_wide_int32(a, b)
        np.testing.assert_array_equal(result, np.full((16, 16), 50331648, dtype=np.int32))

    def test_cancellation_cannot_use_saturated_chunks(self):
        a = np.full((1, 3072), 127, dtype=np.int8)
        b = np.full((3072, 1), 127, dtype=np.int8)
        b[1536:] = -127
        b[-1] = -126
        expected = gemm_wide_int32(a, b)
        self.assertEqual(int(expected[0, 0]), 127)
        wrong = sum(int(np.clip((a[:, start:start + 768].astype(np.int64) @
                                 b[start:start + 768].astype(np.int64))[0, 0],
                                -32768, 32767)) for start in range(0, 3072, 768))
        self.assertNotEqual(wrong, 127)


if __name__ == "__main__":
    unittest.main()
