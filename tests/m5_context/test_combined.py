"""Fused score preparation preserves both affine rounding and fallback output boundaries."""
import argparse
import ctypes as c
from pathlib import Path
import numpy as np
from ref.sfpu_ref import rne_div


def check(path):
    lib = c.CDLL(str(Path(path).resolve())); f = lib.pa_context_score_combined
    f.argtypes = [c.c_void_p, c.c_uint32, c.c_double, c.c_double]+[c.c_void_p]*5
    base = c.CDLL(str(Path('build/m5_tenth_reciprocal_v1/native.so').resolve()))
    base.pa_m5_affine_metadata.argtypes = [c.c_void_p, c.c_uint32, c.c_void_p, c.c_void_p]
    rng = np.random.default_rng(0xC0B1ED); count = 0
    for n in (1, 13, 31, 32, 63, 128, 1024):
        for mode in range(12):
            units = np.exp2(rng.uniform(-14, -1, n))
            query = float(2**rng.uniform(-10, -1))
            raw = rng.integers(-2**20, 2**20, n, np.int32)
            if mode & 1: raw[0] = -2**31; raw[-1] = 2**31-1
            if mode == 2: units[0] = -1
            if mode == 3: units[0] = 0
            if mode == 4: units[0] = 2**-1074
            if mode == 5: units[0] = np.inf
            if mode == 6: query = 0
            scales = query*units*32; maximum = max(0., *units.tolist())
            expected_mult = np.zeros(n, np.uint32); expected_shift = c.c_uint32()
            baseline = base.pa_m5_affine_metadata(scales.ctypes.data, n, expected_mult.ctypes.data, c.byref(expected_shift))
            multipliers = np.zeros(n, np.uint32); shift = c.c_uint32(); scratch = np.zeros(n, np.float64)
            tagged = np.full(n, 1234567, np.int32)
            status = f(units.ctypes.data, n, query, maximum, multipliers.ctypes.data, c.byref(shift),
                       scratch.ctypes.data, raw.ctypes.data, tagged.ctypes.data)
            if baseline:
                assert status == baseline and np.all(tagged == 1234567)
            else:
                assert shift.value == expected_shift.value
                if status == 1:
                    np.testing.assert_array_equal(multipliers, expected_mult)
                    assert np.all(tagged == 1234567)
                else:
                    assert status == 0
                    rounded = [rne_div(int(a)*int(b), 2**shift.value) for a, b in zip(raw, expected_mult)]
                    assert min(rounded) >= -2**31 and max(rounded) < 2**31
                    expected = [0x10000 | (max(-32768, x-max(rounded)) & 65535) for x in rounded]
                    np.testing.assert_array_equal(tagged, expected)
            count += 1
    print('CONTEXT COMBINED SCORES EXACT PASS', count, 'threaded sets; full1024, split tails, specials, preserved fallback boundary')


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__); p.add_argument('--candidate', required=True)
    check(p.parse_args().candidate)
