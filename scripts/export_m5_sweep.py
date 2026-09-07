"""Bounded independent M4 oracle preparation; never executes the FPGA runtime."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import signal
import time

import numpy as np
from scripts.m5_sweep_policy import sha
from zynq.m4_offload import CpuBackend, Runtime
from zynq.m4_run import runtime_cache_digest


def snapshot(runtime, logits):
    return dict(token=int(np.argmax(logits)),
                logits_sha256=hashlib.sha256(logits.astype('<f8').tobytes()).hexdigest(),
                cache_sha256=runtime_cache_digest(runtime))


def expired(*_):
    raise TimeoutError('600-second independent reference preparation guard')


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    args = parser.parse_args()
    out = args.stage / 'references'
    out.mkdir(exist_ok=False)
    policy = json.loads((args.stage/'policy.json').read_text())
    fixture_path = Path('build/m4_runtime_fixtures/manifest.json')
    assert sha(fixture_path) == policy['pinned']['fixtures/manifest.json']
    fixtures = json.loads(fixture_path.read_text())
    report = dict(schema=1, status='PASS', policy_sha256=sha(args.stage/'policy.json'),
                  source='independent previously qualified M4 native operators/runtime',
                  cases={c['id']: c for c in fixtures['generation']}, seeds={}, skips=[],
                  sources={p: sha(p) for p in ('scripts/export_m5_sweep.py', 'zynq/m4_offload.py',
                      'zynq/m4_run.py', 'ref/m4_model_pack.py', 'build/m4_pack_v3/manifest.json',
                      'build/m4_cpu_gemm_host.so', 'build/m4_cpu_sfpu_host.so')})
    started = time.monotonic()

    def save():
        report['elapsed_seconds'] = time.monotonic()-started
        (out/'manifest.json').write_text(json.dumps(report, indent=2)+'\n')

    signal.signal(signal.SIGALRM, expired)
    signal.alarm(policy['reference_budget_seconds'])
    current = 'initialization'
    try:
        # Reuse the exact accepted past-13 independent cache, including its hashes.
        target = out/'p13/seed'
        target.parent.mkdir()
        shutil.copytree('build/m5_opt_seed_v1', target)
        seed = json.loads((target/'manifest.json').read_text())
        assert seed['past'] == 13 and seed['expected'] == report['cases']['story']['steps'][1]
        report['seeds']['13'] = seed
        save()
        runtime = Runtime('build/m4_pack_v3', CpuBackend(
            'build/m4_cpu_gemm_host.so', 'build/m4_cpu_sfpu_host.so'))
        arrays = dict(k=runtime.k, v=runtime.v, k8=runtime.k8, kunits=runtime.kunits)
        story = report['cases']['story']['input_tokens']
        stream = (story * 79)[:1023]
        for n in (1, 16, 32, 64):
            current = f'full_prompt_{n}'
            runtime.reset()
            for array in arrays.values():
                array.fill(0)
            logits = runtime.prefill(stream[:n])
            case = dict(id=f'story_length_{n}', input_tokens=stream[:n],
                        steps=[snapshot(runtime, logits)],
                        scope='synthetic repeated/truncated story tokens; length control, not quality benchmark')
            report['cases'][case['id']] = case
            save()
            print('REFERENCE FULL PASS', n, round(time.monotonic()-started, 2), flush=True)
        # Independent full prefill at each selected length avoids block-boundary assumptions.
        for n in (1, 8, 32, 128, 512, 1023):
            current = f'cached_past_{n}'
            runtime.reset()
            for array in arrays.values():
                array.fill(0)
            logits = runtime.prefill(stream[:n])
            prefix = snapshot(runtime, logits)
            folder = out/f'p{n}/seed'
            folder.mkdir(parents=True)
            seed = dict(schema=1, status='PASS', past=n, input_token=prefix['token'],
                        prefill_logits_sha256=prefix['logits_sha256'],
                        prefill_kv_sha256=prefix['cache_sha256'], arrays={},
                        input_tokens=stream[:n], source=report['source'])
            for name, array in arrays.items():
                path = folder/f'{name}.bin'
                path.write_bytes(np.ascontiguousarray(array, dtype=array.dtype.newbyteorder('<')).tobytes())
                seed['arrays'][name] = dict(file=path.name, bytes=path.stat().st_size, sha256=sha(path))
            seed['expected'] = snapshot(runtime, runtime.step([seed['input_token']]))
            seed['continuation_checked'] = True
            (folder/'manifest.json').write_text(json.dumps(seed, indent=2)+'\n')
            report['seeds'][str(n)] = seed
            save()
            print('REFERENCE CACHE PASS', n, round(time.monotonic()-started, 2), flush=True)
    except TimeoutError as error:
        report['skips'].append(dict(at=current, reason=str(error)))
    except BaseException as error:
        report['status'] = 'FAIL'
        report['error'] = repr(error)
        raise
    finally:
        signal.alarm(0)
        save()
    print('REFERENCE PREPARATION', report['status'], flush=True)


if __name__ == '__main__':
    main()
