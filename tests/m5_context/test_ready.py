"""Exercise the bound consumer-ready path, not its legacy fallback."""
import argparse
import ctypes as c
import hashlib
import json
import mmap
from pathlib import Path
import numpy as np
from ref.gpt2_quantized import dynamic_columns

LIMIT = 0x280000
WORK_START = 0x3000


def configure(path):
    lib = c.CDLL(str(Path(path).resolve()))
    lib.pa_m5_host_tables.argtypes = [c.c_void_p, c.c_void_p]
    gelu = np.asarray([int(x, 16) for x in Path('rtl/sfpu/gelu_q8.mem').read_text().split()], dtype=np.uint16)
    exp = np.asarray([int(x, 16) for x in Path('rtl/sfpu/exp_q24.mem').read_text().split()], dtype=np.uint32)
    lib.pa_m5_host_tables(gelu.ctypes.data, exp.ctypes.data)
    lib._tables = (gelu, exp)
    lib.pa_m5_host_attention.argtypes = [c.c_void_p, c.c_uint32] + [c.c_void_p]*4 + [
        c.c_uint32, c.c_void_p, c.c_uint32, c.c_uint32, c.c_void_p, c.c_void_p]
    lib.pa_m5_host_forward.argtypes = [c.c_void_p, c.c_void_p, c.c_uint32] + [c.c_void_p]*5 + [
        c.c_uint32, c.c_uint32, c.c_void_p, c.c_void_p, c.c_void_p]
    return lib


def bind(lib, arrays, work, trace):
    lib.pa_context_host_bind.argtypes = [c.c_void_p]*6 + [c.c_int]
    lib.pa_context_host_bind(*[a.ctypes.data for a in arrays], c.addressof(work), c.addressof(trace), 1)


def digest(arrays, length):
    h = hashlib.sha256()
    for layer in range(12):
        k = np.ascontiguousarray(arrays[0][layer, :, :length], dtype='<i2')
        v = np.ascontiguousarray(arrays[1][layer, :, :length], dtype='<i2')
        h.update(f'{layer}:{k.shape}:<i2'.encode()); h.update(k.tobytes()); h.update(v.tobytes())
    return h.hexdigest()


def check(path):
    base = configure('build/m5_tenth_reciprocal_v1/native.so')
    ready = configure(path)
    rng = np.random.default_rng(0xC07E57)
    shape = (12, 12, 1024, 64)
    cases = 0
    rejections = 0
    for layer, past, row_counts, mode in ((0, 0, (1, 2), 'zero'), (0, 13, (1, 2), 'grow'),
            (2, 31, (2, 1), 'random'), (11, 63, (3, 1), 'grow'),
            (0, 1008, (16,), 'random'), (11, 1022, (1, 1), 'grow')):
        source = [rng.integers(-512, 513, shape, dtype=np.int16),
                  rng.integers(-512, 513, shape, dtype=np.int16),
                  rng.integers(-127, 128, shape, dtype=np.int8),
                  np.full(shape[:-1], 1/256, dtype=np.float64)]
        if mode == 'zero':
            for a in source: a.fill(0)
        arrays = [[a.copy() for a in source] for _ in range(2)]
        works = [c.create_string_buffer(4*1024*1024) for _ in range(2)]
        trace = c.create_string_buffer(8*1024*1024)
        bind(ready, arrays[1], works[1], trace)
        before = tuple(a.tobytes() for a in arrays[1])
        qkv_probe = np.zeros((1, 2304), np.int16); context_probe = np.full((1, 768), 12345, np.int16)
        high_probe = c.c_uint32()
        assert ready.pa_m5_host_attention(c.addressof(works[1])+WORK_START, 128,
            *[a.ctypes.data for a in arrays[1]], layer, qkv_probe.ctypes.data, 1, past,
            context_probe.ctypes.data, c.byref(high_probe)) == -2
        assert before == tuple(a.tobytes() for a in arrays[1]) and np.all(context_probe == 12345)
        assert bytes(trace) == bytes(len(trace))
        del before
        rejections += 1
        for ordinal, rows in enumerate(row_counts):
            qkv = rng.integers(-512, 513, (rows, 2304), dtype=np.int16)
            if mode == 'zero' and ordinal == 0: qkv.fill(0)
            if mode == 'grow':
                qkv[:, 1536::4] = -32768 if ordinal else 1024
                qkv[:, 1537::4] = 32767 if ordinal else -1024
            outputs = []
            for lib, cache, work in zip((base, ready), arrays, works):
                context = np.full((rows, 768), 12345, dtype=np.int16)
                high = c.c_uint32()
                status = lib.pa_m5_host_attention(c.addressof(work)+WORK_START, LIMIT-WORK_START,
                    *[a.ctypes.data for a in cache], layer, qkv.ctypes.data, rows, past,
                    context.ctypes.data, c.byref(high))
                assert status == 0, (layer, past, rows, status)
                outputs.append(context)
            np.testing.assert_array_equal(*outputs)
            for i in (0, 1, 3): np.testing.assert_array_equal(arrays[0][i], arrays[1][i])
            length = past+rows
            logical = arrays[1][2][layer].reshape(12, 64, 64, 16).transpose(0, 1, 3, 2).reshape(12, 1024, 64)
            np.testing.assert_array_equal(logical[:, :length], arrays[0][2][layer, :, :length])
            for head in range(12):
                index = layer*12+head
                address = (c.addressof(works[1])+LIMIT+index*65536 if index < 24 else
                           c.addressof(trace)+0x80000+(index-24)*65536)
                raw = np.ctypeslib.as_array((c.c_int8*65536).from_address(address))
                values = raw.reshape(4, 1024, 16).transpose(1, 0, 2).reshape(1024, 64)
                expected, _ = dynamic_columns(arrays[0][1][layer, head, :length], 1/256)
                np.testing.assert_array_equal(values[:length], expected)
            valid = np.ctypeslib.as_array((c.c_uint32*144).from_address(c.addressof(trace)+0x60008))
            assert np.all(valid[layer*12:layer*12+12] == length)
            past = length; cases += 1
            before = tuple(a.tobytes() for a in arrays[1]); saved_trace = bytes(trace)
            assert ready.pa_m5_host_attention(c.addressof(works[1])+WORK_START, LIMIT-WORK_START,
                *[a.ctypes.data for a in arrays[1]], layer, qkv_probe.ctypes.data, 1, 1024,
                context_probe.ctypes.data, c.byref(high_probe)) == -1
            assert before == tuple(a.tobytes() for a in arrays[1]) and saved_trace == bytes(trace)
            assert np.all(context_probe == 12345)
            del before, saved_trace
            rejections += 1
    print('CONTEXT READY ATTENTION EXACT PASS', cases, 'incremental calls; full1024, tails, zero/extremes, both V segments', flush=True)
    print('CONTEXT READY REJECTION PASS', rejections, 'small-workspace and full-context overflow; all cache/derived state unchanged', flush=True)

    arrays = [np.zeros(shape, np.int16), np.zeros(shape, np.int16),
              np.zeros(shape, np.int8), np.zeros(shape[:-1], np.float64)]
    work = c.create_string_buffer(4*1024*1024); trace = c.create_string_buffer(8*1024*1024)
    bind(ready, arrays, work, trace)
    fixtures = json.loads(Path('build/m4_runtime_fixtures/manifest.json').read_text())
    total = 0
    with Path('build/m5_arena.1Org4t/model/model.bin').open('rb') as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_COPY) as model:
            backing = (c.c_ubyte*len(model)).from_buffer(model)
            for case in fixtures['generation']:
                for a in arrays: a.fill(0)
                past = 0
                for n, expected in enumerate(case['steps']):
                    tokens = np.asarray(case['input_tokens'] if n == 0 else [case['steps'][n-1]['token']], np.uint32)
                    logits = np.zeros(50257, np.int16); exponent = c.c_uint32(); high = c.c_uint32()
                    status = ready.pa_m5_host_forward(backing, c.addressof(work)+WORK_START, LIMIT-WORK_START,
                        *[a.ctypes.data for a in arrays], tokens.ctypes.data, len(tokens), past,
                        logits.ctypes.data, c.byref(exponent), c.byref(high))
                    assert status == 0, (case['id'], n, status)
                    past += len(tokens)
                    logical = logits.astype(np.float64)*(2.0**exponent.value/256)
                    assert hashlib.sha256(logical.astype('<f8').tobytes()).hexdigest() == expected['logits_sha256']
                    assert int(np.argmax(logits)) == expected['token']
                    assert digest(arrays, past) == expected['cache_sha256']
                    assert high.value <= LIMIT-WORK_START
                    total += 1
            del backing
    print('CONTEXT READY FULL MODEL EXACT PASS', total, 'generation outputs; all logits and full valid KV', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__); parser.add_argument('--candidate', required=True)
    check(parser.parse_args().candidate)
