"""Bitwise int32/binary64 products, exponent/rounding boundaries and fallback."""
import ctypes as c
from pathlib import Path
import random
import struct
import subprocess
import tempfile
import unittest


class Multiply(unittest.TestCase):
    def test_full_product_and_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'multiply.so'
            subprocess.run(['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fno-fast-math', '-shared', '-fPIC', '-Iruntime/m5_search',
                'tests/m5_search/mul_host.c', '-o', str(path)], check=True)
            lib = c.CDLL(str(path))
            for name in ('pa_search_mul_candidate', 'pa_search_mul_reference'):
                f = getattr(lib, name); f.argtypes = [c.c_int32, c.c_double]; f.restype = c.c_double
            rng = random.Random(0x32b164)
            cases = 0
            integers = [0, 1, -1, 2, -2, 3, -3, 32767, -32768, 2**31-1, -2**31]
            integers += [2**n-1 for n in range(2, 31)]
            for encoded in range(2048):
                for fraction in (0, 1, (1<<51)-1, 1<<51, (1<<52)-1, rng.getrandbits(52)):
                    bits = (encoded<<52) | fraction
                    for sign in (0, 1<<63):
                        value = struct.unpack('<d', struct.pack('<Q', bits|sign))[0]
                        for integer in integers:
                            reference = lib.pa_search_mul_reference(integer, value)
                            candidate = lib.pa_search_mul_candidate(integer, value)
                            self.assertEqual(struct.pack('<d', reference), struct.pack('<d', candidate),
                                             (encoded, fraction, sign, integer))
                            cases += 1
            for _ in range(50000):
                bits = rng.getrandbits(64)
                value = struct.unpack('<d', struct.pack('<Q', bits))[0]
                integer = rng.randrange(-2**31, 2**31)
                self.assertEqual(struct.pack('<d', lib.pa_search_mul_reference(integer, value)),
                                 struct.pack('<d', lib.pa_search_mul_candidate(integer, value)))
                cases += 1
            print('M5 SEARCH I32 BINARY64 EXACT PASS', cases, 'bitwise products, all exponent classes and signed endpoints')


if __name__ == '__main__':
    unittest.main()
