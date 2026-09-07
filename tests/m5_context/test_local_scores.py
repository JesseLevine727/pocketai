"""Exact local score affine, saturation, and non-mutating fallback."""
import argparse
import ctypes as c
from pathlib import Path
import numpy as np
from ref.sfpu_ref import rne_div


def check(path):
    lib = c.CDLL(str(Path(path).resolve())); f = lib.pa_context_local_scores
    f.argtypes = [c.c_void_p, c.c_void_p, c.c_uint32, c.c_uint32, c.c_void_p]
    rng = np.random.default_rng(0x10CA1)
    count = 0
    for n in (1, 13, 31, 1024):
        for shift in (0, 1, 7, 24, 31):
            for extreme in (False, True):
                raw = rng.integers(-2**20, 2**20, n, np.int32)
                multiplier = rng.integers(1, 2**31, n, np.uint32)
                if extreme: raw[0] = -2**31; raw[-1] = 2**31-1
                output = np.full(n, 1234567, np.int32)
                rounded = [rne_div(int(a)*int(b), 2**shift) for a, b in zip(raw, multiplier)]
                status = f(raw.ctypes.data, multiplier.ctypes.data, n, shift, output.ctypes.data)
                if min(rounded) < -2**31 or max(rounded) > 2**31-1:
                    assert status == -1 and np.all(output == 1234567)
                else:
                    expected = [0x10000 | (max(-32768, x-max(rounded)) & 65535) for x in rounded]
                    assert status == 0
                    np.testing.assert_array_equal(output, expected)
                count += 1
    print('CONTEXT LOCAL SCORES EXACT PASS', count, 'sets; tails, full1024, signed endpoints, untouched fallback output')


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__); p.add_argument('--candidate', required=True)
    check(p.parse_args().candidate)
