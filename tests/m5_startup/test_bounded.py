"""Proven complete 32-bit products for maximum-derived int16/Q15 quantization."""
import argparse
import ctypes as c
from pathlib import Path
import numpy as np


def check(path):
    rng = np.random.default_rng(0xB0D)
    maxima = np.concatenate((np.tile(np.arange(1, 32769, dtype=np.uint64), 8),
                             rng.integers(1, 32769, 200000, dtype=np.uint64)))
    coefficient = np.uint64(127 << 24)
    multiplier = coefficient//maxima
    remainder = coefficient%maxima
    multiplier += (2*remainder > maxima) | ((2*remainder == maxima) & ((multiplier&1) != 0))
    values = rng.integers(0, 2**32, len(maxima), dtype=np.uint64)%(maxima+1)
    values[:32768] = maxima[:32768]
    values[32768:65536] = maxima[32768:65536]//2
    values[65536:98304] = maxima[65536:98304]-1
    product = values*multiplier
    assert np.all(product < 2**31)
    quotient = product>>24; remainder = product&0xffffff
    quotient += (remainder > 0x800000) | ((remainder == 0x800000) & ((quotient&1) != 0))
    negative = (np.arange(len(values))&1) != 0
    inputs = np.where(negative, -values.astype(np.int64), values.astype(np.int64)).astype(np.int32)
    expected = np.where(negative, -quotient.astype(np.int64), quotient.astype(np.int64)).astype(np.int8)
    inputs = np.concatenate((inputs, np.array([0, 32768, -32768], np.int32)))
    multipliers = np.concatenate((multiplier.astype(np.uint32), np.array([0, 65024, 65024], np.uint32)))
    expected = np.concatenate((expected, np.array([0, 127, -127], np.int8)))
    lib = c.CDLL(str(Path(path).resolve()))
    for name in ('pa_startup_bounded_test', 'pa_startup_signed_test'):
        fn = getattr(lib, name); fn.argtypes = [c.c_void_p]*3+[c.c_uint32]
        output = np.zeros(len(inputs), np.int8)
        fn(inputs.ctypes.data, multipliers.ctypes.data, output.ctypes.data, len(inputs))
        np.testing.assert_array_equal(output, expected)
    print('STARTUP BOUNDED PRODUCT EXACT PASS', len(inputs), 'values; every maximum, signed endpoints, ties, Q15 endpoint')


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__); p.add_argument('--library', required=True); args = p.parse_args()
    check(args.library)
