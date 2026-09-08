"""Retain frozen end-to-end checks, but validate the explicit lazy V contract.

Every materialized row is exact. Poison every unmaterialized row between calls;
outputs must still match the independent eager implementation at every step.
"""
import argparse
import ctypes as c
import hashlib
from pathlib import Path
import numpy as np
from ref.gpt2_quantized import dynamic_columns

READY_TEST = 'e4430817e2c122d63c4c6170d05fd089632798b0fa2f8698da8048275a790191'


def lazy_check(raw, expected, index, length, trace):
    address = c.addressof(trace)
    assert c.c_uint32.from_address(address+0x60004).value == 2
    bitmap = np.ctypeslib.as_array((c.c_uint32*32).from_address(address+0x2b200+index*128))
    positions = np.arange(1024)
    present = ((bitmap[positions//32] >> (positions%32)) & 1).astype(bool)
    assert not np.any(present[length:]), 'materialized beyond valid raw prefix'
    values = raw.reshape(4, 1024, 16).transpose(1, 0, 2).reshape(1024, 64)
    np.testing.assert_array_equal(values[:length][present[:length]], expected[present[:length]])
    # Write through the actual packed layout, not the reshaped logical copy.
    packed = raw.reshape(4, 1024, 16)
    missing = positions[:length][~present[:length]]
    packed[:, missing, :] = np.where(missing[None, :, None] % 2, 127, -128)
    return present


def check(path):
    original = Path('tests/m5_context/test_ready.py').read_bytes()
    assert hashlib.sha256(original).hexdigest() == READY_TEST
    old = '                np.testing.assert_array_equal(values[:length], expected)'
    assert original.decode().count(old) == 1
    source = original.decode().replace(old,
        '                lazy_check(raw, expected, index, length, trace)')
    marker = '            qkv = rng.integers(-512, 513, (rows, 2304), dtype=np.int16)'
    assert source.count(marker) == 1
    source = source.replace(marker, marker+'''
            if ordinal & 1:
                unaligned = np.empty(rows*2304+1, np.int16)
                unaligned[1:] = qkv.reshape(-1)
                qkv = unaligned[1:].reshape(rows, 2304)
                assert qkv.ctypes.data % 4 == 2''')
    scope = {'__name__': 'startup_lazy_frozen_checks', 'lazy_check': lazy_check}
    exec(compile(source, 'tests/m5_context/test_ready.py [lazy-contract derivation]', 'exec'), scope)
    scope['check'](path)

    class Cache(c.Structure):
        _fields_ = [(name, c.c_void_p) for name in ('keys', 'values', 'keys_i8', 'key_units')]

    lib = scope['configure'](path)
    lib.pa_context_prepare.argtypes = [c.POINTER(Cache), c.c_uint32, c.c_uint32]
    lib.pa_context_update_values.argtypes = [c.POINTER(Cache), c.c_uint32, c.c_uint32, c.c_uint32]
    lib.pa_startup_require_values.argtypes = [c.POINTER(Cache), c.c_uint32, c.c_uint32, c.c_uint32, c.c_void_p]
    shape = (12, 12, 1024, 64)
    arrays = [np.zeros(shape, np.int16), np.zeros(shape, np.int16),
              np.zeros(shape, np.int8), np.zeros(shape[:-1], np.float64)]
    work = c.create_string_buffer(4*1024*1024); trace = c.create_string_buffer(8*1024*1024)
    scope['bind'](lib, arrays, work, trace)
    cache = Cache(*[a.ctypes.data for a in arrays])
    rng = np.random.default_rng(0x1A2E)
    calls = 0
    for length in (1, 15, 16, 17, 31, 32, 1008, 1023):
        trace[0x60000:0x60008] = bytes(8)
        arrays[1][0] = rng.integers(-256, 257, (12, 1024, 64), dtype=np.int16)
        assert lib.pa_context_prepare(c.byref(cache), 0, length) == 0
        raw = np.ctypeslib.as_array((c.c_int8*65536).from_address(c.addressof(work)+0x280000))
        expected, _ = dynamic_columns(arrays[1][0, 0, :length], 1/256)
        assert not lazy_check(raw, expected, 0, length, trace).any()
        for pattern in ('zero', 'sparse', 'dense'):
            probability = np.zeros(length, np.int8)
            if pattern == 'sparse': probability[::7] = 127
            if pattern == 'dense': probability[:] = 1
            assert lib.pa_startup_require_values(c.byref(cache), 0, 0, length, probability.ctypes.data) == 0
            present = lazy_check(raw, expected, 0, length, trace)
            assert np.all(present[:length][probability != 0])
            if pattern == 'zero': assert not present.any()
            calls += 1
        # A single changed feature invalidates all prior rows. Full-prefix
        # quantization still determines units, even when only one row is needed.
        arrays[1][0, 0, length, 0] = -32768
        arrays[1][0, 0, length, 1] = 32767
        assert lib.pa_context_update_values(c.byref(cache), 0, 0, length) == 0
        expected, _ = dynamic_columns(arrays[1][0, 0, :length+1], 1/256)
        assert not lazy_check(raw, expected, 0, length+1, trace).any()
        probability = np.zeros(length+1, np.int8); probability[-1] = 127
        assert lib.pa_startup_require_values(c.byref(cache), 0, 0, length+1, probability.ctypes.data) == 0
        present = lazy_check(raw, expected, 0, length+1, trace)
        assert present.sum() == 1 and present[length]
        saved = bytes(trace); saved_values = raw.tobytes()
        for invalid in (0, 1025, length):
            assert lib.pa_startup_require_values(c.byref(cache), 0, 0, invalid, probability.ctypes.data) < 0
            assert bytes(trace) == saved and raw.tobytes() == saved_values
        calls += 1
    print('STARTUP LAZY CONTRACT PASS', calls, 'zero/sparse/dense demands, poisoned absent rows, max-change invalidation, full1024, non-mutation')


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__); p.add_argument('--candidate', required=True)
    check(p.parse_args().candidate)
