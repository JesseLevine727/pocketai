"""Exact fused metadata/range certification, including rejected non-mutating rows."""
import argparse
import ctypes as c
from pathlib import Path
import numpy as np
from ref.gpt2_quantized import affine_metadata, rne_shift
from ref.gpt2_scaled import storage_exponent


def check(path):
    lib = c.CDLL(str(Path(path).resolve())); fn = lib.pa_startup_project_test
    fn.argtypes = [c.c_double, c.c_uint32]+[c.c_void_p]*3+[c.c_uint32, c.c_int, c.c_void_p,
                   c.c_uint32]+[c.c_void_p]*3
    fn.restype = c.c_int
    rng = np.random.default_rng(0xF05ED); accepted = rejected = 0

    def trial(unit, iexp, weights, biases, sums, scaled, residual, rexp):
        nonlocal accepted, rejected
        n = len(sums)
        weights = np.ascontiguousarray(weights, dtype=np.float64)
        biases = np.ascontiguousarray(biases, dtype=np.float64)
        sums = np.ascontiguousarray(sums, dtype=np.int32)
        if residual is not None: residual = np.ascontiguousarray(residual, dtype=np.int16)
        scratch = np.zeros(n, np.int16); output = np.full(n, -12345, np.int16)
        exponent = c.c_uint32(0xDEADBEEF)
        status = fn(unit, iexp, weights.ctypes.data, biases.ctypes.data, sums.ctypes.data,
                    n, scaled, None if residual is None else residual.ctypes.data, rexp,
                    scratch.ctypes.data, output.ctypes.data, c.byref(exponent))
        assert status in (0, 1), status
        if not status:
            rejected += 1
            np.testing.assert_array_equal(output, -12345)
            assert exponent.value == 0xDEADBEEF
            return
        accepted += 1
        scales = (unit*weights)*(2.0**iexp)
        logical = sums.astype(np.float64)*scales+biases
        if residual is not None:
            logical = np.abs(logical)+np.abs(residual.astype(np.float64)*(2.0**(rexp-8)))
        expected_exp = int(storage_exponent(np.max(np.abs(logical)))) if scaled or residual is not None else 0
        assert exponent.value == expected_exp, (exponent.value, expected_exp)
        multiplier, shift = affine_metadata(scales*(2.0**(8-expected_exp)))
        rbias = np.rint(biases*(2.0**(8-expected_exp))).astype(np.int64)
        branch = np.clip(rne_shift(sums.astype(np.int64)*multiplier, shift)+rbias, -32768, 32767)
        if residual is not None:
            rm, rs = affine_metadata(np.full(n, 2.0**(rexp-expected_exp)))
            aligned = np.clip(rne_shift(residual.astype(np.int64)*rm, rs), -32768, 32767)
            branch = np.clip(branch+aligned, -32768, 32767)
        np.testing.assert_array_equal(output, branch.astype(np.int16))

    for i in range(3000):
        n = int(rng.choice([1, 15, 16, 17, 31, 32, 33, 64, 127]))
        trial(2.0**rng.uniform(-8, 1), i%5,
              2.0**rng.uniform(-20, -7, n), rng.uniform(-2, 2, n),
              rng.integers(-10000000, 10000001, n, dtype=np.int32), i%3 != 0,
              rng.integers(-20000, 20001, n, dtype=np.int16) if i%3 == 1 else None, i%6)
    # Strict thresholds, both signs, signed zeros and cancellation. These
    # deliberately trigger uncertainty fallback near the exact boundary.
    for boundary in (0, 16350, 32700):
        for delta in range(-12, 13):
            for sign in (-1, 1):
                for bias in (-0.5/256, -0.0, 0.5/256):
                    trial(1.0, 0, np.full(33, 1/256), np.full(33, bias),
                          np.full(33, sign*(boundary+delta), np.int32), 1, None, 0)
    for value in (0.0, -1.0, np.inf, np.nan, np.nextafter(0.0, 1.0), 1e308):
        trial(1.0, 0, [value], [0], [1], 1, None, 0)
        trial(1.0, 0, [1/256], [value], [1], 1, None, 0)
    assert accepted > 1000 and rejected > 100
    print('STARTUP FUSED PROJECT EXACT PASS', accepted, 'accepted rows;', rejected,
          'fallback rows leave output/exponent unchanged')


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__); p.add_argument('--library', required=True)
    check(p.parse_args().library)
