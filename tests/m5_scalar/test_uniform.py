"""Uniform preparation versus the actual old affine_row, including failure paths."""
import ctypes as c
import hashlib
from pathlib import Path
import random
import subprocess
import tempfile
import unittest


class Uniform(unittest.TestCase):
    def test_planes_chunking_errors_and_workspace(self):
        baseline = Path('build/m5_iterate_c3_v1/generated/ops.c')
        self.assertEqual(hashlib.sha256(baseline.read_bytes()).hexdigest(),
                         'f4105a725ce430b4633501b9906048c0b4dba47f893b58c4f2933402937a1c8d')
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'uniform.so'
            subprocess.run(['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fno-fast-math', '-shared', '-fPIC', '-Iruntime/m5', '-Iruntime/m5_fast',
                'tests/m5_scalar/uniform_host.c', 'build/m5_iterate_c3_v1/generated/numerics.c',
                'runtime/m5/pa_m5_model.c', 'runtime/m5_fast/pa_m5_requant.c', '-o', str(path)], check=True)
            f = c.CDLL(str(path)).pa_scalar_uniform_probe
            f.argtypes = [c.c_int, c.c_void_p, c.c_uint32, c.c_void_p, c.c_double,
                          c.c_void_p, c.c_void_p, c.c_void_p, c.c_uint32,
                          c.c_void_p, c.c_void_p]
            f.restype = c.c_int
            rng = random.Random(0xaff1)
            cases = 0
            for count in (1, 14, 768, 3072, 3073, 50257):
                inputs = (c.c_int32*count)(*[rng.randrange(-32768, 32768) for _ in range(count)])
                for scale in (0., -0., .5, 1., 4., 2.**-30, 2.**30, 2.**-80, -1., float('inf'), float('nan')):
                    scales = (c.c_double*count)(*([scale]*count))
                    for with_bias in (False, True):
                        bias = (c.c_int32*count)(*[rng.randrange(-64, 64) if with_bias else 0 for _ in range(count)])
                        bias_double = (c.c_double*count)(*bias)
                        for capacity in (64, count*8+128, count*12+256):
                            for fail in (0, 1, 2):
                                observations = []
                                for candidate in (0, 1):
                                    storage = c.create_string_buffer(capacity+64)
                                    work = (c.addressof(storage)+63) & ~63
                                    output = (c.c_int16*count)(*([12345]*count))
                                    state = (c.c_uint32*5)(0, 0, fail, 0, 0)
                                    status = f(candidate, work, capacity, inputs, scale,
                                               bias if with_bias else None, scales, bias_double,
                                               count, output, state)
                                    observations.append((status, bytes(output), bytes(state)))
                                self.assertEqual(*observations, msg=(count, scale, with_bias, capacity, fail))
                                cases += 1
            print('M5 SCALAR UNIFORM EXACT PASS', cases, 'plane/chunk/error/workspace comparisons')


if __name__ == '__main__':
    unittest.main()
