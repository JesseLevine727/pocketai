"""Adversarial two-rounding product checks; no tolerance-based comparisons."""
import argparse
import ctypes as c
from pathlib import Path
import numpy as np


def check(path):
    lib = c.CDLL(str(Path(path).resolve()))
    f = lib.pa_context_host_score_product
    f.argtypes = [c.c_double, c.c_double, c.c_uint32]; f.restype = c.c_uint32
    rng = np.random.default_rng(0x20A0D)
    query = np.exp2(rng.uniform(-20, 1, 80000))
    units = np.exp2(rng.uniform(-20, 1, len(query)))
    shifts = rng.integers(0, 32, len(query))
    # Land on and immediately around final integer midpoints. Correctly rounded
    # binary64 products can turn a non-tie exact product into an integer tie.
    q = np.exp2(rng.uniform(-18, -1, 40000)); s = rng.integers(12, 32, len(q))
    middle = rng.integers(0, 2**29, len(q)) + .5
    u = middle/np.ldexp(q, s+5)
    for values in (u, np.nextafter(u, 0), np.nextafter(u, np.inf)):
        query = np.concatenate((query, q)); units = np.concatenate((units, values)); shifts = np.concatenate((shifts, s))
    expected = np.rint(np.ldexp(query*units, shifts+5))
    checked = fallback = 0
    for q, u, s, e in zip(query, units, shifts, expected):
        result = f(q, u, int(s))
        if result == 0xffffffff: fallback += 1; continue
        target = 0x80000000 if e >= 2**31 else int(e)
        assert result == target, (q.hex(), u.hex(), s, result, target)
        checked += 1
    assert checked > 180000
    print('CONTEXT TWO-ROUNDING PRODUCT EXACT PASS', checked, 'values;', fallback, 'generic-fallback cases')


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__); p.add_argument('--library', required=True)
    check(p.parse_args().library)
