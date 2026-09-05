"""Physical/host runtime correctness runner. Diagnostic time is NOT performance."""
import argparse
import hashlib
import json
import resource
import time
from pathlib import Path
import numpy as np
from zynq.m4_offload import Runtime, CpuBackend, CANDIDATE_SHA
from zynq.m4_driver import FpgaBackend
from ref.m4_model_pack import file_sha256


def verify_bundle(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / 'manifest.json').read_text())
    for name, expected in manifest['sha256'].items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory) or file_sha256(path) != expected:
            raise ValueError('staging identity mismatch: ' + name)
    return manifest


def memory_snapshot():
    result = {}
    for name in ('/proc/meminfo', '/proc/self/status', '/proc/self/smaps_rollup'):
        try:
            result[name] = Path(name).read_text()
        except OSError as error:
            result[name] = str(error)
    result['max_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return result


def runtime_cache_digest(runtime):
    digest = hashlib.sha256()
    for layer in range(12):
        k = runtime.k[layer, :, :runtime.length]
        v = runtime.v[layer, :, :runtime.length]
        digest.update(f'{layer}:{k.shape}:<i2'.encode())
        digest.update(np.ascontiguousarray(k, dtype='<i2').tobytes())
        digest.update(np.ascontiguousarray(v, dtype='<i2').tobytes())
    return digest.hexdigest()


class CheckedBackend:
    """Diagnostic-only native checks on actual FPGA operands and results."""
    def __init__(self, actual, oracle):
        self.actual, self.oracle = actual, oracle
        self.counts = actual.counts
        self.checks = 0

    def gemm(self, a, tiles, n):
        result = self.actual.gemm(a, tiles, n)
        np.testing.assert_array_equal(result, self.oracle.gemm(a, tiles, n), err_msg='actual FPGA GEMM')
        self.checks += 1
        return result

    def sfpu(self, descriptor, words):
        result = self.actual.sfpu(descriptor, words)
        np.testing.assert_array_equal(result, self.oracle.sfpu(descriptor, words), err_msg=f'actual FPGA SFPU op={descriptor.op}')
        self.checks += 1
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--backend', choices=('cpu', 'fpga'), default='cpu')
    parser.add_argument('--case', choices=('all', 'single', 'story', 'science', 'computing'), default='all')
    parser.add_argument('--generate', action='store_true')
    parser.add_argument('--boundary', action='store_true')
    parser.add_argument('--check-operators', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('refusing to overwrite runtime qualification evidence')
    stage = args.stage.resolve()
    manifest = verify_bundle(stage)
    fixtures = json.loads((stage / 'fixtures/manifest.json').read_text())
    if fixtures['candidate_sha256'] != CANDIDATE_SHA:
        raise ValueError('wrong reference fixture candidate')
    report = {'status': 'RUNNING', 'backend': args.backend, 'stage_manifest_sha256': file_sha256(stage / 'manifest.json'),
              'sources': manifest, 'numpy': np.__version__, 'before_memory': memory_snapshot(),
              'tensor_cases': [], 'generation': []}
    cpu = CpuBackend(stage / 'm4_cpu_gemm.so', stage / 'm4_cpu_sfpu.so')
    hardware = None
    try:
        backend = cpu
        if args.backend == 'fpga':
            hardware = FpgaBackend(stage / 'm3_pynq.bit')
            backend = CheckedBackend(hardware, cpu) if args.check_operators else hardware
        runtime = Runtime(stage / 'pack', backend)
        report['cache_bytes'] = runtime.cache_bytes
        report['cma_bytes'] = hardware.cma_bytes if hardware is not None else 0
        report['native_cpu_backend'] = cpu.native_gemm.backend
        begin = time.monotonic()
        for case in fixtures['cases']:
            if args.case != 'all' and case['id'] != args.case:
                continue
            runtime.reset()
            checked = []
            def compare(name, actual):
                entry = case['tensors'][name]
                expected = np.load(stage / 'fixtures' / entry['file'], mmap_mode='r', allow_pickle=False)
                np.testing.assert_array_equal(actual, expected, err_msg=case['id'] + ':' + name)
                checked.append(name)
            logits = runtime.prefill(case['input_tokens'], capture=compare)
            compare('logits', logits)
            if runtime_cache_digest(runtime) != case['cache_sha256']:
                raise AssertionError('prefill cache differs from independent reference')
            report['tensor_cases'].append({'id': case['id'], 'tensors': len(checked), 'status': 'EXACT_PASS'})
            print('M4 BOARD RUNTIME EXACT TENSORS/LOGITS/KV PASS', args.backend, case['id'], flush=True)
        if args.generate:
            for case in fixtures['generation']:
                runtime.reset()
                logits = runtime.prefill(case['input_tokens'])
                tokens = []
                for step, expected in enumerate(case['steps']):
                    actual_token = int(logits[-1].argmax())
                    actual_hash = hashlib.sha256(logits.astype('<f8').tobytes()).hexdigest()
                    if (actual_token != expected['token'] or actual_hash != expected['logits_sha256'] or
                            runtime_cache_digest(runtime) != expected['cache_sha256']):
                        raise AssertionError(f'physical generation/logit/KV mismatch {case["id"]} step {step}')
                    tokens.append(actual_token)
                    print('M4 BOARD GENERATION STEP', args.backend, case['id'], step + 1, flush=True)
                    if step + 1 < len(case['steps']):
                        logits = runtime.step([actual_token])
                report['generation'].append({'id': case['id'], 'tokens': tokens, 'status': 'EXACT_20_TOKEN_LOGIT_KV_PASS'})
                print('M4 BOARD GENERATION PASS', args.backend, case['id'], flush=True)
        if args.boundary:
            runtime.reset()
            case = fixtures['boundary']
            logits = None
            for start in range(0, 1024, 16):
                logits = runtime.step(case['input_tokens'][start:start + 16], emit_logits=start == 1008)
                print('M4 BOARD CONTEXT POSITIONS', args.backend, runtime.length, flush=True)
            if (hashlib.sha256(logits.astype('<f8').tobytes()).hexdigest() != case['logits_sha256'] or
                    runtime_cache_digest(runtime) != case['cache_sha256']):
                raise AssertionError('full context differs from frozen reference')
            before = runtime_cache_digest(runtime)
            try:
                runtime.step([0])
            except ValueError:
                pass
            else:
                raise AssertionError('overflow context accepted')
            if runtime_cache_digest(runtime) != before or runtime.length != 1024:
                raise AssertionError('overflow rejection mutated cache')
            report['boundary'] = 'EXACT_1024_PASS_OVERFLOW_REJECTED'
        report['diagnostic_elapsed_seconds'] = time.monotonic() - begin
        report['counts'] = dict(backend.counts)
        report['operator_checks'] = getattr(backend, 'checks', 0)
        report['after_memory'] = memory_snapshot()
        report['status'] = 'RUNTIME_CORRECTNESS_PASS_NOT_PERFORMANCE_OR_M4_CLOSURE'
        report['notes'] = ['Diagnostic wall time includes reference checking and is not inference performance.',
                           'Only explicitly selected tensor/generation/boundary checks are claimed.']
        print('M4 BOARD RUNTIME FINAL', args.backend, report['status'], flush=True)
    except (Exception, KeyboardInterrupt) as error:
        report['status'] = 'INTERRUPTED' if isinstance(error, KeyboardInterrupt) else 'FAIL'
        report['error'] = repr(error)
        raise
    finally:
        if hardware is not None:
            try:
                hardware.close()
            except Exception as error:
                report['status'], report['close_error'] = 'FAIL_DMA_CLEANUP', repr(error)
                args.output.write_text(json.dumps(report, indent=2) + '\n')
                raise
        args.output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
