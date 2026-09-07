"""Prepared score finalization versus the actual original affine_row."""
import ctypes as c
import hashlib
from pathlib import Path
import random
import subprocess
import tempfile
import unittest


class Attention(unittest.TestCase):
    def test_planes_rounding_errors_and_workspace(self):
        baseline = Path('build/m5_fast_runtime_requant_v1/generated/ops.c')
        self.assertEqual(hashlib.sha256(baseline.read_bytes()).hexdigest(),
                         '03edc6897c644852135cc33c41d677133bca7126b043813f4e230fee70c625df')
        with tempfile.TemporaryDirectory() as temporary:
            library = Path(temporary)/'attention.so'
            subprocess.run(['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fno-fast-math', '-shared', '-fPIC', '-Iruntime/m5', '-Iruntime/m5_fast',
                'tests/m5_iterate/attention_host.c', 'build/m5_fast_runtime_requant_v1/generated/numerics.c',
                'runtime/m5/pa_m5_model.c', 'runtime/m5_fast/pa_m5_requant.c', '-o', str(library)], check=True)
            lib = c.CDLL(str(library))
            f = lib.pa_iter_attention_probe
            f.argtypes = [c.c_int, c.c_void_p, c.c_uint32, c.POINTER(c.c_int32),
                          c.POINTER(c.c_double), c.c_uint32, c.c_int64,
                          c.POINTER(c.c_int16), c.POINTER(c.c_uint32)]
            f.restype = c.c_int
            rng = random.Random(0xa11e17)
            cases = 0
            for count in (1, 3, 14, 16, 31, 64, 127, 768, 1024):
                inputs = (c.c_int32*count)(*[rng.randrange(-32768, 32768) for _ in range(count)])
                scales = (c.c_double*count)(*[2.**rng.randrange(-10, 10) for _ in range(count)])
                for capacity in (64, 64+count*4, 128+count*8, 16384):
                    for maximum in (0, -1, 32767, 2**31-1, -2**31, 2**31, 2**40, -2**40):
                        for fail in (0, 1):
                            results = []
                            for candidate in (0, 1):
                                work = c.create_string_buffer(16384)
                                output = (c.c_int16*count)(*([12345]*count))
                                state = (c.c_uint32*5)(0, 0, fail, 0, 0)
                                status = f(candidate, work, capacity, inputs, scales, count, maximum, output, state)
                                results.append((status, bytes(output), bytes(state)))
                            self.assertEqual(*results, msg=(count, capacity, maximum, fail))
                            cases += 1
            print('M5 ITERATE ATTENTION PREPARED EXACT PASS', cases, 'plane/output/error/workspace comparisons')


if __name__ == '__main__':
    unittest.main()
