"""Collect/check bounded scalar results; never builds hardware or accesses the board."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

from scripts.audit_m5_opt import ROOT, sha, require, statistics_for

FINAL = 'build/m5_scalar_affine_v1'
REPRO = 'build/m5_scalar_repro_v1'
CANDIDATES = {
    'arithmetic': 'build/m5_scalar_arithmetic_v2',
    'lookup': 'build/m5_scalar_lookup_v2',
    'metadata': 'build/m5_scalar_metadata_v1',
    'affine': FINAL,
}
REPORTS = {name: directory+'/diagnostic.json' for name, directory in CANDIDATES.items()}
REPORTS.update({name: FINAL+'/'+filename for name, filename in
               (('measurement', 'measurement.json'), ('complete', 'physical_complete.json'),
                ('campaign', 'campaign.json'), ('release', 'release.json'))})
REPORTS.update({name+'_fine': CANDIDATES[name]+'/fine.json' for name in ('lookup', 'metadata')})


def read(path):
    return (ROOT/path).read_text()


def manifest_paths():
    sources = set()
    for pattern in ('runtime/m5_scalar/*', 'tests/m5_scalar/*.py', 'tests/m5_scalar/*.c',
                    'scripts/*m5_scalar*', 'docs/M5_SCALAR*.md'):
        sources.update(str(p.relative_to(ROOT)) for p in ROOT.glob(pattern) if p.is_file())
    # Earlier audit recursively verifies all immutable hardware/model/runner inputs.
    sources.update(('scripts/m5_iterate_sources.py', 'scripts/m5_fast_firmware_sources.py',
                    'runtime/m5_fast/exact_power2.c.inc', 'runtime/m5/pa_m5_hw.c',
                    'runtime/m5/pa_m5_runtime.c', 'runtime/m5_fast/pa_m5_requant.c',
                    'zynq/m5_iterate_profile.py', 'zynq/m5_fast_profile.py',
                    'zynq/m5_opt_profile.py', 'zynq/m5_run.py', 'zynq/m5_fast_complete.py',
                    'zynq/m5_opt_release_check.py', 'tests/m5_iterate/performance_policy.json',
                    'tests/m5_iterate/complete_policy.json'))
    artifacts = {'docs/m5_iterate_evidence.json', 'build/m5_opt_seed_v1/manifest.json'}
    for directory in set(CANDIDATES.values()) | {REPRO}:
        for pattern in ('*.bin', '*.elf', '*.so', '*.log', '*.txt', '*.json', '*.sha256', 'generated/*'):
            artifacts.update(str(p.relative_to(ROOT)) for p in (ROOT/directory).glob(pattern) if p.is_file())
    return sources, artifacts


def validate_runs(report, firmware, workspace, roles):
    seed = json.loads(read('build/m5_opt_seed_v1/manifest.json'))
    require(report['status'] == 'PASS' and report['dma_after_return']['owner'] == 0 and
            not report.get('cleanup_error'), 'decode cleanup failed')
    require([r['role'] for r in report['runs']] == roles, 'missing/cherry-picked samples')
    for index, run in enumerate(report['runs'], 1):
        enabled = index == 1
        require(run['status'] == 'PASS' and run['ordinal'] == index and
                run['profile_enabled'] == enabled and run['firmware_sha256'] == firmware,
                'wrong firmware/role/status')
        require(run['token'] == seed['expected']['token'] == 582 and run['cache_valid'] == 14 and
                run['logits_sha256'] == seed['expected']['logits_sha256'] and
                run['kv_sha256'] == seed['expected']['cache_sha256'], 'inexact decode')
        require(0 < run['model_seconds'] < run['host_request_through_delivery_seconds'] < 120 and
                math.isclose(run['model_seconds'], run['model_cycles']/91000000, abs_tol=1e-12),
                'wrong timing boundary or clock')
        require((run['jobs'], run['mover_input_bytes'], run['mover_output_bytes'], run['workspace_high_water']) ==
                (9701, 134861772, 1981892, workspace), 'transport/workspace changed')
        phases = run['phases']
        if not enabled:
            require(not phases and all(run[key] is None for key in
                    ('service_seconds', 'cpu_remainder_seconds', 'gemm_compute_seconds',
                     'sfpu_compute_seconds', 'unassigned_profile_tail_cycles')), 'disabled counters populated')
            continue
        order = [(1, 0)] + [(kind, layer) for layer in range(12) for kind in range(2, 10)]
        require([(p['kind'], p['layer']) for p in phases] == order+[(10, 0), (11, 0), (12, 0)],
                'phase coverage/order changed')
        require(all(p['cycles'] >= p['service_cycles'] >= p['gemm_cycles']+p['sfpu_cycles'] and
                    p['cpu_remainder_cycles'] == p['cycles']-p['service_cycles'] and
                    math.isclose(p['seconds'], p['cycles']/91000000, abs_tol=1e-12) for p in phases),
                'invalid nested clock intervals')
        require(sum(p['cycles'] for p in phases)+run['unassigned_profile_tail_cycles'] == run['model_cycles'],
                'phase clocks do not reconcile')
        for key, total in (('jobs', 'jobs'), ('input_bytes', 'mover_input_bytes'), ('output_bytes', 'mover_output_bytes')):
            require(sum(p[key] for p in phases) == run[total], 'transport totals do not reconcile')
        for key, total in (('service_cycles', 'service_seconds'), ('gemm_cycles', 'gemm_compute_seconds'),
                           ('sfpu_cycles', 'sfpu_compute_seconds')):
            require(math.isclose(sum(p[key] for p in phases)/91000000, run[total], abs_tol=1e-12),
                    'service/engine totals do not reconcile')
        require(math.isclose(run['cpu_remainder_seconds'], run['model_seconds']-run['service_seconds'], abs_tol=1e-12),
                'CPU remainder does not reconcile')


def validate(evidence, check_files=True):
    require(evidence['schema'] == 1 and evidence['status'] == 'PASS', 'goal not closed')
    require(evidence['decisions'] == {name: 'RETAIN' for name in CANDIDATES}, 'unexpected retained combination')
    policy = json.loads(read('tests/m5_iterate/performance_policy.json'))
    old = json.loads(read('docs/m5_iterate_evidence.json'))
    require(evidence['baseline_sha256'] == sha(ROOT/'docs/m5_iterate_evidence.json'), 'baseline changed')
    if check_files:
        sources, artifacts = manifest_paths()
        require(set(evidence['sources']) == sources and set(evidence['artifacts']) == artifacts, 'manifest incomplete')
        for key in ('sources', 'artifacts'):
            for path, digest in evidence[key].items():
                require(sha(ROOT/path) == digest, 'changed '+key+': '+path)
        for name, path in REPORTS.items():
            require(evidence['reports'][name] == json.loads(read(path)), 'embedded report changed')
    reports = evidence['reports']
    previous = old['statistics']['final']['model_seconds']['mean']
    for name, directory in list(CANDIDATES.items()) + [('measurement', FINAL)]:
        report = reports[name]
        measured = name == 'measurement'
        roles = policy['fixed_decode']['final_roles' if measured else 'diagnostic_roles']
        require(report['policy'] == policy and report['mode'] == ('measure' if measured else 'diagnostic'),
                'imported measurement protocol changed')
        expected = {file: sha(ROOT/'zynq'/file) for file in ('m5_iterate_profile.py', 'm5_opt_profile.py', 'm5_run.py')}
        expected.update({'m5_pynq.bit': policy['hardware']['bit_sha256'], 'm5_pynq.hwh': policy['hardware']['hwh_sha256'],
                         'm5_profile.bin': sha(ROOT/directory/'m5_profile.bin'),
                         'iteration_policy.json': sha(ROOT/'tests/m5_iterate/performance_policy.json'),
                         'seed/manifest.json': policy['imported_seed']['manifest_sha256']})
        require(report['sha256'] == expected, 'decode source/hardware identity mismatch')
        validate_runs(report, expected['m5_profile.bin'], 1632708 if name == 'arithmetic' else 2026052, roles)
        if not measured:
            require(report['runs'][1]['model_seconds'] < previous, 'retained candidate lacks measured improvement')
            previous = report['runs'][1]['model_seconds']
    for name in ('lookup', 'metadata'):
        fine = reports[name+'_fine']
        validate_runs(fine, sha(ROOT/CANDIDATES[name]/'m5_fine.bin'), 2026052,
                      ['profiled_diagnostic', 'unprofiled_diagnostic'])
        require(fine['sha256']['m5_pynq.bit'] == policy['hardware']['bit_sha256'] and
                fine['sha256']['m5_pynq.hwh'] == policy['hardware']['hwh_sha256'], 'fine hardware changed')
        for run in fine['runs']:
            require(len(run['fine']) == 9 and all((f['calls'] > 0 and 0 < f['seconds'] < run['model_seconds'])
                    if run['profile_enabled'] else f['calls'] == f['cycles'] == f['seconds'] == 0
                    for f in run['fine']), 'fine coverage invalid')
    stats = statistics_for(reports['measurement'])
    require(evidence['statistics'] == {'baseline': old['statistics']['final'], 'final': stats}, 'statistics changed')
    require(stats['host_request_through_delivery_seconds']['mean'] <
            old['statistics']['final']['host_request_through_delivery_seconds']['mean'], 'no delivered improvement')
    for name in ('m5_runtime.bin', 'm5_profile.bin', 'm5_fine.bin'):
        require(sha(ROOT/FINAL/name) == sha(ROOT/REPRO/name), 'firmware reproduction mismatch')
    for directory in (FINAL, REPRO):
        require(sha(ROOT/directory/'generated/hardware.c') == sha(ROOT/'runtime/m5/pa_m5_hw.c'), 'controller/WFI changed')
        for kind in ('runtime', 'profile', 'fine'):
            attributes = read(directory+'/'+kind+'.attributes.txt')
            require('rv32i2p1_m2p0_c2p0_zicsr2p0' in attributes and '_f' not in attributes and '_d' not in attributes,
                    'ISA/soft-float contract changed')
        for file, marker in (('native_test.log', 'M5 NUMERICAL FOUNDATION PASS'),
                             ('exact_numerics.log', 'M5 OPT EXACT NUMERICS PASS'),
                             ('cache_test.log', 'M5 SCALAR CACHE EXACT PASS'),
                             ('quantize_test.log', 'M5 SCALAR AFFINE ROUND EXACT PASS'),
                             ('norm_factor.log', 'M5 ITERATE NORM FACTOR EXACT PASS')):
            require(marker in read(directory+'/'+file), 'native gate missing')
    require('M5 SCALAR ATTENTION LAYOUT EXACT PASS 15' in read(FINAL+'/attention_test.log') and
            'M5 SCALAR UNIFORM EXACT PASS 1188' in read(FINAL+'/uniform_test.log'), 'operator regression missing')
    complete, old_complete = reports['complete'], old['reports']['complete']
    require(complete['status'] == 'PASS' and complete['dma']['owner'] == 0 and
            not complete.get('cleanup_error') and complete['allocated_bytes'] == 266289152,
            'complete model/arena/cleanup failed')
    require(complete['policy'] == old_complete['policy'] and len(complete['runs']) == 3, 'complete scope changed')
    expected = dict(old_complete['sha256'])
    expected['firmware_file'] = expected['firmware_readback'] = sha(ROOT/FINAL/'m5_runtime.bin')
    require(complete['sha256'] == expected, 'complete source/artifact identity changed')
    for run, original in zip(complete['runs'], old_complete['runs']):
        for key in ('id', 'generated_tokens', 'logits_sha256', 'kv_sha256', 'cache_valid', 'traces'):
            require(run.get(key) == original.get(key), 'complete exact result changed: '+key)
        require(0 < run['firmware_seconds'] < run['request_through_delivery_seconds'] < 600, 'complete time invalid')
    for key, value in old_complete['boundary_rejection'].items():
        if key != 'wall_seconds': require(complete['boundary_rejection'][key] == value, 'overflow/recovery changed')
    campaign = reports['campaign']
    require(campaign['status'] == 'PASS' and campaign['watchdog_seconds'] == 1200 and 0 < campaign['elapsed_seconds'] < 1200 and
            campaign['runner_sha256'] == sha(ROOT/'zynq/m5_fast_complete.py') and
            campaign['checked_runner_sha256'] == sha(ROOT/'zynq/m5_run.py'), 'campaign gate failed')
    release = reports['release']; info = release['info_after_close_reopen']
    require(release['status'] == 'PASS' and info['owner'] == info['allocated_pages'] == info['pte_dma'] == 0 and
            release['runner_sha256'] == sha(ROOT/'zynq/m5_opt_release_check.py'), 'DMA resources retained')
    require(read(FINAL+'/unload.log').strip() == 'M5 SCALAR NORMAL UNLOAD PASS', 'normal unload missing')


def collect():
    sources, artifacts = manifest_paths()
    reports = {name: json.loads(read(path)) for name, path in REPORTS.items()}
    old = json.loads(read('docs/m5_iterate_evidence.json'))
    evidence = dict(schema=1, status='PASS', baseline_sha256=sha(ROOT/'docs/m5_iterate_evidence.json'),
                    decisions={name: 'RETAIN' for name in CANDIDATES}, reports=reports,
                    sources={p: sha(ROOT/p) for p in sorted(sources)}, artifacts={p: sha(ROOT/p) for p in sorted(artifacts)},
                    statistics={'baseline': old['statistics']['final'], 'final': statistics_for(reports['measurement'])},
                    accounting='Per-forward lazy table initialization/misses are inside the model interval. No persisted or preloaded table.',
                    limitations='Four bounded candidates; short fixed-context samples, not sustained/tail/long-context performance or a global optimum.')
    validate(evidence)
    return evidence


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--collect', action='store_true')
    parser.add_argument('--evidence', default='docs/m5_scalar_evidence.json')
    args = parser.parse_args()
    subprocess.run([sys.executable, '-m', 'scripts.audit_m5_iterate'], cwd=ROOT, check=True)
    if args.collect:
        target = ROOT/args.evidence
        if target.exists(): raise ValueError('use a fresh evidence output')
        target.write_text(json.dumps(collect(), indent=2)+'\n')
    else:
        validate(json.loads(read(args.evidence)))
    print('M5 SCALAR AUDIT PASS: exact faster project, charged preparation, unchanged hardware, reproduced firmware and safe board release')


if __name__ == '__main__':
    main()
