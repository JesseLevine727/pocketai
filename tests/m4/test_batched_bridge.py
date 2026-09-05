import unittest
from collections import Counter
import numpy as np
from zynq.m4_offload import Runtime
from ref import sfpu_ref as sf
from ref.sfpu_stream import evaluate_and_pack
from ref.gpt2_quantized import dynamic_columns


class ReferencePacketBackend:
    """Test backend only; runtime never invokes numerical goldens."""
    def sfpu(self, descriptor, words):
        n = descriptor.length
        planes = tuple(words.view(np.int32)[i*n:(i+1)*n] for i in range(descriptor.planes))
        _, result = evaluate_and_pack(descriptor, planes)
        return result.view(np.int32)


class BatchedBridgeTests(unittest.TestCase):
    def runtime(self):
        result = Runtime.__new__(Runtime)
        result.backend = ReferencePacketBackend()
        result.metadata_counts = Counter()
        return result

    def test_every_representable_amax(self):
        # Exhaust all 32768 nonzero maxima, both signs, unsigned 32768,
        # arbitrary interior magnitudes, and zero columns across packet tails.
        model = self.runtime()
        for start in range(1, 32769, 256):
            maximum = np.arange(start, min(start + 256, 32769))
            raw = np.stack((maximum, -maximum, maximum // 3, np.zeros_like(maximum)))
            got, scales = model.requant_columns(raw, 1 / 256)
            expected, expected_scales = dynamic_columns(raw, 1 / 256)
            np.testing.assert_array_equal(got, expected)
            np.testing.assert_array_equal(scales, expected_scales)
        raw = np.zeros((13, 64), dtype=np.int16)
        got, scales = model.requant_columns(raw, 1 / 32768)
        self.assertTrue(np.all(got == 0) and np.all(scales == 1))

    def test_full_shapes_and_units(self):
        rng = np.random.default_rng(7161)
        model = self.runtime()
        for length, columns in ((1, 64), (13, 64), (33, 64), (1024, 64), (768, 13), (3072, 16)):
            raw = rng.integers(-32768, 32769, (length, columns), dtype=np.int32)
            got, scales = model.requant_columns(raw, 1 / 256)
            expected, expected_scales = dynamic_columns(raw, 1 / 256)
            np.testing.assert_array_equal(got, expected)
            np.testing.assert_array_equal(scales, expected_scales)


if __name__ == '__main__':
    unittest.main()
