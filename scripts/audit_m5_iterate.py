"""Read-only closure audit for three bounded cycles; no rebuild or board access."""
import argparse
import json
import math
import subprocess
import sys

from scripts.audit_m5_opt import ROOT, require, sha, statistics_for
from scripts.audit_m5_fast import hardware_from_reports

FINAL = 'build/m5_iterate_c3_v1'
REPRO = 'build/m5_iterate_repro_v1'
VARIANTS = {'cycle1': 'build/m5_iterate_c1_v1',
            'cycle2': 'build/m5_iterate_c2_hart1_v1', 'cycle3': FINAL}
REPORT_PATHS = {name: directory+'/diagnostic.json' for name, directory in VARIANTS.items()}
REPORT_PATHS.update(rejected_clock='build/m5_iterate_c2_v1/diagnostic.json',
                    measurement=FINAL+'/measurement.json', complete=FINAL+'/physical_complete.json',
                    campaign=FINAL+'/campaign.json', release=FINAL+'/release.json')


def read(path):
    return (ROOT/path).read_text()


def validate_decode(report, directory, policy, seed, measured=False):
    require(report['status'] == 'PASS' and report['dma_after_return']['owner'] == 0 and
            not report.get('cleanup_error'), 'decode/cleanup failed')
    require(report['policy'] == policy, 'decode policy changed')
    roles = policy['fixed_decode']['final_roles' if measured else 'diagnostic_roles']
    require(report['mode'] == ('measure' if measured else 'diagnostic') and
            [r['role'] for r in report['runs']] == roles, 'missing/cherry-picked samples')
    firmware = sha(ROOT/directory/'m5_profile.bin')
    expected_hashes = {'m5_pynq.bit': policy['hardware']['bit_sha256'],
                       'm5_pynq.hwh': policy['hardware']['hwh_sha256'],
                       'm5_profile.bin': firmware,
                       'iteration_policy.json': sha(ROOT/'tests/m5_iterate/performance_policy.json'),
                       'seed/manifest.json': policy['imported_seed']['manifest_sha256']}
    for name in ('m5_iterate_profile.py', 'm5_opt_profile.py', 'm5_run.py'):
        expected_hashes[name] = sha(ROOT/'zynq'/name)
    require(report['sha256'] == expected_hashes, 'decode source/artifact identity mismatch')
    for ordinal, run in enumerate(report['runs'], 1):
        require(run['status'] == 'PASS' and run['ordinal'] == ordinal and
                run['firmware_sha256'] == firmware and run['token'] == seed['expected']['token'] == 582 and
                run['cache_valid'] == 14 and run['logits_sha256'] == seed['expected']['logits_sha256'] and
                run['kv_sha256'] == seed['expected']['cache_sha256'], 'decode exactness mismatch')
        enabled = ordinal == 1
        require(run['profile_enabled'] == enabled, 'profiling enable changed')
        require(0 < run['model_seconds'] < run['host_request_through_delivery_seconds'] < 120 and
                math.isclose(run['model_seconds'], run['model_cycles']/91000000, abs_tol=1e-12),
                'decode timing boundary mismatch')
        require(run['jobs'] == 9701 and run['mover_input_bytes'] == 134861772 and
                run['mover_output_bytes'] == 1981892 and run['workspace_high_water'] == 1632708,
                'decode job/transport/workspace contract changed')
        if not enabled:
            require(not run['phases'] and all(run[key] is None for key in
                    ('service_seconds', 'cpu_remainder_seconds', 'gemm_compute_seconds',
                     'sfpu_compute_seconds', 'unassigned_profile_tail_cycles')),
                    'disabled profiling contains counters')
    run = report['runs'][0]
    phases = run['phases']
    expected_order = [(1, 0)] + [(kind, layer) for layer in range(12) for kind in range(2, 10)]
    expected_order += [(10, 0), (11, 0), (12, 0)]
    require([(p['kind'], p['layer']) for p in phases] == expected_order, 'phase coverage/order changed')
    require(all(p['cycles'] >= p['service_cycles'] >= p['gemm_cycles']+p['sfpu_cycles'] and
                p['cpu_remainder_cycles'] == p['cycles']-p['service_cycles'] and
                math.isclose(p['seconds'], p['cycles']/91000000, abs_tol=1e-12) for p in phases),
                'nested profile interval invalid')
    require(sum(p['cycles'] for p in phases)+run['unassigned_profile_tail_cycles'] == run['model_cycles'],
            'phase times do not reconcile')
    for key, total in (('jobs', 'jobs'), ('input_bytes', 'mover_input_bytes'),
                       ('output_bytes', 'mover_output_bytes')):
        require(sum(p[key] for p in phases) == run[total], 'phase job/transport sum mismatch')
    for key, seconds in (('service_cycles', 'service_seconds'), ('gemm_cycles', 'gemm_compute_seconds'),
                          ('sfpu_cycles', 'sfpu_compute_seconds')):
        require(math.isclose(sum(p[key] for p in phases)/91000000, run[seconds], abs_tol=1e-12),
                'nested compute/service sum mismatch')
    require(math.isclose(run['cpu_remainder_seconds'], run['model_seconds']-run['service_seconds'],
                         abs_tol=1e-12), 'CPU remainder mismatch')


def validate(evidence, check_files=True):
    require(evidence['schema'] == 1 and evidence['status'] == 'PASS', 'iteration goal not closed')
    require(evidence['gates'] == {key: 'PASS' for key in
            ('scope', 'cycle1', 'cycle2', 'cycle3', 'final_decode', 'complete_board', 'release', 'reproduction')},
            'required gate incomplete')
    policy = json.loads(read('tests/m5_iterate/performance_policy.json'))
    require(evidence['policy'] == policy, 'policy changed')
    require(sha(ROOT/'docs/m5_fast_evidence.json') == policy['baseline_evidence_sha256'],
            'qualified baseline changed')
    if check_files:
        from scripts.collect_m5_iterate_evidence import manifest_paths
        sources, artifacts = manifest_paths()
        require(set(evidence['sources']) == sources and set(evidence['artifacts']) == artifacts,
                'source/artifact manifest incomplete')
        for collection in ('sources', 'artifacts'):
            for path, digest in evidence[collection].items():
                require(sha(ROOT/path) == digest, 'stale '+collection+': '+path)
        for name, path in REPORT_PATHS.items():
            require(evidence['reports'][name] == json.loads(read(path)), 'embedded report changed: '+name)
    require(evidence['hardware'] == hardware_from_reports(), 'qualified hardware changed')
    seed = json.loads(read('build/m5_opt_seed_v1/manifest.json'))
    require(sha(ROOT/'build/m5_opt_seed_v1/manifest.json') == policy['imported_seed']['manifest_sha256'] and
            seed['policy_sha256'] == policy['imported_seed']['original_policy_sha256'] and
            seed['fixture_sha256'] == policy['imported_seed']['reference_manifest_sha256'], 'seed changed')
    reports = evidence['reports']
    for name, directory in VARIANTS.items():
        validate_decode(reports[name], directory, policy, seed)
    validate_decode(reports['measurement'], FINAL, policy, seed, measured=True)
    require(evidence['statistics']['final'] == statistics_for(reports['measurement']), 'statistics mismatch')
    baseline = json.loads(read('docs/m5_fast_evidence.json'))
    require(evidence['statistics']['baseline'] == baseline['statistics']['requant'], 'baseline statistics changed')
    previous = baseline['statistics']['requant']['model_seconds']['mean']
    for name in ('cycle1', 'cycle3'):
        now = reports[name]['runs'][1]['model_seconds']
        require(now < previous, 'retained cycle lacks measured improvement')
        previous = now
    require(evidence['statistics']['final']['host_request_through_delivery_seconds']['mean'] <
            baseline['statistics']['requant']['host_request_through_delivery_seconds']['mean'],
            'final delivered result is not faster')
    require(evidence['decisions'] == {'cycle1': 'RETAIN', 'cycle2_both_sleep': 'REJECT_TIMER_UNDERCOUNT',
            'cycle2_hart1_sleep': 'DEFER_NO_MATERIAL_GAIN', 'cycle3': 'RETAIN', 'new_rtl': 'NOT_NEEDED',
            'persistent_model_cache': 'DEFER'}, 'cycle decisions changed')
    rejected = reports['rejected_clock']
    require(rejected['status'] == 'FAIL' and not rejected['runs'] and
            rejected['error'] == 'ValueError: invalid nested profile interval' and
            rejected['dma_after_return']['owner'] == 0 and not rejected.get('cleanup_error'),
            'rejected clock diagnostic was concealed or relabelled')
    require(rejected['sha256']['m5_profile.bin'] == sha(ROOT/'build/m5_iterate_c2_v1/m5_profile.bin'),
            'rejected diagnostic identity changed')
    require('hart=0 state=3 errors=00010000' in read('build/m5_iterate_clock_v1/simulation_0.log') and
            'M5 ACTUAL DUAL-IBEX MEMORY SIMULATION PASS boots=2 aborted_boots=1' in
            read('build/m5_iterate_clock_v1/simulation_1.log'), 'clock red/green regression missing')
    require('M5 ACTUAL DUAL-IBEX MEMORY SIMULATION PASS boots=2 aborted_boots=1' in
            read('build/m5_iterate_wait_v2/simulation.log'), 'actual WFI semantics test missing')
    for directory in (*VARIANTS.values(), REPRO):
        require('M5 NUMERICAL FOUNDATION PASS' in read(directory+'/native_test.log') and
                'M5 OPT EXACT NUMERICS PASS' in read(directory+'/exact_numerics.log'), 'native exact suite missing')
    for name in ('m5_runtime.bin', 'm5_profile.bin'):
        require(sha(ROOT/FINAL/name) == sha(ROOT/REPRO/name), 'clean firmware reproduction changed')
    for directory in (FINAL, REPRO):
        for kind in ('runtime', 'profile'):
            attributes = read(directory+'/'+kind+'.attributes.txt')
            require('rv32i2p1_m2p0_c2p0_zicsr2p0' in attributes and '_f' not in attributes and '_d' not in attributes,
                    'firmware ISA changed')
        hardware = read(directory+'/generated/hardware.c')
        require(sha(ROOT/directory/'generated/hardware.c') ==
                sha(ROOT/'runtime/m5/pa_m5_hw.c') and 'pa_iter_wait_mailbox' not in hardware,
                'unretained WFI candidate was deployed')
    complete = reports['complete']
    require(complete['status'] == 'PASS' and complete['dma']['owner'] == 0 and
            not complete.get('cleanup_error') and complete['allocated_bytes'] == 266289152,
            'full board/arena/cleanup failure')
    cp = json.loads(read('tests/m5_iterate/complete_policy.json'))
    require(complete['policy'] == cp and len(complete['runs']) == 3 and cp['matrix'] ==
            policy['final_complete_matrix'] and cp['parent_policy_sha256'] ==
            sha(ROOT/'tests/m5_iterate/performance_policy.json'), 'complete matrix/policy changed')
    old_complete = baseline['reports']['complete']
    for key, expected in (('bitstream', policy['hardware']['bit_sha256']),
                           ('hwh', policy['hardware']['hwh_sha256']),
                           ('firmware_file', sha(ROOT/FINAL/'m5_runtime.bin')),
                           ('firmware_readback', sha(ROOT/FINAL/'m5_runtime.bin')),
                           ('policy', sha(ROOT/'tests/m5_iterate/complete_policy.json')),
                           ('fixtures', policy['imported_seed']['reference_manifest_sha256']),
                           ('model', old_complete['sha256']['model']), ('layout', old_complete['sha256']['layout'])):
        require(complete['sha256'][key] == expected, 'complete artifact mismatch: '+key)
    for run, old in zip(complete['runs'], old_complete['runs']):
        for key in ('id', 'generated_tokens', 'logits_sha256', 'kv_sha256', 'cache_valid'):
            require(run[key] == old[key], 'complete exact result changed: '+key)
        require(run.get('traces') == old.get('traces'), 'complete traces changed')
        require(0 < run['firmware_seconds'] < run['request_through_delivery_seconds'] < 600,
                'complete timing boundary invalid')
    for key, old in old_complete['boundary_rejection'].items():
        if key != 'wall_seconds':
            require(complete['boundary_rejection'][key] == old, 'overflow non-mutation/recovery changed')
    campaign = reports['campaign']
    require(campaign['status'] == 'PASS' and campaign['watchdog_seconds'] == 1200 and
            0 < campaign['elapsed_seconds'] < 1200 and campaign['runner_sha256'] ==
            sha(ROOT/'zynq/m5_fast_complete.py') and campaign['checked_runner_sha256'] ==
            sha(ROOT/'zynq/m5_run.py'), 'campaign watchdog/identity failed')
    release = reports['release']
    info = release['info_after_close_reopen']
    require(release['status'] == 'PASS' and info['owner'] == info['allocated_pages'] == info['pte_dma'] == 0 and
            release['runner_sha256'] == sha(ROOT/'zynq/m5_opt_release_check.py'), 'DMA resources retained')
    require(read(FINAL+'/unload.log').strip() == 'M5 ITERATE NORMAL UNLOAD PASS', 'normal unload missing')
    require('M5 PHYSICAL PASS:' in read(FINAL+'/physical_complete.log') and
            'M5 FAST COMPLETE CAMPAIGN PASS' in read(FINAL+'/physical_complete.log'), 'terminal board result missing')
    unit_log = read('build/m5_iterate_unit_tests_v1.log')
    require('Ran 15 tests' in unit_log and '\nOK\n' in unit_log and
            'test_negative_gates' in unit_log and 'M5 ITERATE ATTENTION PREPARED EXACT PASS 576' in unit_log and
            'M5 ITERATE EXACT RANGE PASS 38640' in unit_log, 'targeted/negative tests missing')


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--evidence', default='docs/m5_iterate_evidence.json')
    args = parser.parse_args()
    subprocess.run([sys.executable, '-m', 'scripts.audit_m5_fast'], cwd=ROOT, check=True)
    validate(json.loads(read(args.evidence)))
    print('M5 ITERATE AUDIT PASS: three cycles, exact faster model, honest clocks, qualified hardware, bounded board and release')


if __name__ == '__main__':
    main()
