"""Certify fixed-factor branches against the original binary64 two-rounding path."""
import argparse
import ctypes as c
from pathlib import Path
import numpy as np
from ref.gpt2_quantized import rne_shift


def check(path):
    rng = np.random.default_rng(0xF12ED); count = 500000
    wreal = rng.uniform(1, 2**31-1, count)
    rreal = rng.uniform(2**29, 2**31-1, count)
    wreal[:10000] = rng.integers(1, 2**30, 10000)+.5
    rreal[:10000] = rng.integers(2**29, 2**30, 10000)+.5
    weight = np.rint(wreal).astype(np.uint32); row = np.rint(rreal).astype(np.uint32)
    shift = rng.integers(8, 32, count, dtype=np.uint32)
    values = rng.integers(-2**26, 2**26+1, count, dtype=np.int32)
    values[:count//2] = rng.integers(-65536, 65537, count//2, dtype=np.int32)
    # S=20, power=8; all power-of-two operations here are normal/exact.
    weights = np.ldexp(wreal, -20)
    units = np.ldexp(rreal, -18-shift.astype(np.int32))
    multiplier = np.rint(np.ldexp(np.ldexp(units*weights, 8), shift.astype(np.int32)))
    valid = (multiplier > 0)&(multiplier < 2**31)
    products = values.astype(np.int64)*np.where(valid, multiplier, 0).astype(np.int64)
    expected = np.zeros(count, np.int64)
    for s in range(8, 32):
        select = shift == s; expected[select] = rne_shift(products[select], s)
    lib = c.CDLL(str(Path(path).resolve())); fn = lib.pa_startup_fixed_test
    fn.argtypes = [c.c_void_p]*6+[c.c_uint32]
    output = np.full(count, 12345, np.int32); status = np.zeros(count, np.int32)
    fn(*[a.ctypes.data for a in (values, weight, row, shift, output, status)], count)
    accepted = status != 0
    assert np.all(valid[accepted]) and np.all(np.abs(expected[accepted]) < 2**29)
    np.testing.assert_array_equal(output[accepted], expected[accepted])
    assert np.all(output[~accepted] == 12345)
    assert accepted.sum() > 100000
    print('STARTUP FIXED FACTOR EXACT PASS', count, 'cases;', accepted.sum(), 'certified, all fallback outputs unchanged')


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__); p.add_argument('--library', required=True)
    check(p.parse_args().library)
