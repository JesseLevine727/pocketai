import unittest
import numpy as np
from ref.m4_model_pack import tile_weights
from ref.gemm_v3_ref import M3GemmDescriptor, WIDE_RESULT_V1, pack_input_v3


class ModelPackTests(unittest.TestCase):
    def test_tiling_and_real_packet_layout(self):
        rng = np.random.default_rng(0x5041434b)
        for k, n, m in ((1, 1, 1), (7, 17, 3), (768, 50257, 1), (3072, 33, 16)):
            b = rng.integers(-128, 128, (k, n), dtype=np.int8)
            a = rng.integers(-128, 128, (m, k), dtype=np.int8)
            tiles = tile_weights(b)
            np.testing.assert_array_equal(tiles.transpose(1, 0, 2).reshape(k, -1)[:, :n], b)
            for tile in {0, len(tiles) - 1}:
                width = min(16, n - tile * 16)
                descriptor = M3GemmDescriptor(m, width, k, flags=WIDE_RESULT_V1)
                packed = pack_input_v3(descriptor, a, b[:, tile * 16:tile * 16 + width])
                np.testing.assert_array_equal(packed.view(np.int8)[m * ((k + 3) // 4) * 4:], tiles[tile].reshape(-1))
            if n % 16:
                self.assertTrue(np.all(tiles[-1, :, n % 16:] == 0))

    def test_invalid_weight_formats(self):
        for x in (np.zeros((4, 4)), np.zeros((3073, 1), dtype=np.int8), np.zeros((1, 0), dtype=np.int8)):
            with self.assertRaises(ValueError):
                tile_weights(x)


if __name__ == '__main__':
    unittest.main()
