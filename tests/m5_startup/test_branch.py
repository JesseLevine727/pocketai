"""Every accepted branch equals full binary64-to-multiplier-to-integer RNE."""
import argparse
import ctypes as c
from pathlib import Path
import numpy as np


def check(path):
    rng = np.random.default_rng(0xB2A); count = 500000
    factors = np.ldexp(rng.uniform(1, 2, count), rng.integers(-16, 0, count))
    weights = np.ldexp(rng.uniform(1, 2, count), rng.integers(-12, -2, count))
    power = rng.integers(-8, 13, count, dtype=np.int32)
    shift = rng.integers(8, 32, count, dtype=np.uint32)
    values = rng.integers(-2**26, 2**26+1, count, dtype=np.int32)
    values[:count//2] = rng.integers(-65536, 65537, count//2, dtype=np.int32)
    # Include cancellation-free halfway and neighboring metadata boundaries.
    factors[:10000] = 1
    weights[:10000] = np.nextafter(rng.integers(1, 10000, 10000)+.5,
                                  np.tile([-np.inf, np.inf], 5000))*2.0**-20
    power[:10000] = 0; shift[:10000] = 20
    multiplier = np.rint(np.ldexp(np.ldexp(factors*weights, power), shift.astype(np.int32)))
    valid = (multiplier > 0)&(multiplier < 2**31)
    safe = np.where(valid, multiplier, 0).astype(np.uint64)
    product = np.abs(values.astype(np.int64)).astype(np.uint64)*safe
    s = shift.astype(np.uint64); q = product>>s
    remainder = product&((np.uint64(1)<<s)-np.uint64(1)); half = np.uint64(1)<<(s-1)
    q += (remainder > half)|((remainder == half)&((q&1) != 0))
    expected = np.where(values < 0, -q.astype(np.int64), q.astype(np.int64))
    lib = c.CDLL(str(Path(path).resolve())); fn = lib.pa_startup_branch_test
    fn.argtypes = [c.c_void_p]*7+[c.c_uint32]
    out = np.full(count, 12345, np.int32); status = np.zeros(count, np.int32)
    fn(*[a.ctypes.data for a in (factors, weights, power, shift, values, out, status)], count)
    accepted = status != 0
    assert np.all(valid[accepted]) and np.all(np.abs(expected[accepted]) < 2**29)
    np.testing.assert_array_equal(out[accepted], expected[accepted])
    assert np.all(out[~accepted] == 12345)
    assert accepted.sum() > 100000
    print('STARTUP FINAL BRANCH EXACT PASS', count, 'cases;', accepted.sum(), 'certified, all rejections non-mutating')


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__); p.add_argument('--library', required=True)
    check(p.parse_args().library)
