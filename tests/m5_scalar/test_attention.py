"""Short operator-only layout checks, including tile tails and full KV capacity."""
import argparse
import ctypes as c
from pathlib import Path
import numpy as np


def check(candidate):
    libraries = [c.CDLL(str(Path(path).resolve())) for path in
                 ('build/m5_iterate_c3_v1/native.so', candidate)]
    i16p = c.POINTER(c.c_int16); u32p = c.POINTER(c.c_uint32)
    gelu = np.asarray([int(x, 16) for x in Path('rtl/sfpu/gelu_q8.mem').read_text().split()], dtype=np.uint16)
    exp = np.asarray([int(x, 16) for x in Path('rtl/sfpu/exp_q24.mem').read_text().split()], dtype=np.uint32)
    for lib in libraries:
        lib.pa_m5_host_tables.argtypes = [i16p, u32p]
        lib.pa_m5_host_tables(gelu.ctypes.data_as(i16p), exp.ctypes.data_as(u32p))
        lib.pa_m5_host_attention.argtypes = [c.c_void_p, c.c_uint32, c.c_void_p,
            c.c_void_p, c.c_void_p, c.c_void_p, c.c_uint32, c.c_void_p,
            c.c_uint32, c.c_uint32, c.c_void_p, u32p]
        lib.pa_m5_host_attention.restype = c.c_int
    rng = np.random.default_rng(0x5ca1a2)
    cases = 0
    for past, rows in ((0, 1), (13, 1), (15, 2), (63, 3), (1008, 16)):
        keys = rng.integers(-512, 513, (12, 1024, 64), dtype=np.int16)
        values = rng.integers(-512, 513, keys.shape, dtype=np.int16)
        k8 = rng.integers(-127, 128, keys.shape, dtype=np.int8)
        units = np.full((12, 1024), 1/256, dtype=np.float64)
        qkv = rng.integers(-512, 513, (rows, 2304), dtype=np.int16)
        qkv.flat[0] = -32768; qkv.flat[-1] = 32767
        for capacity in (128, 160000, 1024*1024):
            outputs = []
            for lib in libraries:
                arrays = [a.copy() for a in (keys, values, k8, units)]
                context = np.full((rows, 768), 12345, dtype=np.int16)
                work = c.create_string_buffer(capacity+64)
                aligned = (c.addressof(work)+63) & ~63
                high_water = c.c_uint32()
                status = lib.pa_m5_host_attention(aligned, capacity,
                    *[a.ctypes.data for a in arrays], 0, qkv.ctypes.data,
                    rows, past, context.ctypes.data, c.byref(high_water))
                outputs.append((status, high_water.value, context.tobytes(),
                                tuple(a.tobytes() for a in arrays)))
            assert outputs[0] == outputs[1], (past, rows, capacity, outputs[0][:2], outputs[1][:2])
            if capacity == 1024*1024: assert outputs[0][0] == 0
            cases += 1
    print('M5 SCALAR ATTENTION LAYOUT EXACT PASS', cases,
          'complete operator/cache/error comparisons, through valid1024 (not a full-model endurance run)')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--candidate', required=True)
    check(parser.parse_args().candidate)
