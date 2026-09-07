"""Targeted factor-search differential, including failure output side effects."""
import argparse
import ctypes as c
import json
import math
from pathlib import Path
import random


def bind(path):
    lib = c.CDLL(str(Path(path).resolve()))
    f = lib.pa_m5_layernorm_metadata
    f.argtypes = [c.POINTER(c.c_int16), c.c_uint32, c.c_uint32,
                  c.POINTER(c.c_double), c.POINTER(c.c_double),
                  c.POINTER(c.c_int16), c.POINTER(c.c_int32), c.POINTER(c.c_uint32)]
    f.restype = c.c_int
    return f


def invoke(f, values, gain, bias, exponent, null=()):
    n = len(values)
    args = [(c.c_int16*n)(*values), n, exponent, (c.c_double*n)(*gain),
            (c.c_double*n)(*bias), (c.c_int16*n)(*([12345]*n)),
            (c.c_int32*n)(*([0x12345678]*n)), c.c_uint32(0x13579bdf)]
    call = args[:-1] + [c.byref(args[-1])]
    for index in null:
        call[index] = None
    rc = f(*call)
    return rc, bytes(args[5]), bytes(args[6]), args[7].value


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--candidate', required=True)
    args = parser.parse_args()
    baseline, candidate = bind(args.baseline), bind(args.candidate)
    rng = random.Random(0x173a51)
    cases, failures = 0, 0

    def check(values, gain, bias, exponent, null=()):
        nonlocal cases, failures
        expected = invoke(baseline, values, gain, bias, exponent, null)
        assert invoke(candidate, values, gain, bias, exponent, null) == expected, (cases, exponent)
        cases += 1
        failures += expected[0] != 0

    # Exact factor threshold and its adjacent binary64 encodings, +/- gains,
    # homogeneous/nonhomogeneous input and correction with all storage exponents.
    threshold = 32767/4096
    for exponent in range(31):
        for factor in (1, 2, 256, 1 << 30):
            for value in (math.nextafter(threshold*factor, 0), threshold*factor,
                          math.nextafter(threshold*factor, math.inf)):
                for sign in (-1, 1):
                    gain = [1., -.5, sign*value, -0., 0., 1.5, -2.]
                    check([0]*7, gain, [0.]*7, exponent)
                    check([-32768, 32767, 5, 1, -2, 32760, -4], gain,
                          [.5/256, 1.5/256, -2.5/256, 0., 1., -1., 0.], exponent)
    for n in (1, 7, 64, 768, 3072):
        for _ in range(12):
            values = [rng.randrange(-32768, 32768) for _ in range(n)]
            gain = [rng.uniform(-30, 30) for _ in range(n)]
            bias = [rng.uniform(-100, 100) for _ in range(n)]
            check(values, gain, bias, rng.randrange(31))
    # NaN/inf gain fallback and bad bias preserve the original return value AND
    # partial output mutation; finite magnitudes near overflow/underflow too.
    edges = [float('nan'), float('inf'), -float('inf'), 1e300, -1e300, 5e-324, -5e-324]
    for value in edges:
        for index in (0, 3, 6):
            for exponent in (0, 1, 30):
                gain, bias = [1.]*7, [0.]*7
                gain[index] = value
                check([100]*7, gain, bias, exponent)
                gain[index], bias[index] = 1., value
                check([100]*7, gain, bias, exponent)
    for index in (0, 3, 4, 5, 6, 7):
        check([1], [1.], [0.], 0, (index,))
    for count, exponent in ((0, 0), (3073, 0), (7, 31)):
        check([1]*count, [1.]*count, [0.]*count, exponent)
    print('M5 ITERATE NORM FACTOR EXACT PASS', json.dumps(dict(cases=cases, failures=failures,
          partial_output_side_effects=True, maximum_count=3072)))


if __name__ == '__main__':
    main()
