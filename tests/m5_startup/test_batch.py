"""Whole-batch preflight, exact affine output and non-mutating rejections."""
import argparse
import ctypes as c
from pathlib import Path
import numpy as np
from ref.gpt2_quantized import affine_metadata, rne_shift


def check(path):
    lib = c.CDLL(str(Path(path).resolve())); fn = lib.pa_startup_batch_test
    fn.argtypes = [c.c_void_p]*5+[c.c_uint32]*2+[c.c_void_p]*3
    rng = np.random.default_rng(0xBA7C)
    accepted = rejected = 0
    for rows in (1, 2, 3, 7, 16):
        for columns in (31, 32, 64, 96, 768, 3072):
            for offset in (0, 1):
                units = rng.uniform(.0001, .01, rows)
                exponents = rng.integers(0, 4, rows, dtype=np.uint32)
                weights = rng.uniform(.0001, .02, columns)
                bias = rng.uniform(-10, 10, columns)
                sums = rng.integers(-2**26, 2**26+1, (rows, columns), dtype=np.int32)
                sums[:, :4] = [0, -2**31, 2**31-1, -1]
                scratch = np.full(2*columns, 999, np.int32)
                memory = np.full(rows*columns+2, 12345, np.int16)
                output = memory[offset:offset+rows*columns].reshape(rows, columns)
                out_exp = np.full(rows, 12345, np.uint32)
                def call():
                    return fn(*[a.ctypes.data for a in (units, exponents, weights, bias, sums)],
                        rows, columns, scratch.ctypes.data, output.ctypes.data, out_exp.ctypes.data)
                result = call()
                if rows == 1 or columns % 32 or offset:
                    assert result == 0 and np.all(memory == 12345) and np.all(out_exp == 12345)
                    rejected += 1; continue
                assert result == 1
                expected = []
                for row, unit, exponent in zip(sums, units, exponents):
                    scale = np.ldexp(unit*weights, int(exponent)+8)
                    multiplier, shift = affine_metadata(scale)
                    expected.append(np.clip(rne_shift(row.astype(np.int64)*multiplier, shift)+
                        np.rint(bias*256).astype(np.int64), -32768, 32767).astype(np.int16))
                np.testing.assert_array_equal(output, expected); np.testing.assert_array_equal(out_exp, 0)
                assert np.all(memory[:offset] == 12345) and np.all(memory[offset+rows*columns:] == 12345)
                accepted += 1
                for field in ('last_bias', 'last_exponent', 'last_weight', 'last_unit'):
                    output.fill(12345); out_exp.fill(12345)
                    saved = [a.copy() for a in (bias, exponents, weights, units)]
                    if field == 'last_bias': bias[-1] = np.inf
                    if field == 'last_exponent': exponents[-1] = 31
                    if field == 'last_weight': weights[-1] = -1
                    if field == 'last_unit': units[-1] = 0
                    assert call() == 0 and np.all(memory == 12345) and np.all(out_exp == 12345), field
                    for destination, before in zip((bias, exponents, weights, units), saved): destination[:] = before
                    rejected += 1
    print('STARTUP BATCH EXACT PASS', accepted, 'accepted;', rejected,
          'rejections, full-sum/saturation edges, all rows preflight, guards intact')


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__); p.add_argument('--library', required=True)
    check(p.parse_args().library)
