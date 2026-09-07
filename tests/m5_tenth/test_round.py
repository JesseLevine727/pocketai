"""Exact signed binary64 RNE fast-domain and original int64 fallback checks."""
import argparse
import ctypes as c
import math
import random
import struct


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--candidate', required=True)
    args = parser.parse_args()
    functions = []
    for path in ('build/m5_search_product_v1/native.so', args.candidate):
        f = c.CDLL(path).pa_m5_rne_f64_signed
        f.argtypes = [c.c_double]; f.restype = c.c_int64
        functions.append(f)
    rng = random.Random(0x1002026)
    cases = 0
    def compare(value):
        nonlocal cases
        assert functions[0](value) == functions[1](value), value.hex()
        cases += 1
    for encoded in range(2048):
        for fraction in (0, 1, (1<<51)-1, 1<<51, (1<<52)-1, rng.getrandbits(52)):
            for sign in (0, 1<<63):
                compare(struct.unpack('<d', struct.pack('<Q', sign | encoded<<52 | fraction))[0])
    for integer in list(range(-32769, 32770)) + [2**31-1, 2**31, -2**31, -2**31-1]:
        tie = integer+.5
        for value in (math.nextafter(tie, -math.inf), tie, math.nextafter(tie, math.inf)): compare(value)
    for _ in range(100000): compare(struct.unpack('<d', struct.pack('<Q', rng.getrandbits(64)))[0])
    print('M5 TENTH SIGNED ROUND EXACT PASS', cases, 'binary64/int64 comparisons')


if __name__ == '__main__': main()
