"""Fused preparation against actual qualified ordered scaling/affine operations."""
import ctypes as c
from pathlib import Path
import random
import subprocess
import tempfile
import unittest


class Fusion(unittest.TestCase):
    def test_exact_planes_fallback_errors_and_workspace(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'fusion.so'
            subprocess.run(['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fno-fast-math', '-shared', '-fPIC', '-Iruntime/m5', '-Iruntime/m5_fast', '-Iruntime/m5_scalar',
                'tests/m5_search/fusion_host.c', 'build/m5_scalar_affine_v1/generated/numerics.c',
                'runtime/m5/pa_m5_model.c', 'build/m5_scalar_affine_v1/generated/requant.c',
                'runtime/m5_scalar/cache.c', '-o', str(path)], check=True)
            f = c.CDLL(str(path)).pa_search_fusion_probe
            f.argtypes = [c.c_int, c.c_void_p, c.c_uint32, c.c_void_p, c.c_void_p, c.c_void_p,
                          c.c_void_p, c.c_uint32, c.c_int, c.c_void_p, c.c_void_p]
            f.restype = c.c_int
            rng = random.Random(0xf053d)
            cases = 0
            for count in (0, 1, 17, 768, 3073, 50257):
                inputs = (c.c_int32*count)(*[rng.randrange(-64, 65) for _ in range(count)])
                normal = [2.**rng.uniform(-8, -4) for _ in range(count)]
                for exceptional in (None, 0., -0., -1., 5e-324, 2.**-1022, 2.**1023, float('inf'), float('nan')):
                    values = normal.copy()
                    if count and exceptional is not None: values[count//2] = exceptional
                    for power in (-22, 0, 8):
                        for invalid_bias in (False, True):
                            bias = (c.c_double*count)(*[rng.uniform(-4, 4) for _ in range(count)])
                            if count and invalid_bias: bias[-1] = 2.**40
                            for capacity in (64, count*8+128, count*12+256):
                                for fail in (0, 1, 2):
                                    observations = []
                                    for candidate in (0, 1):
                                        storage = c.create_string_buffer(capacity+64)
                                        work = (c.addressof(storage)+63) & ~63
                                        scales = (c.c_double*count)(*values)
                                        scratch = (c.c_double*count)()
                                        output = (c.c_int16*count)(*([12345]*count))
                                        state = (c.c_uint32*5)(0, 0, fail, 0, 0)
                                        status = f(candidate, work, capacity, inputs, scales, bias,
                                                   scratch, count, power, output, state)
                                        observations.append((status, bytes(output), bytes(state)))
                                    self.assertEqual(*observations, msg=(count, exceptional, power, invalid_bias, capacity, fail))
                                    cases += 1
            print('M5 SEARCH FUSION EXACT PASS', cases, 'plane/fallback/error/workspace comparisons')


if __name__ == '__main__':
    unittest.main()
