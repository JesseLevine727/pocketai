"""Exact hot-table signed saturation, all int16 inputs, and generic fallback."""
import argparse
import ctypes as c
from pathlib import Path
import numpy as np


def check(candidate):
    lib = c.CDLL(str(Path(candidate).resolve()))
    lib.pa_startup_lut_test.argtypes = [c.c_void_p]*3
    rng = np.random.default_rng(0xC01D)
    values = np.arange(-32768, 32768, dtype=np.int16).reshape(1024, 64)
    multipliers = [np.full(64, m, np.uint32) for m in (0, 1, 1 << 24, 0xffffffff)]
    multipliers.append(rng.integers(1, 0xffffffff, 64, dtype=np.uint32))
    for multiplier in multipliers:
        output = np.zeros((4, 1024, 16), np.int8)
        lib.pa_startup_lut_test(values.ctypes.data, multiplier.ctypes.data, output.ctypes.data)
        absolute = np.abs(values.astype(np.int64)).astype(np.uint64)
        product = absolute*multiplier.astype(np.uint64)
        quotient = product >> 24; remainder = product & 0xffffff
        quotient += (remainder > 0x800000) | ((remainder == 0x800000) & ((quotient & 1) != 0))
        signed = np.where(values < 0, -quotient.astype(np.int64), quotient.astype(np.int64))
        expected = np.clip(signed, -128, 127).astype(np.int8)
        np.testing.assert_array_equal(output.transpose(1, 0, 2).reshape(1024, 64), expected)
    print('STARTUP LUT EXACT PASS 327680 values; all int16, hot/fallback boundaries, asymmetric saturation')


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__); p.add_argument('--candidate', required=True); args = p.parse_args()
    check(args.candidate)
