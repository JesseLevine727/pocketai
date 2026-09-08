"""Threaded row/alignment/overflow tests for the real generic entry points."""
import argparse
import ctypes as c
from pathlib import Path
import numpy as np
from ref.gpt2_quantized import affine_metadata, dynamic_columns, rne_shift
from ref.gpt2_scaled import storage_exponent


def check(path):
    lib = c.CDLL(str(Path(path).resolve()))
    smooth = lib.pa_startup_smooth_generic
    smooth.argtypes = [c.c_void_p, c.c_uint32, c.c_uint32]+[c.c_void_p]*4+[c.c_uint32, c.c_void_p]
    quant = lib.pa_startup_quant_generic
    quant.argtypes = [c.c_void_p, c.c_uint32, c.c_uint32]+[c.c_void_p]*3+[c.c_uint32, c.c_void_p]
    rng = np.random.default_rng(0xED6E)
    work = c.create_string_buffer(1024*1024); used = c.c_uint32()
    cases = 0
    for columns in (1, 15, 16, 17, 31, 32, 33, 63, 64, 65, 768, 3072):
        for rows in (1, 2, 3, 16):
            for offset in (0, 1):
                count = rows*columns
                storage = rng.integers(-32768, 32768, count+2, dtype=np.int16)
                data = storage[offset:offset+count].reshape(rows, columns)
                if cases % 3 == 0: data[:] //= 256
                if cases % 13 == 0: data.fill(0)
                if cases % 17 == 0: data.flat[0] = -32768
                smoothing = rng.uniform(.25, 4, columns)
                scales = 1/smoothing; multipliers, shift = affine_metadata(scales)
                prospective = rne_shift(data.astype(np.int64)*multipliers, shift)
                expected_exp = np.zeros(rows, np.uint32)
                if np.any((prospective < -32768)|(prospective > 32767)):
                    expected_exp = storage_exponent(np.max(np.abs(data*scales), axis=1)/256).astype(np.uint32)
                expected = []
                for row, exponent in zip(data, expected_exp):
                    m, s = affine_metadata(scales/(2.0**int(exponent)))
                    expected.append(np.clip(rne_shift(row.astype(np.int64)*m, s), -32768, 32767).astype(np.int16))
                output_storage = np.full(count+2, 12345, np.int16)
                output = output_storage[offset:offset+count].reshape(rows, columns)
                exponents = np.full(rows, 12345, np.uint32)
                assert smooth(data.ctypes.data, rows, columns, smoothing.ctypes.data, output.ctypes.data,
                    exponents.ctypes.data, work, len(work), c.byref(used)) == 0
                np.testing.assert_array_equal(output, expected); np.testing.assert_array_equal(exponents, expected_exp)
                assert used.value == 0 and np.all(output_storage[:offset] == 12345) and np.all(output_storage[offset+count:] == 12345)
                output.fill(12345); exponents.fill(12345)
                assert smooth(data.ctypes.data, rows, columns, smoothing.ctypes.data, output.ctypes.data,
                    exponents.ctypes.data, work, 1, c.byref(used)) == -2
                assert used.value == 0 and np.all(output == 12345) and np.all(exponents == 12345)
                q_storage = np.full(count+4, 99, np.int8)
                q = q_storage[offset:offset+count].reshape(rows, columns)
                units = np.full(rows, 12345.0)
                assert quant(data.ctypes.data, rows, columns, q.ctypes.data, units.ctypes.data,
                    work, len(work), c.byref(used)) == 0
                expected_q, expected_units = dynamic_columns(data.T, 1/256)
                np.testing.assert_array_equal(q, expected_q.T); np.testing.assert_array_equal(units, expected_units)
                assert used.value == 0 and np.all(q_storage[:offset] == 99) and np.all(q_storage[offset+count:] == 99)
                q.fill(99); units.fill(12345)
                assert quant(data.ctypes.data, rows, columns, q.ctypes.data, units.ctypes.data,
                    work, 1, c.byref(used)) == -1
                assert used.value == 0 and np.all(q == 99) and np.all(units == 12345)
                cases += 1
    print('STARTUP GENERIC SCALAR EXACT PASS', cases, 'threaded shape/alignment pairs; smooth/quant, overflow, workspace rejection, guards')


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__); p.add_argument('--library', required=True)
    check(p.parse_args().library)
