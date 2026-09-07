"""Exact fused score metadata, including fallback domains and query-cache epochs."""
import argparse
import ctypes as c
from pathlib import Path
import numpy as np


def check(path):
    lib = c.CDLL(str(Path(path).resolve()))
    baseline = c.CDLL(str(Path('build/m5_tenth_reciprocal_v1/native.so').resolve()))
    lib.pa_context_score_metadata.argtypes = [c.c_void_p, c.c_uint32, c.c_double, c.c_double,
        c.c_void_p, c.c_void_p, c.c_void_p]
    baseline.pa_m5_affine_metadata.argtypes = [c.c_void_p, c.c_uint32, c.c_void_p, c.c_void_p]
    rng = np.random.default_rng(0x5C0AE)
    cases = []
    for n in (1, 13, 31, 128, 1024):
        for _ in range(16):
            maxima = rng.integers(1, 32769, n)
            multiplier = np.rint((127*2**24)/maxima)
            units = (2**24/multiplier)/256
            # Deliberate repeated units and direct-map collisions are harmless.
            units[::3] = units[0]
            cases.append((units, float(2**rng.uniform(-16, 4))))
    for values in ([0., -0.], [1., -1.], [np.inf, 1.], [np.nan, 1.],
                   [2.**-1074, 2.**-1022], [2.**1010, 2.**1000], [1., 2.**-50]):
        for query in (0., 1., -1., 2.**-30, 2.**30):
            cases.append((np.asarray(values), query))
    for units, query in cases:
        units = np.ascontiguousarray(units, dtype=np.float64)
        with np.errstate(invalid='ignore', over='ignore'):
            scales = np.ascontiguousarray(query*units*32)
        maximum = max(0., *units.tolist())
        a = np.zeros(len(units), np.uint32); b = np.zeros_like(a)
        scratch = np.zeros(len(units), np.float64)
        sa = c.c_uint32(); sb = c.c_uint32()
        expected = baseline.pa_m5_affine_metadata(scales.ctypes.data, len(units), a.ctypes.data, c.byref(sa))
        actual = lib.pa_context_score_metadata(units.ctypes.data, len(units), query, maximum,
            b.ctypes.data, c.byref(sb), scratch.ctypes.data)
        assert actual == expected, (units, query, actual, expected)
        if expected == 0:
            assert sa.value == sb.value
            np.testing.assert_array_equal(a, b)
    print('CONTEXT SCORE METADATA EXACT PASS', len(cases), 'sets; full1024, repeated keys, epoch changes, fallback domains')


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__); p.add_argument('--candidate', required=True)
    check(p.parse_args().candidate)
