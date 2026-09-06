"""Differential checks against the untouched M5 scalar ABI before optimization."""
import argparse
import ctypes as c
import json
import math
import random
import struct


def bind(path):
    lib = c.CDLL(path)
    lib.pa_m5_rne_u64.argtypes = [c.c_uint64, c.c_uint64]
    lib.pa_m5_rne_u64.restype = c.c_uint64
    lib.pa_m5_rne_i64.argtypes = [c.c_int64, c.c_uint64]
    lib.pa_m5_rne_i64.restype = c.c_int64
    lib.pa_m5_affine_metadata.argtypes = [c.POINTER(c.c_double), c.c_uint32,
                                        c.POINTER(c.c_uint32), c.POINTER(c.c_uint32)]
    lib.pa_m5_affine_metadata.restype = c.c_int
    return lib


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True)
    parser.add_argument('--candidate', required=True)
    args = parser.parse_args()
    base, candidate = bind(args.baseline), bind(args.candidate)
    rng = random.Random(0x4d354f50)
    integer_cases = 0
    for denominator in [0, 1, 3, 127, 32767, 32768, 2**64-1] + [2**s for s in range(64)]:
        values = [0, 1, 2**63-1, 2**63, 2**64-1]
        for q in (0, 1, 2, 3, 16, 127):
            values += [min(2**64-1, max(0, q*denominator+denominator//2+d)) for d in (-1, 0, 1)]
        values += [rng.getrandbits(64) for _ in range(200)]
        for value in values:
            assert candidate.pa_m5_rne_u64(value, denominator) == base.pa_m5_rne_u64(value, denominator)
            signed = c.c_int64(value).value
            assert candidate.pa_m5_rne_i64(signed, denominator) == base.pa_m5_rne_i64(signed, denominator)
            integer_cases += 2
    sets = [[0., -0.], [.5, 1.5, 2.5], [2**31-.5], [2**31-1.5], [2**31],
            [-1.], [float('inf')], [float('nan')], [5e-324], [0., -1., 1.]]
    for exponent in range(-64, 65):
        sets.append([2.**exponent * x for x in (.5, .75, 1., 1.5, 2., 3.)])
    for shift in range(32):
        for integer in (0, 1, 2, 127, 2**31-2, 2**31-1):
            tie = (integer + .5) / 2.**shift
            for value in (math.nextafter(tie, 0.), tie, math.nextafter(tie, math.inf)):
                sets.append([0., value, value / 2.])
    for _ in range(500):
        sets.append([struct.unpack('<d', struct.pack('<Q', rng.getrandbits(64)))[0]
                     for _ in range(rng.randrange(1, 65))])
        sets.append([2.**rng.uniform(-40, 30) for _ in range(rng.randrange(1, 65))])
    for scales in sets:
        source = (c.c_double * len(scales))(*scales)
        outputs = []
        for lib in (base, candidate):
            multipliers = (c.c_uint32 * len(scales))(*([0xdeadbeef]*len(scales)))
            shift = c.c_uint32(0xdeadbeef)
            status = lib.pa_m5_affine_metadata(source, len(scales), multipliers, c.byref(shift))
            outputs.append((status, list(multipliers), shift.value))
        assert outputs[0] == outputs[1], (scales, outputs)
    print('M5 OPT EXACT NUMERICS PASS', json.dumps({'integer_results': integer_cases,
          'affine_cases': len(sets), 'checks_error_side_effects': True}))


if __name__ == '__main__':
    main()
