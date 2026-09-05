"""Supplementary fresh-process first-token observations, with post-clock checks.

Only stdlib imports at module scope: the child imports NumPy/runtime/PYNQ
after the parent's process-launch clock starts. Never competes with main tests.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time

POLICY_SHA = 'd8a013a8e317039c4a928f724ad0033ca677cf658e5422438886be12f6080b7d'
FIXTURE_SHA = '7324fb3a88c9b7340e9aa65ea6dd43f77253f0ddf7e7aca9fb100f47f963c537'
PREFIX = 'M4_COLD_EVENT '


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def policy_at(path):
    if sha(path) != POLICY_SHA:
        raise ValueError('not the frozen supplemental startup policy')
    return json.loads(Path(path).read_text())


def child(args):
    # These imports and LUT/library initialization are inside the parent's
    # launch-to-delivery timing, unlike in the main component timers.
    from zynq.m4_offload import Runtime, CpuBackend
    from zynq.m4_driver import FpgaBackend
    from zynq.m4_run import verify_bundle, memory_snapshot, runtime_cache_digest
    stage = args.stage.resolve()
    policy = policy_at(args.policy)
    hardware = None
    result = {'event': 'result', 'backend': args.backend, 'status': 'RUNNING'}
    try:
        manifest = verify_bundle(stage)
        if sha(stage / 'fixtures/manifest.json') != FIXTURE_SHA:
            raise ValueError('startup uses wrong reference fixtures')
        fixtures = json.loads((stage / 'fixtures/manifest.json').read_text())
        case = next(case for case in fixtures['generation'] if case['id'] == policy['prompt_id'])
        if len(case['input_tokens']) != policy['prompt_tokens']:
            raise ValueError('startup prompt length mismatch')
        if args.backend == 'cpu':
            backend = CpuBackend(stage / 'm4_cpu_gemm.so', stage / 'm4_cpu_sfpu.so')
            if backend.native_gemm.backend != 'ARMv7 NEON int8 widening multiply/int32 accumulate, N16 tiled':
                raise ValueError('startup baseline is not physical ARM native CPU')
        else:
            hardware = backend = FpgaBackend(stage / 'm3_pynq.bit')
        runtime = Runtime(stage / 'pack', backend)
        runtime.reset()
        logits = runtime.prefill(case['input_tokens'])
        token = int(logits[-1].argmax())
        print(PREFIX + json.dumps({'event': 'first_token', 'token': token}), flush=True)
        # Parent acknowledges only after recording delivery time. Otherwise
        # child validation could consume CPU before the parent is scheduled.
        if sys.stdin.readline() != 'DELIVERY_RECORDED\n':
            raise RuntimeError('parent did not acknowledge timed token delivery')
        # Selection was computed from delivered logits, never from this golden.
        expected = case['steps'][0]
        if (token != expected['token'] or hashlib.sha256(logits.astype('<f8').tobytes()).hexdigest() != expected['logits_sha256']
                or runtime_cache_digest(runtime) != expected['cache_sha256']):
            raise AssertionError('startup token/logits/KV differ from frozen reference')
        result.update(status='EXACT_FIRST_TOKEN_LOGIT_KV_PASS', token=token,
                      stage_manifest_sha256=sha(stage / 'manifest.json'),
                      runner_sha256=sha(__file__), sources=manifest,
                      counts=dict(backend.counts), cache_bytes=runtime.cache_bytes,
                      cma_bytes=0 if hardware is None else hardware.cma_bytes,
                      memory=memory_snapshot())
    except (Exception, KeyboardInterrupt) as error:
        result['status'], result['error'] = 'FAIL', repr(error)
        raise
    finally:
        try:
            if hardware is not None:
                hardware.close()
        except Exception as error:
            result['status'], result['close_error'] = 'FAIL_DMA_CLEANUP', repr(error)
            raise
        finally:
            print(PREFIX + json.dumps(result), flush=True)


def measure_process(command, cwd, env, timeout=600):
    """Observe pipe delivery with a bounded wait and graceful-only abort.

    Never SIGKILL a potentially DMA-owning child. A failed graceful abort
    reports its still-live PID, and callers must not start another board job.
    """
    start = time.perf_counter()
    process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               start_new_session=True)  # parent sends one graceful abort, not duplicate terminal signals
    result = {'pid': process.pid, 'first_token_seconds': None, 'token': None,
              'child_result': None, 'raw_child_lines': []}
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    os.set_blocking(process.stdout.fileno(), False)
    pending, total = b'', 0
    try:
        eof = False
        while not eof:
            if time.perf_counter() - start > timeout:
                raise TimeoutError('fresh-process startup observation timed out')
            for key, _ in selector.select(timeout=min(1., max(.001, timeout - (time.perf_counter() - start)))):
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    eof = True
                    break
                total += len(chunk)
                if total > 2 ** 20:
                    raise RuntimeError('unexpectedly large startup child output')
                pending += chunk
                while b'\n' in pending:
                    raw, pending = pending.split(b'\n', 1)
                    line = raw.decode('utf-8', errors='replace')
                    if line.startswith(PREFIX):
                        event = json.loads(line[len(PREFIX):])
                        if event.get('event') == 'first_token':
                            token = event.get('token')
                            if result['token'] is not None or type(token) is not int or not 0 <= token < 50257:
                                raise RuntimeError('invalid or duplicate token-delivery event')
                            delivered = [token]
                            result['first_token_seconds'] = time.perf_counter() - start
                            result['token'] = delivered[0]
                            process.stdin.write(b'DELIVERY_RECORDED\n')
                            process.stdin.flush()
                        elif event.get('event') == 'result':
                            if result['child_result'] is not None:
                                raise RuntimeError('duplicate child result')
                            result['child_result'] = event
                    result['raw_child_lines'].append(line)
        process.wait(timeout=max(.001, timeout - (time.perf_counter() - start)))
        result['full_process_completion_seconds'] = time.perf_counter() - start
        result['exit_code'] = process.returncode
        if (process.returncode or result['token'] is None or not result['child_result'] or
                result['child_result'].get('status') != 'EXACT_FIRST_TOKEN_LOGIT_KV_PASS' or
                result['child_result'].get('token') != result['token']):
            raise RuntimeError('startup process did not complete exact validation and cleanup')
        return result
    except BaseException as error:
        result['error'] = repr(error)
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                result['active_child_pid'] = process.pid
                result['abort_note'] = 'Child still live after graceful abort; do not start competing hardware work.'
        result['exit_code'] = process.poll()
        error.observation = result
        raise
    finally:
        selector.close()
        # If the child remains alive, its PID is preserved above. No forceful
        # termination or new FPGA owner is created by this helper.
        for pipe in (process.stdout, process.stdin):
            try:
                pipe.close()
            except BrokenPipeError:
                pass  # an exited child cannot consume a pending acknowledgement


def completed_prerequisites(stage):
    identity = sha(stage / 'manifest.json')
    benchmark = json.loads((stage / 'benchmark_all.json').read_text())
    if (benchmark['status'] != 'BENCHMARK_SELECTED_PHASES_EXACT_PASS' or benchmark['phase'] != 'all'
            or benchmark['stage_manifest_sha256'] != identity):
        raise ValueError('main benchmark must finish successfully before startup measurements')
    for backend in ('cpu', 'fpga'):
        result = json.loads((stage / f'runtime_{backend}_boundary.json').read_text())
        if (result['status'] != 'RUNTIME_CORRECTNESS_PASS_NOT_PERFORMANCE_OR_M4_CLOSURE' or
                result['boundary'] != 'EXACT_1024_PASS_OVERFLOW_REJECTED' or result['backend'] != backend or
                result['stage_manifest_sha256'] != identity):
            raise ValueError('both physical context tests must finish before startup measurements')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--backend', choices=('cpu', 'fpga'), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        if not args.backend:
            raise ValueError('child backend required')
        return child(args)
    if args.output is None or args.output.exists():
        raise ValueError('a fresh startup evidence output path is required')
    report = {'status': 'RUNNING', 'runner_sha256': sha(__file__), 'policy_sha256': POLICY_SHA,
              'observations': [], 'note': 'n=1 per backend; descriptive process-cold observation, not disk-cold statistics or a cold speedup claim.'}
    try:
        policy = policy_at(args.policy)
        report['policy'] = policy
        if os.environ.get('OPENBLAS_NUM_THREADS') != '1' or os.geteuid() != 0:
            raise ValueError('physical startup comparison requires root and OPENBLAS_NUM_THREADS=1')
        stage = args.stage.resolve()
        completed_prerequisites(stage)
        env = dict(os.environ)
        env['PYTHONPATH'] = str(stage) + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
        for backend in policy['backend_order']:
            command = [sys.executable, str(Path(__file__).resolve()), '--child', '--stage', str(stage),
                       '--policy', str(args.policy.resolve()), '--backend', backend]
            try:
                observation = measure_process(command, stage, env)
            except BaseException as error:
                report['observations'].append({'backend': backend, **getattr(error, 'observation', {'error': repr(error)})})
                raise
            report['observations'].append({'backend': backend, **observation})
            args.output.write_text(json.dumps(report, indent=2) + '\n')
            print('M4 PROCESS-COLD FIRST TOKEN EXACT PASS', backend, flush=True)
        report['status'] = 'PROCESS_COLD_OBSERVATIONS_EXACT_PASS_NOT_DISK_COLD_OR_M4_CLOSURE'
    except BaseException as error:
        report['status'], report['error'] = 'FAIL', repr(error)
        raise
    finally:
        args.output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
