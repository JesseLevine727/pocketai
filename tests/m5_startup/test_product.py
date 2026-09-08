"""Full binary64 and integer double-rounding oracle for certified products."""
import argparse
import ctypes as c
from pathlib import Path
import numpy as np


def check(path):
    rng = np.random.default_rng(0x106)
    count = 300000
    factors = np.exp2(rng.uniform(-40, 20, count))
    weights = np.exp2(rng.uniform(-40, 10, count))
    power = rng.integers(-22, 39, count, dtype=np.int32)
    shift = rng.integers(0, 32, count, dtype=np.uint32)
    ties = np.arange(1, 10001, dtype=np.float64)+.5
    near = np.concatenate((np.nextafter(ties, 0), ties, np.nextafter(ties, np.inf)))
    factors = np.concatenate((factors, np.ones(len(near))))
    weights = np.concatenate((weights, near/(2.0**31)))
    power = np.concatenate((power, np.zeros(len(near), dtype=np.int32)))
    shift = np.concatenate((shift, np.full(len(near), 31, dtype=np.uint32)))
    # Each operation has the same ordered binary64 rounding as the model;
    # positive normal-to-normal power-of-two scaling is exact.
    product = factors*weights
    scaled = np.ldexp(product, power)
    expected = np.minimum(np.rint(np.ldexp(scaled, shift.astype(np.int32))), 2**31).astype(np.uint32)
    lib = c.CDLL(str(Path(path).resolve())); fn = lib.pa_startup_product_test
    fn.argtypes = [c.c_void_p]*5+[c.c_uint32]
    output = np.empty(len(expected), np.uint32)
    fn(factors.ctypes.data, weights.ctypes.data, power.ctypes.data, shift.ctypes.data,
       output.ctypes.data, len(output))
    np.testing.assert_array_equal(output, expected)
    print('STARTUP PRODUCT TWO-ROUNDING EXACT PASS', len(output),
          'normal products, exponent edges, halfway and adjacent values')


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__); p.add_argument('--library', required=True)
    check(p.parse_args().library)
