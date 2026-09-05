import unittest
import numpy as np
from zynq.m4_offload import affine_parameters, rounded_product, packet_words, Runtime
from zynq.m4_driver import pack_gemm_into, FpgaBackend
from ref.gpt2_quantized import affine_metadata, rne_shift
from ref.gemm_v3_ref import M3GemmDescriptor, WIDE_RESULT_V1, pack_input_v3
from ref.sfpu_stream import Op, SfpuDescriptor, evaluate_and_pack


class RuntimeControlTests(unittest.TestCase):
    def test_metadata_matches_frozen(self):
        rng = np.random.default_rng(872323)
        for length in (1, 17, 3072, 50257):
            scales = rng.uniform(1e-4, 4, length)
            m, s = affine_parameters(scales)
            em, es = affine_metadata(scales)
            np.testing.assert_array_equal(m, em)
            self.assertEqual(s, es)
        x = rng.integers(-(1 << 31), 1 << 31, 1000, dtype=np.int64)
        m = rng.integers(0, 1 << 31, 1000, dtype=np.int64)
        for s in range(32):
            np.testing.assert_array_equal(rounded_product(x, m, s), rne_shift(x * m, s))

    def test_gemm_dma_packet_layout(self):
        rng = np.random.default_rng(42783)
        target = np.empty(24576, dtype=np.uint32)
        for m, n, k in ((1, 1, 1), (3, 13, 7), (16, 16, 3072), (13, 1, 768)):
            a = rng.integers(-128, 128, (m, k), dtype=np.int8)
            b = np.zeros((k, 16), dtype=np.int8)
            b[:, :n] = rng.integers(-128, 128, (k, n), dtype=np.int8)
            size = pack_gemm_into(target, a, b)
            expected = pack_input_v3(M3GemmDescriptor(m, n, k, flags=WIDE_RESULT_V1), a, b[:, :n])
            np.testing.assert_array_equal(target[:size], expected)

    def test_sfpu_packet_without_golden_evaluation(self):
        x = np.array([-32768, 32767, 0, 5], dtype=np.int32)
        for op, planes, shift, multiplier in (
                (Op.GELU, (x,), 0, 0), (Op.LAYERNORM, (x, x, x), 0, 0),
                (Op.SOFTMAX, (x, np.array([True, False, True, True])), 0, 0),
                (Op.AFFINE, (x, np.array([1, 2, 3, 4]), x), 5, 0),
                (Op.REQUANT8, (np.array([32768, 0, 1, -2]),), 24, 1234),
                (Op.ADD, (x, x), 0, 0)):
            expected, _ = evaluate_and_pack(SfpuDescriptor(op, 4, shift, multiplier), planes)
            np.testing.assert_array_equal(packet_words(op, planes), expected)

    def test_failed_backend_does_not_rewrite_buffers(self):
        backend = FpgaBackend.__new__(FpgaBackend)
        backend.failed, backend.closed = True, False
        backend.tx_array = np.full(24576, 0x12345678, dtype=np.uint32)
        with self.assertRaises(RuntimeError):
            backend.gemm(np.ones((1, 1), dtype=np.int8), np.zeros((1, 1, 16), dtype=np.int8), 1)
        with self.assertRaises(RuntimeError):
            backend.sfpu(SfpuDescriptor(Op.GELU, 1), np.array([0], dtype=np.uint32))
        self.assertTrue(np.all(backend.tx_array == 0x12345678))

    def test_invalid_prefill_rejected_before_any_step(self):
        runtime = Runtime.__new__(Runtime)
        runtime.length, runtime.capacity = 0, 1024
        runtime.step = lambda *args, **kwargs: self.fail('invalid input entered the model')
        for tokens in ([1] * 16 + [50257], [1.0], [], [1] * 1025):
            with self.assertRaises(ValueError):
                runtime.prefill(tokens)


if __name__ == '__main__':
    unittest.main()
