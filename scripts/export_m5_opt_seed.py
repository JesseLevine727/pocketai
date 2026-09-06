"""Export a short, independently checked M4-runtime cache for M5 decode profiling."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from ref.m4_model_pack import file_sha256
from zynq.m4_offload import CpuBackend, Runtime
from zynq.m4_run import runtime_cache_digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('use a fresh seed directory')
    policy_path = Path('tests/m5_opt/performance_policy.json')
    policy = json.loads(policy_path.read_text())
    fixture_path = Path('build/m4_runtime_fixtures/manifest.json')
    if file_sha256(fixture_path) != policy['reference_manifest_sha256']:
        raise ValueError('frozen reference changed')
    fixture = json.loads(fixture_path.read_text())
    case = next(c for c in fixture['generation'] if c['id'] == policy['fixed_decode']['prompt'])
    runtime = Runtime('build/m4_pack_v3', CpuBackend(
        'build/m4_cpu_gemm_host.so', 'build/m4_cpu_sfpu_host.so'))
    arrays = {'k': runtime.k, 'v': runtime.v, 'k8': runtime.k8, 'kunits': runtime.kunits}
    for array in arrays.values():
        array.fill(0)
    logits = runtime.prefill(case['input_tokens'])
    logits_hash = hashlib.sha256(logits.astype('<f8').tobytes()).hexdigest()
    kv_hash = runtime_cache_digest(runtime)
    if (logits_hash != case['steps'][0]['logits_sha256'] or
            kv_hash != case['steps'][0]['cache_sha256'] or
            int(np.argmax(logits)) != policy['fixed_decode']['input_token'] or
            runtime.length != policy['fixed_decode']['past']):
        raise ValueError('independent seed does not match frozen prefill')
    args.output.mkdir(parents=True)
    report = {'schema': 1, 'status': 'PASS', 'source': 'independent frozen M4 native runtime',
              'scope': 'fixed-context seeded decode; not physical empty-cache endurance',
              'policy_sha256': file_sha256(policy_path),
              'fixture_sha256': file_sha256(fixture_path), 'past': runtime.length,
              'input_token': policy['fixed_decode']['input_token'],
              'prefill_logits_sha256': logits_hash, 'prefill_kv_sha256': kv_hash,
              'expected': case['steps'][1], 'arrays': {},
              'sources': {name: file_sha256(name) for name in (
                  __file__, 'zynq/m4_offload.py', 'ref/m4_model_pack.py',
                  'build/m4_pack_v3/manifest.json', 'build/m4_cpu_gemm_host.so',
                  'build/m4_cpu_sfpu_host.so')}}
    for name, array in arrays.items():
        path = args.output / (name + '.bin')
        payload = np.ascontiguousarray(array, dtype=array.dtype.newbyteorder('<')).tobytes()
        path.write_bytes(payload)
        report['arrays'][name] = {'file': path.name, 'bytes': len(payload),
                                  'sha256': file_sha256(path)}
    next_logits = runtime.step([report['input_token']])
    if (hashlib.sha256(next_logits.astype('<f8').tobytes()).hexdigest() != report['expected']['logits_sha256'] or
            runtime_cache_digest(runtime) != report['expected']['cache_sha256'] or
            int(np.argmax(next_logits)) != report['expected']['token']):
        raise ValueError('independent seeded continuation does not match frozen reference')
    report['continuation_checked'] = True
    (args.output / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print('M5 OPT INDEPENDENT SEED PASS', args.output, flush=True)


if __name__ == '__main__':
    main()
