"""Bitwise normal/subnormal/boundary validation of the exact scaling helper."""
import ctypes as c
from pathlib import Path
import random
import struct
import subprocess
import tempfile
import unittest


class Power2(unittest.TestCase):
    def test_bits(self):
        with tempfile.TemporaryDirectory() as temporary:
            library = Path(temporary) / 'power2.so'
            subprocess.run(['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                            '-fno-fast-math', '-shared', '-fPIC',
                            'tests/m5_fast/power2_host.c', '-o', str(library)], check=True)
            lib = c.CDLL(str(library))
            for name in ('pa_fast_test_scale', 'pa_fast_reference_scale'):
                function = getattr(lib, name)
                function.argtypes = [c.c_double, c.c_int]; function.restype = c.c_double
            rng = random.Random(0x50324d35)
            values = [0, 1, 0x000fffffffffffff, 0x0010000000000000,
                      0x3ff0000000000000, 0x7fefffffffffffff, 0x7ff0000000000000]
            values += [rng.getrandbits(63) for _ in range(1024)]
            count = 0
            for exponent in range(-22, 31):
                for raw in values:
                    for sign in (0, 1 << 63):
                        value = struct.unpack('<d', struct.pack('<Q', raw | sign))[0]
                        got = lib.pa_fast_test_scale(value, exponent)
                        expected = lib.pa_fast_reference_scale(value, exponent)
                        self.assertEqual(struct.pack('<d', got), struct.pack('<d', expected))
                        count += 1
            print('M5 FAST EXACT POWER2 PASS', count, 'bitwise comparisons')


if __name__ == '__main__': unittest.main()
