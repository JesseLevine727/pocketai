"""Exact split-word RNE and non-mutating wider fallback at the +/-2^29 bound."""
import argparse
import ctypes as c
from pathlib import Path
import numpy as np


def check(path):
    rng = np.random.default_rng(0x29); count = 300000
    values = rng.integers(-(2**31), 2**31, count, dtype=np.int32)
    multiplier = rng.integers(0, 2**32, count, dtype=np.uint32)
    shift = rng.integers(0, 33, count, dtype=np.uint32)
    edge = np.array([0, 1, -1, 2**29-1, 2**29, -(2**29), -(2**31)], np.int32)
    values[:len(edge)*33] = np.tile(edge, 33)
    multiplier[:len(edge)*33] = 2
    shift[:len(edge)*33] = np.repeat(np.arange(33), len(edge))
    product = np.abs(values.astype(np.int64)).astype(np.uint64)*multiplier
    s = shift.astype(np.uint64); q = product>>s
    remainder = product&((np.uint64(1)<<s)-np.uint64(1))
    half = np.uint64(1)<<np.maximum(s, np.uint64(1))-np.uint64(1)
    q += (s != 0)&((remainder > half)|((remainder == half)&((q&1) != 0)))
    accepted = (shift >= 1)&(shift <= 31)&(q < 2**29)
    expected = np.full(count, 12345, np.int32)
    signed = np.where(values < 0, -q.astype(np.int64), q.astype(np.int64))
    expected[accepted] = signed[accepted].astype(np.int32)
    lib = c.CDLL(str(Path(path).resolve())); fn = lib.pa_startup_word_test
    fn.argtypes = [c.c_void_p]*5+[c.c_uint32]
    output = np.full(count, 12345, np.int32); status = np.zeros(count, np.int32)
    fn(values.ctypes.data, multiplier.ctypes.data, shift.ctypes.data, output.ctypes.data,
       status.ctypes.data, count)
    np.testing.assert_array_equal(status, accepted.astype(np.int32))
    np.testing.assert_array_equal(output, expected)
    print('STARTUP WORD AFFINE EXACT PASS', count, 'wide products, shifts, saturation/fallback boundaries')


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__); p.add_argument('--library', required=True)
    check(p.parse_args().library)
