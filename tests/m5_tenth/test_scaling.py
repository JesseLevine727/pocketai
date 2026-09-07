"""Actual generated power-of-two helpers: signed zeros and fallback edges."""
import ctypes as c
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from scripts.m5_tenth_sources import function


class Scaling(unittest.TestCase):
    def test_exact_generated_helpers(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, library = Path(temporary)/'scale.c', Path(temporary)/'scale.so'
            texts = ['#include <stdint.h>']
            for index, directory in enumerate(('m5_search_product_v1', 'm5_tenth_reciprocal_v1')):
                generated = (Path('build')/directory/'generated/numerics.c').read_text()
                body = function(generated, 'pa_fast_scale_power2')
                texts.append(body.replace('static double pa_fast_scale_power2', 'double scale_'+str(index)))
            source.write_text('\n'.join(texts)+'\n')
            subprocess.run(['gcc', '-std=c11', '-O2', '-fno-fast-math', '-Wall', '-Wextra', '-Werror',
                            '-shared', '-fPIC', str(source), '-o', str(library)], check=True)
            lib = c.CDLL(str(library))
            for f in (lib.scale_0, lib.scale_1): f.argtypes = [c.c_double, c.c_int]; f.restype = c.c_double
            cases = 0
            for encoded in (0, 1, 2, 1022, 1023, 1024, 2045, 2046, 2047):
                for fraction in (0, 1, (1<<51)-1, 1<<51, (1<<52)-1):
                    for sign in (0, 1<<63):
                        value = struct.unpack('<d', struct.pack('<Q', sign | encoded<<52 | fraction))[0]
                        for power in (-1023, -1022, -60, -30, -22, 0, 8, 12, 30, 1023, 1024):
                            self.assertEqual(struct.pack('<d', lib.scale_0(value, power)),
                                             struct.pack('<d', lib.scale_1(value, power)))
                            cases += 1
            print('M5 TENTH POWER2 EXACT PASS', cases, 'signed-zero and range/special fallback cases')


if __name__ == '__main__': unittest.main()
