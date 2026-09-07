"""Exact lazy-table domain, zero/out-of-domain fallback, reset and ownership."""
import argparse
import ctypes as c
from pathlib import Path
import struct


class Workspace(c.Structure):
    _fields_ = [('base', c.c_void_p), ('capacity', c.c_uint32),
                ('used', c.c_uint32), ('high_water', c.c_uint32)]


def check(path):
    lib = c.CDLL(str(Path(path).resolve()))
    lib.pa_scalar_cache_begin.argtypes = [c.POINTER(Workspace)]
    lib.pa_scalar_cache_end.argtypes = []
    lib.pa_scalar_dynamic.argtypes = [c.c_uint32, c.c_uint32, c.POINTER(c.c_uint32)]
    lib.pa_scalar_dynamic.restype = c.c_double
    lib.pa_m5_workspace_open.argtypes = [c.POINTER(Workspace), c.c_void_p, c.c_uint32]
    lib.pa_m5_workspace_rewind.argtypes = [c.POINTER(Workspace), c.c_uint32]
    hits = c.c_uint32.in_dll(lib, 'pa_scalar_cache_hits')
    misses = c.c_uint32.in_dll(lib, 'pa_scalar_cache_misses')
    storage = c.create_string_buffer(4*1024*1024+64)
    aligned = (c.addressof(storage)+63) & ~63
    multiplier = c.c_uint32()
    cases = 0
    for capacity in (4096, 3*1024*1024-1, 3*1024*1024, 4*1024*1024):
        work = Workspace()
        lib.pa_m5_workspace_open(c.byref(work), aligned, capacity)
        lib.pa_scalar_cache_begin(c.byref(work))
        allocated = work.used
        assert bool(allocated) == (capacity >= 3*1024*1024)
        assert work.used <= capacity
        for repeat in range(2):
            for maximum in list(range(32769)) + [32769, 65536, 2**31, 2**32-1]:
                if maximum:
                    q, r = divmod(127<<24, maximum)
                    expected = q + (r > maximum-r or (r == maximum-r and q & 1))
                else:
                    expected = 0
                for shift in (8, 15):
                    unit = lib.pa_scalar_dynamic(maximum, shift, c.byref(multiplier))
                    assert multiplier.value == expected, (maximum, repeat, shift)
                    reference = (16777216.0/expected)*2.**-shift if expected else 1.0
                    assert struct.pack('<d', unit) == struct.pack('<d', reference)
                    cases += 1
        assert hits.value == (3*32768 if allocated else 0)
        assert misses.value == ((32768 if allocated else 4*32768)+16)
        lib.pa_scalar_cache_end()
        lib.pa_m5_workspace_rewind(c.byref(work), 0)
        # Poison the now-unowned table; the fallback must not observe it.
        c.memset(aligned, 0xa5, allocated)
        value = lib.pa_scalar_dynamic(100, 8, c.byref(multiplier))
        assert multiplier.value == 21307064 and value > 0
        assert work.used == 0
    lib.pa_scalar_cache_begin(None)
    lib.pa_scalar_cache_end()
    print('M5 SCALAR CACHE EXACT PASS', cases, 'unit/multiplier comparisons; bounds, fallback, invalidation and poisoned rewind')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--candidate', required=True)
    check(parser.parse_args().candidate)
