"""Native-only branch coverage on original prompts; never board timing evidence."""
import argparse
import ctypes as c
import hashlib
import json
import mmap
from pathlib import Path
import subprocess

import numpy as np

from scripts.m5_iterate_sources import once
from scripts.m5_sweep_policy import sha
from tests.m5_context.test_ready import bind, configure, digest, LIMIT, WORK_START


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); a.output.mkdir(exist_ok=False)
    generated = a.build/'generated'
    ops = '#include <stdint.h>\nuint32_t startup_rows[1024][9], startup_count;\n'+(generated/'attention_ops.c').read_text()
    rolling = 'uint32_t cached_exponent = UINT32_MAX;' in ops
    ops = once(ops, '    if (fast < 0) { pa_m5_workspace_rewind(workspace, mark); return fast; }', '''    if (startup_count < 1024) {
      uint32_t *entry = startup_rows[startup_count++];
      entry[0] = n; entry[1] = rows; entry[2] = scaled; entry[3] = residual != 0;
      entry[4] = row; entry[5] = bias_cache != 0; entry[6] = (uint32_t)fast;
      entry[7] = residual ? residual_exponents[row] : 0;
      entry[8] = STARTUP_COVERAGE_REUSE;
    }
    if (fast < 0) { pa_m5_workspace_rewind(workspace, mark); return fast; }''')
    ops = once(ops, 'STARTUP_COVERAGE_REUSE',
        'bias_cache && cached_exponent == residual_exponents[row]' if rolling else 'bias_cache && row != 0')
    instrumented = a.output/'attention_ops.c'; instrumented.write_text(ops)
    sources = [str(generated/name) for name in ('numerics.c', 'requant.c', 'runtime.c', 'cache.c', 'ready_cache.c')]
    sources += [str(instrumented), 'runtime/m5/pa_m5_model.c',
        'runtime/m5_context/score_parallel.c', 'runtime/m5_context/smooth_cache.c',
        'runtime/m5_context/local_scores.c', 'runtime/m5_context/parallel.c',
        'tests/m5/model_ops_host.c', 'tests/m5_scalar/quantize_host.c', 'zynq/m4_cpu_sfpu.c',
        'tests/m5_context/host.c', 'tests/m5_startup/ops_host.c']
    flags = ['-DPA_CONTEXT_'+name for name in ('SMOOTH_CACHE', 'SCORE_PRODUCT', 'LOCAL_SCORES',
        'PARALLEL_VALUES', 'POSITION_VALUES', 'COMBINED_SCORES', 'MASKED_VALUES', 'TEST_THREADS')]
    includes = ['-I'+str(generated)]+['-Iruntime/'+name for name in
        ('m5_startup', 'm5', 'm5_fast', 'm5_scalar', 'm5_search', 'm5_tenth', 'm5_context')]
    library = a.output/'native.so'
    command = ['gcc', '-std=c11', '-O2', '-fPIC', '-shared', '-Wall', '-Wextra', '-Werror',
        '-fno-fast-math', '-pthread', *includes, *flags, *sources, '-lm', '-o', str(library)]
    subprocess.run(command, check=True)
    lib = configure(library)
    count = c.c_uint32.in_dll(lib, 'startup_count')
    records = np.ctypeslib.as_array(((c.c_uint32*9)*1024).in_dll(lib, 'startup_rows'))
    fixtures = json.loads(Path('build/m4_runtime_fixtures/manifest.json').read_text())
    model = Path('build/m5_arena.1Org4t/model/model.bin')
    result = dict(scope='native exact operator coverage, not FPGA time',
        inputs={str(Path(x)): sha(Path(x)) for x in sources}, instrumented_sha256=sha(instrumented),
        model_sha256=sha(model), command=command, cases=[])
    for case in fixtures['generation']:
        arrays = [np.zeros((12, 12, 1024, 64), dtype) for dtype in (np.int16, np.int16, np.int8)]
        arrays.append(np.zeros((12, 12, 1024), np.float64))
        work = c.create_string_buffer(4*1024*1024); trace = c.create_string_buffer(8*1024*1024)
        bind(lib, arrays, work, trace)
        count.value = 0
        tokens = np.asarray(case['input_tokens'], np.uint32)
        logits = np.zeros(50257, np.int16); exponent = c.c_uint32(); high = c.c_uint32()
        with model.open('rb') as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_COPY) as memory:
            backing = (c.c_uint8*len(memory)).from_buffer(memory)
            status = lib.pa_m5_host_forward(backing, c.addressof(work)+WORK_START, LIMIT-WORK_START,
                *[x.ctypes.data for x in arrays], tokens.ctypes.data, len(tokens), 0,
                logits.ctypes.data, c.byref(exponent), c.byref(high))
            del backing
        expected = case['steps'][0]
        assert status == 0 and count.value < 1024
        logical = logits.astype(np.float64)*(2.0**exponent.value/256)
        assert hashlib.sha256(logical.astype('<f8').tobytes()).hexdigest() == expected['logits_sha256']
        assert int(np.argmax(logits)) == expected['token'] and digest(arrays, len(tokens)) == expected['cache_sha256']
        rows = records[:count.value].copy()
        summary = dict(case=case['id'], status='EXACT PASS', rows=len(rows),
            fast=int(np.sum(rows[:, 6] == 1)), cached=int(np.sum(rows[:, 5] != 0)),
            residual_rows=int(np.sum(rows[:, 3] != 0)),
            reused=int(np.sum(rows[:, 8] != 0)),
            columns=['n', 'rows', 'scaled', 'residual', 'row', 'cache', 'fast', 'residual_exponent', 'reuse'],
            records=rows.tolist())
        result['cases'].append(summary)
        print({k: v for k, v in summary.items() if k not in ('columns', 'records')}, flush=True)
    (a.output/'coverage.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__': main()
