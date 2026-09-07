"""Bitwise original/candidate range reduction, not approximate output checks."""
import ctypes as c
import random
import struct
import subprocess
from pathlib import Path
import tempfile
import unittest


class Range(unittest.TestCase):
    def test_exact_range(self):
        with tempfile.TemporaryDirectory() as temporary:
            library = Path(temporary)/'range.so'
            subprocess.run(['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                            '-fno-fast-math', '-ffp-contract=off', '-shared', '-fPIC',
                            'tests/m5_iterate/range_host.c', '-o', str(library)], check=True)
            lib = c.CDLL(str(library))
            reference, candidate = lib.pa_iter_range_reference, lib.pa_iter_range_candidate
            for f in (reference, candidate):
                f.argtypes = [c.POINTER(c.c_int32), c.POINTER(c.c_double), c.POINTER(c.c_double),
                              c.POINTER(c.c_int16), c.c_uint32, c.c_uint32]
                f.restype = c.c_double
            rng = random.Random(0x3eaf913)
            raw = [0, 1, 0x000fffffffffffff, 0x0010000000000000, 0x3ff0000000000000,
                   0x7fefffffffffffff, 0x7ff0000000000000, 0x7ff8000000000000,
                   0x7ff0000000000001, 0x3fe0000000000000]
            raw += [rng.getrandbits(63) for _ in range(128)]
            floats = [struct.unpack('<d', struct.pack('<Q', bits | sign))[0]
                      for bits in raw for sign in (0, 1 << 63)]
            integers = [-2**31, -32768, -1, 0, 1, 32767, 2**31-1]
            cases = 0
            for exponent in (0, 1, 8, 15, 30):
                for scale in floats:
                    for integer in integers:
                        scales = (c.c_double*7)(scale, 0., 1., -1., 1e-300, 1e300, scale)
                        sums = (c.c_int32*7)(integer, 0, -1, 1, -32768, 32767, integer)
                        bias = (c.c_double*7)(-0., 0., scale, .5, -1., -1e300, rng.choice(floats))
                        residual = (c.c_int16*7)(-32768, 32767, 0, -1, 1, -128, 128)
                        for count in (1, 7):
                            for plane in (None, residual):
                                arguments = sums, scales, bias, plane, exponent, count
                                self.assertEqual(struct.pack('<d', candidate(*arguments)),
                                                 struct.pack('<d', reference(*arguments)))
                                cases += 1
            print('M5 ITERATE EXACT RANGE PASS', cases, 'bitwise comparisons')


if __name__ == '__main__':
    unittest.main()
