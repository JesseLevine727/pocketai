"""Bitwise reciprocal across exponent classes and real smoothing metadata."""
import ctypes as c
import json
from pathlib import Path
import random
import struct
import subprocess
import tempfile
import unittest


class Reciprocal(unittest.TestCase):
    def test_exact_reciprocal(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'reciprocal.so'
            subprocess.run(['gcc', '-std=c11', '-O2', '-fno-fast-math', '-Wall', '-Wextra', '-Werror',
                '-shared', '-fPIC', '-Iruntime/m5_tenth', 'tests/m5_tenth/reciprocal_host.c', '-o', str(path)], check=True)
            lib = c.CDLL(str(path))
            for name in ('pa_tenth_candidate_reciprocal', 'pa_tenth_reference_reciprocal'):
                f = getattr(lib, name); f.argtypes = [c.c_double]; f.restype = c.c_double
            rng = random.Random(0x1d1d3)
            cases = 0
            def compare(value):
                nonlocal cases
                self.assertEqual(struct.pack('<d', lib.pa_tenth_reference_reciprocal(value)),
                                 struct.pack('<d', lib.pa_tenth_candidate_reciprocal(value)), value.hex())
                cases += 1
            for exponent in range(2048):
                for mantissa in (0, 1, 2, (1<<51)-1, 1<<51, (1<<52)-2, (1<<52)-1, rng.getrandbits(52)):
                    for sign in (0, 1<<63): compare(struct.unpack('<d', struct.pack('<Q', sign | exponent<<52 | mantissa))[0])
            for _ in range(200000): compare(struct.unpack('<d', struct.pack('<Q', rng.getrandbits(64)))[0])
            # Real arena is read only; every smoothing value is included.
            directory = Path('build/m5_arena.1Org4t/model')
            layout = json.loads((directory/'layout.json').read_text())
            with (directory/'model.bin').open('rb') as source:
                for item in layout['arrays']:
                    if item['name'].endswith('.smooth'):
                        source.seek(item['offset'])
                        for value, in struct.iter_unpack('<d', source.read(item['bytes'])): compare(value)
            print('M5 TENTH RECIPROCAL EXACT PASS', cases, 'certified binary64 reciprocals')


if __name__ == '__main__': unittest.main()
