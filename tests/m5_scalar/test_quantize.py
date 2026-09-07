"""Exact bounded-domain quantization and the full uint32 divider API."""
import argparse
import ctypes as c
from pathlib import Path
import random


def check(path):
    lib = c.CDLL(str(Path(path).resolve()))
    lib.pa_m5_dynamic_multiplier.argtypes = [c.c_uint32]
    lib.pa_m5_dynamic_multiplier.restype = c.c_uint32
    lib.pa_scalar_quantize_probe.argtypes = [c.c_int32, c.c_uint32]
    lib.pa_scalar_quantize_probe.restype = c.c_int8
    lib.pa_scalar_rne_probe.argtypes = [c.c_int32, c.c_uint32, c.c_uint32]
    lib.pa_scalar_rne_probe.restype = c.c_int64
    lib.pa_scalar_scaled_probe.argtypes = [c.c_uint64, c.c_uint32]
    lib.pa_scalar_scaled_probe.restype = c.c_uint32
    rng = random.Random(0x5ca1a2)
    maxima = list(range(32769)) + [2**31, 2**32-1, 127<<24]
    maxima += [rng.randrange(2**32) for _ in range(10000)]
    for maximum in maxima:
        if maximum:
            q, r = divmod(127 << 24, maximum)
            expected = q + (r > maximum-r or (r == maximum-r and q & 1))
        else:
            expected = 0
        assert lib.pa_m5_dynamic_multiplier(maximum) == expected, maximum
    multipliers = [0, 1, 255, 256, (1<<23)-1, 1<<23, (1<<23)+1,
                   (127<<24), 2**31-1, 2**32-1]
    cases = 0
    for value in range(-32768, 32769):
        for multiplier in multipliers:
            q, r = divmod(abs(value)*multiplier, 1<<24)
            q += r > (1<<23) or (r == (1<<23) and q & 1)
            expected = max(-128, min(127, -q if value < 0 else q))
            assert lib.pa_scalar_quantize_probe(value, multiplier) == expected, (value, multiplier)
            cases += 1
    print('M5 SCALAR QUANTIZE EXACT PASS', len(maxima), 'divider cases;', cases,
          'full input-domain quantization cases')
    cases = 0
    for shift in range(32):
        values = [-2**31, 2**31-1, -32768, 32768, 0, -1, 1]
        values += [rng.randrange(-2**31, 2**31) for _ in range(2000)]
        for value in values:
            for multiplier in multipliers:
                q, r = divmod(abs(value)*multiplier, 1<<shift)
                q += r > (1<<shift)-r or (r == (1<<shift)-r and q & 1)
                expected = -q if value < 0 else q
                assert lib.pa_scalar_rne_probe(value, multiplier, shift) == expected
                cases += 1
    print('M5 SCALAR VARIABLE SHIFT EXACT PASS', cases, 'signed product/RNE cases')
    cases = 0
    for encoded in range(2047):
        for fraction in (0, 1, (1<<51)-1, 1<<51, (1<<52)-1, rng.getrandbits(52)):
            bits = (encoded<<52) | fraction
            for shift in range(32):
                exponent = encoded - 1023 + shift - 52
                if encoded == 0:
                    expected = 0
                elif exponent >= 0:
                    expected = 0x80000000
                else:
                    q, r = divmod((1<<52)|fraction, 1<<-exponent)
                    expected = min(0x80000000, q + (r > (1<<-exponent)-r or
                                    (r == (1<<-exponent)-r and q & 1)))
                assert lib.pa_scalar_scaled_probe(bits, shift) == expected, (encoded, fraction, shift)
                cases += 1
    print('M5 SCALAR AFFINE ROUND EXACT PASS', cases, 'binary64 exponent/mantissa/shift cases')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--candidate', required=True)
    check(parser.parse_args().candidate)
