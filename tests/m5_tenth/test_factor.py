"""Full binary64 products including 106-bit rounding and special fallback."""
import ctypes as c
from pathlib import Path
import random
import struct
import subprocess
import tempfile
import unittest


class Factor(unittest.TestCase):
    def test_exact_products(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'factor.so'
            subprocess.run(['gcc', '-std=c11', '-O2', '-fno-fast-math', '-Wall', '-Wextra', '-Werror',
                '-shared', '-fPIC', '-Iruntime/m5_tenth', 'tests/m5_tenth/mul_host.c', '-o', str(path)], check=True)
            lib = c.CDLL(str(path))
            for name in ('pa_tenth_candidate', 'pa_tenth_reference'):
                f = getattr(lib, name); f.argtypes = [c.c_double, c.c_double]; f.restype = c.c_double
            def floating(bits): return struct.unpack('<d', struct.pack('<Q', bits))[0]
            cases = 0
            def compare(a, b):
                nonlocal cases
                self.assertEqual(struct.pack('<d', lib.pa_tenth_reference(a, b)),
                                 struct.pack('<d', lib.pa_tenth_candidate(a, b)), (a.hex(), b.hex()))
                cases += 1
            rng = random.Random(0x106b17)
            for exponent in range(2048):
                for fraction in (0, 1, (1<<51)-1, 1<<51, (1<<52)-1, rng.getrandbits(52)):
                    for sign in (0, 1<<63):
                        a = floating(sign | exponent<<52 | fraction)
                        for e in (0, 1, 2, 1022, 1023, 1024, 2045, 2046, 2047):
                            for m in (0, 1, (1<<52)-1, rng.getrandbits(52)):
                                b = floating(e<<52 | m | (rng.getrandbits(1)<<63))
                                compare(a, b)
            for _ in range(100000): compare(floating(rng.getrandbits(64)), floating(rng.getrandbits(64)))
            print('M5 TENTH FACTOR EXACT PASS', cases, 'full binary64 products')


if __name__ == '__main__': unittest.main()
