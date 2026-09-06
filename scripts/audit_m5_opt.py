"""Read-only audit of bounded M5 optimization evidence; never accesses the board."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATHS = {'baseline': 'build/m5_opt_profile/profile_baseline.json',
                'shift': 'build/m5_opt_shift/profile_shift.json',
                'metadata': 'build/m5_opt_metadata/profile_metadata.json',
                'reuse': 'build/m5_opt_reuse/profile_reuse.json',
                'complete': 'build/m5_opt_runtime/physical_complete.json',
                'release': 'build/m5_opt_runtime/release.json',
                'probes': 'build/m5_opt_probe/probe_results.json',
                'precision': 'build/m5_opt_profile/precision_screen.json'}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(4 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def statistics_for(report):
    measured = [r for r in report['runs'] if r['role'].startswith('unprofiled_measured_')]
    result = {}
    for field in ('model_seconds', 'host_request_through_delivery_seconds'):
        values = [r[field] for r in measured]
        result[field] = {'samples': values, 'mean': statistics.mean(values),
                         'median': statistics.median(values), 'min': min(values),
                         'max': max(values), 'population_stddev': statistics.pstdev(values),
                         'aggregate_tokens_per_second': len(values)/sum(values)}
    result['profiling_model_overhead_seconds'] = report['runs'][0]['model_seconds'] - result['model_seconds']['mean']
    return result


def validate(evidence):
    require(evidence['schema'] == 1 and evidence['status'] == 'PASS', 'optimization not qualified')
    for collection in ('sources', 'artifacts'):
        for path, digest in evidence[collection].items():
            require(sha(ROOT/path) == digest, f'stale {collection}: {path}')
    for key, path in REPORT_PATHS.items():
        embedded = evidence['decode'][key] if key in ('baseline', 'shift', 'metadata', 'reuse') else evidence[key]
        require(embedded == json.loads((ROOT/path).read_text()), f'embedded report differs from original: {key}')
    policy = json.loads((ROOT/'tests/m5_opt/performance_policy.json').read_text())
    require(evidence['policy'] == policy, 'measurement policy changed')
    seed = json.loads((ROOT/'build/m5_opt_seed_v1/manifest.json').read_text())
    require(seed['status'] == 'PASS' and seed['continuation_checked'], 'unqualified independent seed')
    require(seed['policy_sha256'] == sha(ROOT/'tests/m5_opt/performance_policy.json'), 'seed policy mismatch')
    require(seed['fixture_sha256'] == policy['reference_manifest_sha256'] ==
            sha(ROOT/'build/m4_runtime_fixtures/manifest.json'), 'independent fixture identity mismatch')
    for name, entry in seed['arrays'].items():
        path = ROOT/'build/m5_opt_seed_v1'/entry['file']
        require(name in ('k', 'v', 'k8', 'kunits') and path.stat().st_size == entry['bytes'] and
                sha(path) == entry['sha256'], 'seed payload mismatch')
    for path, digest in seed['sources'].items():
        require(sha(ROOT/path) == digest, 'independent seed source mismatch: ' + path)
    old = json.loads((ROOT/'docs/m5_closure_evidence.json').read_text())
    hardware_dir = ROOT/old['hardware']['directory']
    bit, hwh = sha(hardware_dir/'m5_pynq.bit'), sha(hardware_dir/'m5_pynq.hwh')
    variants = {'baseline': 'm5_opt_profile', 'shift': 'm5_opt_shift',
                'metadata': 'm5_opt_metadata', 'reuse': 'm5_opt_reuse'}
    for name, directory in variants.items():
        report = evidence['decode'][name]
        require(report['status'] == 'PASS' and report['dma_after_return']['owner'] == 0 and
                not report.get('cleanup_error'), f'{name} decode/lifecycle failure')
        require(report['policy'] == policy and report['sha256']['m5_pynq.bit'] == bit and
                report['sha256']['m5_pynq.hwh'] == hwh, f'{name} measurement/overlay mismatch')
        require(report['seed_manifest_sha256'] == sha(ROOT/'build/m5_opt_seed_v1/manifest.json') and
                report['sha256']['m5_opt_profile.py'] == sha(ROOT/'zynq/m5_opt_profile.py') and
                report['sha256']['m5_run.py'] == sha(ROOT/'zynq/m5_run.py'), f'{name} seed/runner identity mismatch')
        firmware = sha(ROOT/'build'/directory/'m5_profile.bin')
        require(report['sha256']['m5_profile.bin'] == firmware, f'{name} wrong firmware')
        require([r['role'] for r in report['runs']] == policy['fixed_decode']['initial_order'], 'missing/cherry-picked samples')
        for index, run in enumerate(report['runs']):
            require(run['status'] == 'PASS' and run['firmware_sha256'] == firmware and
                    run['token'] == seed['expected']['token'] and run['cache_valid'] == 14 and
                    run['logits_sha256'] == seed['expected']['logits_sha256'] and
                    run['kv_sha256'] == seed['expected']['cache_sha256'], f'{name} reference mismatch')
            require(0 < run['model_seconds'] < run['host_request_through_delivery_seconds'] < 120, 'decode time/boundary mismatch')
            require(run['profile_enabled'] == (index == 0), 'profiling state mismatch')
        diagnostic = report['runs'][0]
        phases = diagnostic['phases']
        order = [(1, 0)] + [(kind, layer) for layer in range(12) for kind in range(2, 10)]
        order += [(10, 0), (11, 0), (12, 0)]
        require([(p['kind'], p['layer']) for p in phases] == order, 'stage order/coverage mismatch')
        require(len(phases) == 100 and all(p['cycles'] >= p['service_cycles'] >=
                p['gemm_cycles']+p['sfpu_cycles'] for p in phases), 'invalid nested phase accounting')
        require(sum(p['cycles'] for p in phases)+diagnostic['unassigned_profile_tail_cycles'] ==
                diagnostic['model_cycles'], 'phase coverage does not reconcile')
        require(sum(p['jobs'] for p in phases) == diagnostic['jobs'] == 9652, 'job coverage changed')
        for key, field in (('service_cycles', 'service_seconds'), ('gemm_cycles', 'gemm_compute_seconds'),
                           ('sfpu_cycles', 'sfpu_compute_seconds')):
            require(math.isclose(sum(p[key] for p in phases)/policy['clock_hz'], diagnostic[field], abs_tol=1e-12), 'counter sum mismatch')
        require(evidence['statistics'][name] == statistics_for(report), 'statistics mismatch')
    require(evidence['statistics']['reuse']['model_seconds']['mean'] <
            evidence['statistics']['metadata']['model_seconds']['mean'] <
            evidence['statistics']['shift']['model_seconds']['mean'] <
            evidence['statistics']['baseline']['model_seconds']['mean'], 'retained candidate did not improve latency')
    final = evidence['complete']
    require(final['status'] == 'PASS' and final['dma']['owner'] == 0 and not final.get('cleanup_error'), 'final physical/cleanup failure')
    require(final['sha256']['bitstream'] == bit and final['sha256']['hwh'] == hwh and
            final['sha256']['firmware_file'] == final['sha256']['firmware_readback'] ==
            sha(ROOT/'build/m5_opt_runtime/m5_runtime.bin'), 'final artifact mismatch')
    require(final['allocated_bytes'] == 266289152, 'full arena was reduced')
    require('M5 PHYSICAL PASS:' in (ROOT/'build/m5_opt_runtime/physical_complete.log').read_text(), 'terminal physical completion missing')
    require(sha(ROOT/'build/m5_opt_runtime/m5_runtime.bin') ==
            sha(ROOT/'build/m5_opt_runtime_repro/m5_runtime.bin'), 'clean firmware reproduction differs')
    complete_policy = json.loads((ROOT/'tests/m5_opt/complete_policy.json').read_text())
    require(final['policy'] == complete_policy and len(final['runs']) == 3, 'complete request policy mismatch')
    fixtures = json.loads((ROOT/'build/m4_runtime_fixtures/manifest.json').read_text())
    references = {r['id']: r for r in fixtures['generation']}
    for run, trial in zip(final['runs'], complete_policy['matrix']):
        reference = references[trial['prompt']]
        count = trial['new_tokens']; expected = reference['steps'][count-1]
        require(run['id'] == trial['prompt'] and run['generated_tokens'] ==
                [s['token'] for s in reference['steps'][:count]], 'complete tokens mismatch')
        require(run['logits_sha256'] == expected['logits_sha256'] and
                run['kv_sha256'] == expected['cache_sha256'] and
                run['cache_valid'] == len(reference['input_tokens'])+count-1, 'complete logits/KV mismatch')
        require(0 < run['firmware_seconds'] < run['request_through_delivery_seconds'] < 600, 'complete timing mismatch')
    require([t['name'] for t in final['runs'][0]['traces']] ==
            ['embedding', 'h.0.qkv', 'h.0.context', 'h.0.output', 'h.11.output'], 'affected trace coverage missing')
    boundary = final['boundary_rejection']
    require(boundary['state'] == 5 and boundary['error'] == 1 and
            boundary['cache_valid'] == 17 and boundary['generated_count'] == 19 and
            boundary['output_sentinel_unchanged'] and len(boundary['cache_regions_unchanged']) == 4, 'rejection/non-mutation missing')
    require(evidence['release']['status'] == 'PASS' and
            evidence['release']['info_after_close_reopen']['owner'] == 0 and
            evidence['release']['info_after_close_reopen']['allocated_pages'] == 0, 'pages/ownership retained')
    require((ROOT/'build/m5_opt_runtime/unload.log').read_text().strip() == 'M5 OPT NORMAL UNLOAD PASS', 'normal unload missing')
    require(evidence['probes']['status'] == 'PASS' and len(evidence['probes']['records']) == 8 and
            evidence['probes']['returned']['owner'] == 0, 'scalar probes failed')
    precision = evidence['precision']
    for path, digest in precision['source_sha256'].items():
        require(sha(ROOT/path) == digest, 'precision source mismatch: ' + path)
    require(precision['policy'] == json.loads((ROOT/'tests/m5_opt/precision_policy.json').read_text()) and
            precision['status'] == 'CANDIDATE_REJECTED' and precision['host_evaluation_seconds'] < 600, 'precision disposition mismatch')
    require(all(precision['variants']['accepted_w8a8']['gates'].values()) and
            not all(precision['variants']['candidate_w4a8']['gates'].values()), 'precision result mismatch')
    require('M5 NUMERICAL FOUNDATION PASS' in (ROOT/'build/m5_opt_runtime/native_test.log').read_text(), 'native foundation missing')
    require('M5 OPT EXACT NUMERICS PASS' in (ROOT/'build/m5_opt_runtime/exact_test.log').read_text(), 'exact scalar tests missing')
    require('M5 OPT EXACT NUMERICS PASS' in (ROOT/'build/m5_opt_runtime/exact_edge_test.log').read_text(), 'targeted tie-boundary tests missing')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, default=ROOT/'docs/m5_opt_evidence.json')
    args = parser.parse_args()
    subprocess.run([sys.executable, '-m', 'scripts.audit_m5'], cwd=ROOT, check=True)
    validate(json.loads(args.evidence.read_text()))
    print('M5 OPT AUDIT PASS: exact faster firmware, bounded physical checks, explicit hardware/precision dispositions')


if __name__ == '__main__':
    main()
