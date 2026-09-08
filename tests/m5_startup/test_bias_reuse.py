"""Exact row-reuse eligibility, rounding ties and fallback-clobber lifetime."""
import argparse
import ctypes as c
from pathlib import Path

import numpy as np


def check(path):
    lib = c.CDLL(str(Path(path).resolve()))
    row = lib.pa_startup_project_test
    row.argtypes = [c.c_double, c.c_uint32]+[c.c_void_p]*3+[c.c_uint32, c.c_int,
                    c.c_void_p, c.c_uint32]+[c.c_void_p]*3
    rolling = hasattr(lib, 'pa_startup_rolling_rows_test')
    fixed = rolling or hasattr(lib, 'pa_startup_fixed_rows_test')
    seq = lib.pa_startup_rolling_rows_test if rolling else lib.pa_startup_fixed_rows_test if fixed else lib.pa_startup_bias_rows_test
    seq.argtypes = [c.c_double, c.c_uint32]+[c.c_void_p]*3+[c.c_uint32]*2+[c.c_void_p]*6
    rng = np.random.default_rng(0xB1A5)
    cases = reused = rejected = 0

    def trial(n, rows, exponent, mode):
        nonlocal cases, reused, rejected
        weights = np.full(n, 2.0**(exponent-8), np.float64)
        bias = rng.choice([0., -0., .5, -.5, 1.5, -1.5], n)*(2.0**(exponent-8))
        residual = rng.integers(-500, 501, (rows, n), dtype=np.int16)
        sums = rng.integers(-20000, 20001, (rows, n), dtype=np.int32)
        sums[:, 0] = 20000  # certify a positive incoming exponent
        exponents = np.full(rows, exponent, np.uint32)
        unit, input_exponent = 1., 0
        if mode == 'random':
            unit, input_exponent = 2.0**rng.uniform(-5, 1), int(rng.integers(0, 4))
            weights = 2.0**rng.uniform(-25, -12, n)
            bias = rng.uniform(-4, 4, n)*2.0**(exponent-8)
            residual = rng.integers(-32000, 32001, (rows, n), dtype=np.int16)
            sums = rng.integers(-(1<<26), (1<<26)+1, (rows, n), dtype=np.int32)
        if mode == 'mixed': exponents[-1] = exponent+1
        if mode == 'first_fallback': sums[0, 0] = 100000
        if mode == 'middle_fallback': sums[rows//2, 0] = 100000
        if mode == 'alternate': exponents[1::2] += 1
        if mode == 'returning': exponents[rows//2] += 1
        if mode == 'wide_bias':
            sums.fill(-40000); bias.fill(40000/256)
        if mode == 'subnormal': bias[0] = np.nextafter(0., 1.)
        if mode == 'invalid': bias[-1] = np.inf
        if mode == 'nan': bias[-1] = np.nan
        if mode == 'bias_limit': bias[-1] = 2.0**(29+exponent-8)
        source = [x.copy() for x in (weights, bias, residual, sums, exponents)]
        output = np.full((rows, n), -12345, np.int16)
        output_exp = np.full(rows, 0xDEADBEEF, np.uint32)
        expected, expected_exp = output.copy(), output_exp.copy()
        statuses = np.full(rows, -12345, np.int32)
        reference_status = []
        for i in range(rows):
            scratch = np.zeros(n, np.int16)
            reference_status.append(row(unit, input_exponent, weights.ctypes.data, bias.ctypes.data,
                sums[i].ctypes.data, n, 1, residual[i].ctypes.data, int(exponents[i]),
                scratch.ctypes.data, expected[i].ctypes.data, expected_exp[i:].ctypes.data))
        storage = np.full(n*(16 if fixed else 8)+128, 0xC7, np.uint8)
        scratch = storage[64:-64]
        count = seq(unit, input_exponent, weights.ctypes.data, bias.ctypes.data, sums.ctypes.data,
            rows, n, residual.ctypes.data, exponents.ctypes.data, scratch.ctypes.data,
            output.ctypes.data, output_exp.ctypes.data, statuses.ctypes.data)
        assert count >= 0
        reused += count
        rejected += sum(s == 0 for s in reference_status)
        if mode == 'wide_bias':
            assert np.all(np.asarray(reference_status) == 1) and np.all(statuses == 0)
            expected.fill(-12345); expected_exp.fill(0xDEADBEEF)
        else: np.testing.assert_array_equal(statuses, reference_status)
        np.testing.assert_array_equal(output, expected)
        np.testing.assert_array_equal(output_exp, expected_exp)
        assert np.all(storage[:64] == 0xC7) and np.all(storage[-64:] == 0xC7)
        for actual, old in zip((weights, bias, residual, sums, exponents), source):
            np.testing.assert_array_equal(actual.view(np.uint8), old.view(np.uint8))
        if mode == 'normal': assert count == rows-1 and np.all(statuses == 1)
        if mode in ('mixed', 'first_fallback'): assert count == (rows-2 if rolling else 0)
        if mode == 'middle_fallback': assert count == (max(1, rows-2) if rolling else rows//2)
        cases += 1

    for n in (1, 15, 16, 17, 31, 32, 33, 768):
        for rows in (2, 3, 8, 16):
            for exponent in (0, 1, 8, 30):
                for mode in ('normal', 'mixed', 'first_fallback', 'middle_fallback',
                             'subnormal', 'invalid', 'nan', 'bias_limit'):
                    trial(n, rows, exponent, mode)
    assert reused > 1000 and rejected > 100
    print('STARTUP ROLLING REUSE EXACT PASS' if rolling else 'STARTUP BIAS REUSE EXACT PASS', cases, 'sequences;', reused,
          'reused rows;', rejected, 'fallbacks; clobber invalidation, ties, guards, nonmutation')
    if fixed:
        before = cases, reused, rejected
        for _ in range(1024):
            trial(int(rng.choice([1, 15, 16, 17, 32, 33, 64, 768])),
                  int(rng.choice([2, 3, 8, 16])), int(rng.integers(0, 9)), 'random')
        assert cases-before[0] == 1024 and reused-before[1] > 100
        print('STARTUP RESIDUAL FIXED EXACT PASS', cases-before[0], 'random sequences;',
              reused-before[1], 'reused rows;', rejected-before[2],
              'fallbacks; non-power-of-two weights/units, row exponents, exact old operator')
    if rolling:
        before = cases, reused, rejected
        for n in (1, 15, 16, 17, 31, 32, 33, 768):
            for rows in (2, 3, 8, 16):
                for exponent in (0, 1, 8, 30):
                    for mode in ('alternate', 'returning'):
                        trial(n, rows, exponent, mode)
        print('STARTUP ROLLING TAG EXACT PASS', cases-before[0], 'sequences;',
              reused-before[1], 'reused rows;', rejected-before[2],
              'fallbacks; alternating and returning exponents rebuild after clobber')
    if hasattr(lib, 'pa_startup_local_project_capacity'):
        assert lib.pa_startup_local_project_capacity() == 2048
        before = cases
        for n in (2047, 2048, 2049):
            for rows in (2, 3):
                for exponent in (0, 8):
                    for mode in ('normal', 'middle_fallback', 'alternate', 'returning'):
                        trial(n, rows, exponent, mode)
        print('STARTUP LOCAL PROJECT EXACT PASS', cases-before,
              'boundary sequences; 2047/2048/2049 columns, two workers, fallback, tags, guards')
    if hasattr(lib, 'pa_startup_local_bias_capacity'):
        assert lib.pa_startup_local_bias_capacity() == 1024
        before = cases
        for n in (1023, 1024, 1025):
            for rows in (2, 3):
                for mode in ('normal', 'middle_fallback', 'alternate', 'returning', 'wide_bias'):
                    trial(n, rows, 0, mode)
        print('STARTUP LOCAL BIAS EXACT PASS', cases-before,
              'boundary sequences; 1023/1024/1025, exact int16 fit or full fallback, local poison, guards')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--library', required=True)
    check(parser.parse_args().library)
