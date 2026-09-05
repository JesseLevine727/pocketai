"""Frozen, paired physical M4 timings. Independent validation is outside clocks."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import time
import numpy as np
from ref.m4_model_pack import file_sha256
from ref.sfpu_stream import Op, SfpuDescriptor, evaluate_and_pack
from zynq.m4_offload import Runtime, CpuBackend, packet_words
from zynq.m4_driver import FpgaBackend
from zynq.m4_run import memory_snapshot, runtime_cache_digest, verify_bundle

POLICY_SHA = '17bcd0a823f551c539525fc54c0f51e759a306f9c346e968de06523b8380d8cf'


class ProfiledBackend:
    """Disjoint complete-call wall spans, including native/DMA delivery."""
    def __init__(self, actual):
        self.actual = actual
        self.counts = actual.counts
        self.wall = Counter()

    def gemm(self, a, tiles, n):
        start = time.perf_counter()
        try:
            return self.actual.gemm(a, tiles, n)
        finally:
            self.wall['gemm_seconds'] += time.perf_counter() - start

    def sfpu(self, descriptor, words):
        start = time.perf_counter()
        try:
            return self.actual.sfpu(descriptor, words)
        finally:
            self.wall['sfpu_seconds'] += time.perf_counter() - start


def differences(after, before):
    return {key: after.get(key, 0) - before.get(key, 0) for key in sorted(set(after) | set(before))}


def statistics(values):
    x = np.asarray(values, dtype=np.float64)
    if x.ndim != 1 or not len(x) or np.any(~np.isfinite(x)) or np.any(x < 0):
        raise ValueError('invalid latency observations')
    return {'n': len(x), 'median': float(np.median(x)), 'p95_linear': float(np.percentile(x, 95)),
            'min': float(x.min()), 'max': float(x.max()), 'mean': float(x.mean()),
            'population_stddev': float(x.std())}


def snapshot_cache(runtime):
    n = runtime.length
    return {'length': n, 'k': runtime.k[:, :, :n].copy(), 'v': runtime.v[:, :, :n].copy(),
            'k8': runtime.k8[:, :, :n].copy(), 'kunits': runtime.kunits[:, :, :n].copy()}


def restore_cache(runtime, saved):
    n = saved['length']
    if not 0 <= n <= runtime.capacity:
        raise ValueError('cache snapshot does not fit runtime')
    # Hardware failures cannot be cleared by restoring software state.
    if getattr(getattr(runtime.backend, 'actual', runtime.backend), 'failed', False):
        raise RuntimeError('cannot benchmark failed hardware')
    for key in ('k', 'v', 'k8', 'kunits'):
        getattr(runtime, key)[:, :, :n] = saved[key]
    runtime.length, runtime.failed = n, False


def check_result(runtime, logits, token, expected, check_cache=True):
    if token != expected['token'] or hashlib.sha256(logits.astype('<f8').tobytes()).hexdigest() != expected['logits_sha256']:
        raise AssertionError('timed token/logits differ from frozen independent reference')
    if check_cache and runtime_cache_digest(runtime) != expected['cache_sha256']:
        raise AssertionError('timed cache differs from frozen independent reference')


def measure(backend, action):
    before_counts, before_wall = dict(backend.counts), dict(backend.wall)
    start = time.perf_counter()
    result = action()
    elapsed = time.perf_counter() - start
    spans = differences(backend.wall, before_wall)
    spans['host_remainder_seconds'] = elapsed - sum(spans.values())
    if spans['host_remainder_seconds'] < 0:
        raise AssertionError('overlapping or invalid profile accounting')
    return result, {'seconds': elapsed, 'wall_profile': spans,
                    'counts': differences(backend.counts, before_counts)}


def fixed_action(runtime, tokens, first_token, workload):
    def run():
        start = time.perf_counter()
        if workload == 'prefill_first_token':
            runtime.reset()
            logits = runtime.prefill(tokens)
        elif workload == 'cached_decode_second_token':
            logits = runtime.step([first_token])
        else:
            raise ValueError('unknown fixed workload')
        compute_end = time.perf_counter()
        delivered = [int(logits[-1].argmax())]
        return logits, delivered, compute_end - start
    return run


def generation_action(runtime, tokens, count):
    def run():
        start = time.perf_counter()
        runtime.reset()
        logits = runtime.prefill(tokens)
        delivered, all_logits, latencies = [], [], []
        step_start = start
        for index in range(count):
            if index:
                logits = runtime.step([delivered[-1]])
            delivered.append(int(logits[-1].argmax()))
            # Keep returned logits for post-clock validation; no goldens or
            # reference arithmetic in the timed loop. This list/bookkeeping
            # overhead remains inside the measured common boundary.
            all_logits.append(logits)
            now = time.perf_counter()
            latencies.append(now - step_start)
            step_start = now
        return delivered, all_logits, latencies
    return run


def paired_order(rng):
    order = ['cpu', 'fpga']
    rng.shuffle(order)
    return order


def summarize(rows):
    result = {}
    for row in rows:
        if row['warmup']:
            continue
        key = row['workload'] + ':' + row['backend']
        result.setdefault(key, []).append(row['seconds'])
    return {key: statistics(values) for key, values in sorted(result.items())}


def save_report(path, report):
    # Owned, newly-created evidence file. Intermediate records survive failures.
    report['summary_seconds'] = summarize(report['trials'])
    path.write_text(json.dumps(report, indent=2) + '\n')


def run_fixed(runtime, backends, fixtures, policy, report, save):
    case = next(c for c in fixtures['generation'] if c['id'] == policy['prompt_id'])
    tokens, steps = case['input_tokens'], case['steps']
    if len(tokens) != policy['prompt_tokens'] or len(steps) != policy['generated_tokens']:
        raise ValueError('frozen workload length mismatch')
    runtime.backend = backends['cpu']
    setup_start = time.perf_counter()
    runtime.reset()
    logits = runtime.prefill(tokens)
    report['untimed_cpu_prefix_setup_seconds'] = time.perf_counter() - setup_start
    check_result(runtime, logits, int(logits[-1].argmax()), steps[0])
    prefix = snapshot_cache(runtime)
    report['untimed_cached_prefix_bytes'] = sum(value.nbytes for value in prefix.values() if isinstance(value, np.ndarray))
    rng = random.Random(policy['paired_order_seed'])
    for iteration in range(policy['warmups'] + policy['fixed_workload_trials']):
        warmup = iteration < policy['warmups']
        for workload in policy['fixed_workloads']:
            for name in paired_order(rng):
                runtime.backend = backend = backends[name]
                if workload == 'cached_decode_second_token':
                    restore_cache(runtime, prefix)
                (logits, delivered, model_seconds), row = measure(backend, fixed_action(runtime, tokens, steps[0]['token'], workload))
                expected = steps[0 if workload == 'prefill_first_token' else 1]
                check_result(runtime, logits, delivered[0], expected)
                row.update(backend=name, workload=workload, iteration=iteration, warmup=warmup,
                           token=delivered[0], model_before_greedy_seconds=model_seconds,
                           status='EXACT_LOGIT_KV_PASS')
                report['trials'].append(row)
                report.setdefault('fixed_backend_memory', {})[name] = memory_snapshot()
                save()
        print('M4 BENCH FIXED PAIR PASS', iteration, 'warmup' if warmup else 'measured', flush=True)


def run_generation(runtime, backends, fixtures, policy, report, save):
    case = next(c for c in fixtures['generation'] if c['id'] == policy['prompt_id'])
    tokens, steps = case['input_tokens'], case['steps']
    rng = random.Random(policy['paired_order_seed'] + 1)
    # Three prefill+decode warmups, not three discarded full generation chains.
    for iteration in range(policy['warmups']):
        for name in paired_order(rng):
            runtime.backend = backend = backends[name]
            (delivered, all_logits, latency), row = measure(backend, generation_action(runtime, tokens, 2))
            for i in range(2):
                check_result(runtime, all_logits[i], delivered[i], steps[i], check_cache=i == 1)
            row.update(backend=name, workload='generation_two_token_warmup', iteration=iteration,
                       warmup=True, status='EXACT_LOGIT_FINAL_KV_PASS')
            report['trials'].append(row)
            report.setdefault('generation_backend_memory', {})[name] = memory_snapshot()
            save()
    for iteration in range(policy['full_generation_trials']):
        for name in paired_order(rng):
            runtime.backend = backend = backends[name]
            (delivered, all_logits, latencies), row = measure(backend, generation_action(runtime, tokens, len(steps)))
            for i, expected in enumerate(steps):
                check_result(runtime, all_logits[i], delivered[i], expected, check_cache=i + 1 == len(steps))
            row.update(backend=name, workload='generation_20_tokens', iteration=iteration, warmup=False,
                       tokens=delivered, token_delivery_seconds=latencies,
                       first_token_seconds=latencies[0], cached_decode_seconds=sum(latencies[1:]),
                       delivered_tokens_per_second=len(steps) / row['seconds'],
                       status='EXACT_20_TOKEN_ALL_LOGITS_FINAL_KV_PASS')
            report['trials'].append(row)
            report.setdefault('generation_backend_memory', {})[name] = memory_snapshot()
            save()
            print('M4 BENCH GENERATION PASS', iteration, name, flush=True)


def primitive_cases(runtime):
    rng = np.random.default_rng(1295270994)
    cases = []
    for k, n, name in ((3072, 16, 'gemm_down_projection_tile'), (768, 17, 'gemm_vocabulary_tail')):
        a = rng.integers(-128, 128, (1, k), dtype=np.int8)
        weights = runtime.pack.linears['h.0.mlp.c_proj' if k == 3072 else 'lm_head'][0][: (n + 15) // 16].copy()
        if n % 16:
            weights[-1, :, n % 16:] = 0
        matrix = weights.transpose(1, 0, 2).reshape(k, -1)[:, :n]
        expected = a.astype(np.int64) @ matrix.astype(np.int64)
        cases.append((name, lambda b, a=a, w=weights, n=n: b.gemm(a, w, n), expected))
    for op in Op:
        length = 13 if op == Op.SOFTMAX else 768 if op == Op.LAYERNORM else 3072
        x = rng.integers(-1500, 1501, length, dtype=np.int32)
        shift, multiplier = 0, 0
        if op == Op.LAYERNORM:
            planes = (x, np.full(length, 4096, np.int32), np.zeros(length, np.int32))
        elif op == Op.SOFTMAX:
            planes = (x, np.ones(length, bool))
        elif op in (Op.AFFINE, Op.AFFINE_GELU):
            shift = 24
            planes = (x, np.full(length, 1 << 23, np.int32), np.zeros(length, np.int32))
        elif op == Op.ADD:
            planes = (x, -x // 2)
        else:
            planes = (x,)
            if op == Op.REQUANT8:
                shift, multiplier = 24, 1 << 20
        descriptor = SfpuDescriptor(op, length, shift, multiplier)
        _, expected_words = evaluate_and_pack(descriptor, planes)
        # Packet packing is inside the operator microbenchmark clock for both.
        cases.append(('sfpu_' + op.name.lower(),
                      lambda b, d=descriptor, p=planes: b.sfpu(d, packet_words(d.op, p)),
                      expected_words.view(np.int32)))
    return cases


def run_primitives(runtime, backends, policy, report, save):
    rng = random.Random(policy['paired_order_seed'] + 2)
    cases = primitive_cases(runtime)
    for name, action, expected in cases:
        for iteration in range(policy['warmups'] + policy['fixed_workload_trials']):
            for backend_name in paired_order(rng):
                backend = backends[backend_name]
                actual, row = measure(backend, lambda: action(backend))
                np.testing.assert_array_equal(actual, expected)
                row.update(backend=backend_name, workload=name, iteration=iteration,
                           warmup=iteration < policy['warmups'], status='EXACT_PASS')
                report['trials'].append(row)
        save()
        print('M4 BENCH PRIMITIVE PASS', name, flush=True)
    inputs = np.random.default_rng(policy['paired_order_seed'])
    for length in (13, 32, 1024):
        raw = inputs.integers(-32768, 32768, (length, 64), dtype=np.int32)
        raw[:, 0] = 0
        runtime.backend = backends['cpu']
        expected = scalar_bridge(runtime, raw)
        for iteration in range(policy['warmups'] + policy['fixed_workload_trials']):
            for backend_name in paired_order(rng):
                runtime.backend = backend = backends[backend_name]
                methods = ['scalar', 'batched']
                rng.shuffle(methods)
                for method in methods:
                    action = (lambda: scalar_bridge(runtime, raw)) if method == 'scalar' else (lambda: runtime.requant_columns(raw, 1 / 256))
                    actual, row = measure(backend, action)
                    np.testing.assert_array_equal(actual[0], expected[0])
                    np.testing.assert_array_equal(actual[1], expected[1])
                    row.update(backend=backend_name, workload=f'v_bridge_{length}x64_{method}', iteration=iteration,
                               warmup=iteration < policy['warmups'], status='EXACT_CODES_UNITS_PASS')
                    report['trials'].append(row)
            save()
        print('M4 BENCH BRIDGE PASS', length, flush=True)


def scalar_bridge(runtime, raw):
    codes = np.empty(raw.shape, dtype=np.int8)
    units = np.empty(raw.shape[1], dtype=np.float64)
    for column in range(raw.shape[1]):
        codes[:, column], units[column] = runtime.requant(raw[:, column], 1 / 256)
    return codes, units


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--phase', choices=('primitives', 'fixed', 'generation', 'all'), default='all')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('refusing to overwrite benchmark evidence')
    if os.environ.get('OPENBLAS_NUM_THREADS') != '1':
        raise ValueError('frozen benchmark requires OPENBLAS_NUM_THREADS=1')
    stage = args.stage.resolve()
    policy_path = stage / 'performance_policy.json'
    if file_sha256(policy_path) != POLICY_SHA:
        raise ValueError('performance policy is not frozen version')
    policy = json.loads(policy_path.read_text())
    report = {'status': 'RUNNING', 'phase': args.phase, 'policy': policy, 'policy_sha256': POLICY_SHA,
              'runner_sha256': file_sha256(__file__), 'platform': platform.uname()._asdict(),
              'python': platform.python_version(), 'numpy': np.__version__, 'trials': [],
              'before_memory': memory_snapshot()}
    hardware = None
    save = lambda: save_report(args.output, report)
    save()
    try:
        start = time.perf_counter()
        report['bundle'] = verify_bundle(stage)
        report['stage_manifest_sha256'] = file_sha256(stage / 'manifest.json')
        if file_sha256(stage / 'fixtures/manifest.json') != policy['fixture_manifest_sha256']:
            raise ValueError('unexpected benchmark fixtures')
        fixtures = json.loads((stage / 'fixtures/manifest.json').read_text())
        report['integrity_scan_seconds'] = time.perf_counter() - start
        start = time.perf_counter()
        cpu = CpuBackend(stage / 'm4_cpu_gemm.so', stage / 'm4_cpu_sfpu.so')
        if cpu.native_gemm.backend != 'ARMv7 NEON int8 widening multiply/int32 accumulate, N16 tiled':
            raise ValueError('physical benchmark requires accepted ARMv7 NEON CPU backend')
        runtime = Runtime(stage / 'pack', cpu)
        report['cpu_runtime_init_seconds'] = time.perf_counter() - start
        start = time.perf_counter()
        hardware = FpgaBackend(stage / 'm3_pynq.bit')
        report['overlay_dma_init_seconds'] = time.perf_counter() - start
        report['cache_bytes'], report['cma_bytes'] = runtime.cache_bytes, hardware.cma_bytes
        report['native_cpu_backend'] = cpu.native_gemm.backend
        backends = {'cpu': ProfiledBackend(cpu), 'fpga': ProfiledBackend(hardware)}
        report['resident_initial_memory'] = memory_snapshot()
        save()
        for name, function in (('primitives', run_primitives), ('fixed', run_fixed), ('generation', run_generation)):
            if args.phase not in (name, 'all'):
                continue
            if name == 'primitives':
                function(runtime, backends, policy, report, save)
            else:
                function(runtime, backends, fixtures, policy, report, save)
            report[name + '_memory'] = memory_snapshot()
            save()
        report['status'] = 'BENCHMARK_SELECTED_PHASES_EXACT_PASS'
        print('M4 BENCH FINAL', args.phase, report['status'], flush=True)
    except (Exception, KeyboardInterrupt) as error:
        report['status'] = 'INTERRUPTED' if isinstance(error, KeyboardInterrupt) else 'FAIL'
        report['error'] = repr(error)
        raise
    finally:
        try:
            if hardware is not None:
                hardware.close()
        except Exception as error:
            report['status'], report['close_error'] = 'FAIL_DMA_CLEANUP', repr(error)
            raise
        finally:
            report['after_memory'] = memory_snapshot()
            save()


if __name__ == '__main__':
    main()
