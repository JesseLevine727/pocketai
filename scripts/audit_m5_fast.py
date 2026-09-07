"""Read-only M5 fast-controller closure audit; no board access or rebuild."""
import argparse
import json
import math
import re
import subprocess
import sys

from scripts.audit_m5_opt import ROOT, require, sha, statistics_for

HW = 'build/m5_fast_pynq_finish_v2'
SYNTH = 'build/m5_fast_pynq_v4'
FINAL = 'build/m5_fast_runtime_requant_v1'
REPRO = 'build/m5_fast_runtime_requant_repro'
REPORT_PATHS = {
    'fast_only': 'build/m5_fast_only_v1/fast_only.json',
    'prepared': 'build/m5_fast_runtime_v1/measurement.json',
    'requant': FINAL + '/measurement.json',
    'fine_final': 'build/m5_fast_final_fine_v1/fine.json',
    'fine_slow': 'build/m5_fast_fine_v1/fine_slow_v2.json',
    'prepare_slow': 'build/m5_fast_prepare_v2/prepare_slow.json',
    'requant_probe': 'build/m5_fast_only_v1/requant_fast.json',
    'requant_probe_slow': 'build/m5_fast_requant_v1/requant_slow.json',
    'scalar_probe': 'build/m5_fast_only_v1/scalar.json',
    'complete': FINAL + '/physical_complete.json',
    'campaign': FINAL + '/campaign.json',
    'release': FINAL + '/release.json',
}
FIRMWARE = {
    'fast_only': 'build/m5_opt_reuse/m5_profile.bin',
    'prepared': 'build/m5_fast_runtime_v1/m5_profile.bin',
    'requant': FINAL + '/m5_profile.bin',
    'fine_final': 'build/m5_fast_final_fine_v1/m5_profile.bin',
    'fine_slow': 'build/m5_fast_fine_v1/m5_profile.bin',
    'prepare_slow': 'build/m5_fast_prepare_v2/m5_profile.bin',
}


def read(path):
    return (ROOT / path).read_text()


def hardware_from_reports():
    timing = read(HW + '/reports/m5_timing_summary.rpt')
    match = re.search(r'WNS\(ns\).*?\n\s*-+[^\n]*\n\s*([^\n]+)', timing, re.S)
    require(match, 'timing summary missing')
    values = match[1].split()
    result = dict(wns=float(values[0]), tns=float(values[1]),
                  hold=float(values[4]), ths=float(values[5]), clock_mhz=91.0)
    require('10.989          91.000' in timing, 'wrong fabric clock')
    require(len(set(re.findall(r'\d+\. checking \w+ \(0\)', timing))) == 12,
            'unconstrained endpoint/clock check failed')
    require('All user specified timing constraints are met.' in timing, 'timing unmet')
    route = read(HW + '/reports/m5_route_status.rpt')
    counts = [int(re.search(label + r'\.+\s*:\s*(\d+)', route)[1]) for label in
              ('# of routable nets', '# of fully routed nets', '# of nets with routing errors')]
    require(counts[0] == counts[1] and counts[0] > 0 and counts[2] == 0, 'route incomplete')
    result['routed_nets'] = counts[0]
    utilization = read(HW + '/reports/m5_utilization.rpt')
    for key, label in (('luts', 'Slice LUTs'), ('registers', 'Slice Registers'),
                       ('bram36', 'Block RAM Tile'), ('dsp', 'DSPs'), ('slices', 'Slice')):
        found = re.search(r'\|\s*' + label + r'\s*\|\s*([\d.]+)\s*\|', utilization)
        require(found, 'missing utilization: ' + label)
        result[key] = float(found[1])
    for report, rule, count in (('m5_drc.rpt', 'RTSTAT-10', 1),
                                ('m5_methodology.rpt', 'LUTAR-1', 6)):
        body = read(HW + '/reports/' + report)
        rules = re.findall(r'^\|\s*([A-Z][A-Z0-9-]+)\s*\|\s*(Warning|Error|Critical Warning)\s*\|[^\n]+?\|\s*(\d+)\s*\|', body, re.M)
        require(rules == [(rule, 'Warning', str(count))], 'unreviewed DRC/methodology finding')
    require('M5_FAST_RESET_REVIEW_COMPLETE cells=6' in read('build/m5_fast_reset_review_stdout.log'),
            'actual final reset-cone review missing')
    require(result['wns'] >= .250 and result['tns'] == 0 and result['hold'] > 0 and
            result['ths'] == 0 and result['dsp'] == 0, 'hardware gate failed')
    configuration = read(SYNTH + '/reports/m5_fast_synth_configuration.rpt')
    for hart in (0, 1):
        require(f'hart={hart} multiplier=RV32MFast cells=91' in configuration and
                f'u_core{hart}/' in configuration, 'both synthesized fast harts not proven')
    require('M5 VIVADO PASS clock_mhz=91.0 setup_wns_ns=0.263' in
            read('build/m5_fast_finish_v2_stdout.log'), 'terminal qualified bitstream missing')
    return result


def validate_decode(name, report, policy, seed, bit, hwh):
    require(report['status'] == 'PASS' and report['dma_after_return']['owner'] == 0 and
            not report.get('cleanup_error'), name + ' decode/cleanup failure')
    require(report['policy'] == policy, name + ' policy mismatch')
    firmware = sha(ROOT / FIRMWARE[name])
    for key, value in (('m5_pynq.bit', bit), ('m5_pynq.hwh', hwh), ('m5_profile.bin', firmware),
                       ('m5_fast_profile.py', sha(ROOT/'zynq/m5_fast_profile.py')),
                       ('m5_opt_profile.py', sha(ROOT/'zynq/m5_opt_profile.py')),
                       ('m5_run.py', sha(ROOT/'zynq/m5_run.py'))):
        require(report['sha256'][key] == value, name + ' artifact mismatch: ' + key)
    fine = name.startswith('fine') or name == 'prepare_slow'
    roles = (['profiled_diagnostic', 'unprofiled_diagnostic'] if fine else
             ['profiled_diagnostic', 'unprofiled_warmup'] + [f'unprofiled_measured_{i}' for i in (1, 2, 3)])
    require(report['mode'] == ('fine' if fine else 'measure') and
            [r['role'] for r in report['runs']] == roles, name + ' missing/cherry-picked runs')
    for index, run in enumerate(report['runs']):
        require(run['status'] == 'PASS' and run['firmware_sha256'] == firmware and
                run['token'] == seed['expected']['token'] == 582 and run['cache_valid'] == 14 and
                run['logits_sha256'] == seed['expected']['logits_sha256'] and
                run['kv_sha256'] == seed['expected']['cache_sha256'], name + ' exact seed mismatch')
        require(run['profile_enabled'] == (index == 0), name + ' profiling state mismatch')
        require(0 < run['model_seconds'] < run['host_request_through_delivery_seconds'] < 120 and
                math.isclose(run['model_seconds'], run['model_cycles']/91000000, abs_tol=1e-12),
                name + ' timing boundary mismatch')
        if fine:
            expected_names = ['dynamic_quantize', 'layernorm_metadata', 'smooth_inclusive',
                              'affine_row_inclusive', 'head_affine_row_inclusive', 'affine_metadata',
                              'head_affine_metadata', 'project_inclusive', 'head_project_inclusive']
            require([r['name'] for r in run['fine']] == expected_names, 'missing fine profile focus')
            for counter in run['fine']:
                require((counter['calls'] > 0 and counter['cycles'] > 0) if index == 0 else
                        (counter['calls'] == counter['cycles'] == 0), 'fine counter enable/coverage')
                require(math.isclose(counter['seconds'], counter['cycles']/91000000, abs_tol=1e-12),
                        'fine 64-bit interval mismatch')
    diagnostic = report['runs'][0]
    phases = diagnostic['phases']
    order = [(1, 0)] + [(kind, layer) for layer in range(12) for kind in range(2, 10)]
    order += [(10, 0), (11, 0), (12, 0)]
    require([(p['kind'], p['layer']) for p in phases] == order, 'phase order changed')
    require(all(p['cycles'] >= p['service_cycles'] >= p['gemm_cycles']+p['sfpu_cycles']
                for p in phases), 'nested profile counter mismatch')
    require(sum(p['cycles'] for p in phases)+diagnostic['unassigned_profile_tail_cycles'] ==
            diagnostic['model_cycles'], 'phase coverage mismatch')
    expected_jobs = 9701 if name in ('requant', 'fine_final') else 9652
    require(sum(p['jobs'] for p in phases) == diagnostic['jobs'] == expected_jobs, 'backend job coverage')
    for counter, seconds in (('service_cycles', 'service_seconds'), ('gemm_cycles', 'gemm_compute_seconds'),
                              ('sfpu_cycles', 'sfpu_compute_seconds')):
        require(math.isclose(sum(p[counter] for p in phases)/91000000, diagnostic[seconds], abs_tol=1e-12),
                'nested service sum mismatch')
    require(math.isclose(diagnostic['cpu_remainder_seconds'], diagnostic['model_seconds']-
                         diagnostic['service_seconds'], abs_tol=1e-12), 'CPU remainder accounting')


def validate(evidence, check_files=True):
    require(evidence['schema'] == 1 and evidence['status'] == 'PASS', 'fast goal not qualified')
    require(evidence['gates'] == {f'F{i}': 'PASS' for i in range(8)}, 'required gate incomplete')
    policy = json.loads(read('tests/m5_fast/performance_policy.json'))
    require(evidence['policy'] == policy, 'frozen fast policy changed')
    require(sha(ROOT/'docs/m5_opt_evidence.json') == policy['baseline_evidence_sha256'], 'baseline identity changed')
    if check_files:
        from scripts.collect_m5_fast_evidence import manifest_paths
        required_sources, required_artifacts = manifest_paths()
        require(set(evidence['sources']) == required_sources and
                set(evidence['artifacts']) == required_artifacts, 'missing/unexpected manifest entries')
        require(len(evidence['sources']) >= 35 and len(evidence['artifacts']) >= 60, 'incomplete identity manifest')
        for collection in ('sources', 'artifacts'):
            for path, digest in evidence[collection].items():
                require(sha(ROOT/path) == digest, f'stale {collection}: {path}')
        for name, path in REPORT_PATHS.items():
            require(evidence['reports'][name] == json.loads(read(path)), 'embedded original mismatch: ' + name)
    hardware = hardware_from_reports()
    require(evidence['hardware'] == hardware, 'hardware summary mismatch')
    seed = json.loads(read(policy['imported_seed']['manifest']))
    require(sha(ROOT/policy['imported_seed']['manifest']) == policy['imported_seed']['manifest_sha256'],
            'independent seed changed')
    baseline = json.loads(read('docs/m5_opt_evidence.json'))
    bit, hwh = sha(ROOT/HW/'m5_pynq.bit'), sha(ROOT/HW/'m5_pynq.hwh')
    reports = evidence['reports']
    for name in FIRMWARE:
        slow = name in ('fine_slow', 'prepare_slow')
        validate_decode(name, reports[name], policy, seed,
                        baseline['decode']['reuse']['sha256']['m5_pynq.bit'] if slow else bit,
                        baseline['decode']['reuse']['sha256']['m5_pynq.hwh'] if slow else hwh)
    for name in ('fast_only', 'prepared', 'requant'):
        require(evidence['statistics'][name] == statistics_for(reports[name]), 'statistics changed: ' + name)
    require(evidence['statistics']['slow'] == baseline['statistics']['reuse'], 'imported baseline stats changed')
    means = [evidence['statistics'][name]['model_seconds']['mean'] for name in ('slow', 'fast_only', 'prepared', 'requant')]
    require(all(a > b for a, b in zip(means, means[1:])), 'retained optional candidate lacks net improvement')
    require(sha(ROOT/FIRMWARE['fast_only']) == policy['configurations'][0]['profile_firmware_sha256'],
            'fast-only firmware is not identical')
    for name in ('m5_runtime.bin', 'm5_profile.bin'):
        require(sha(ROOT/FINAL/name) == sha(ROOT/REPRO/name), 'clean firmware reproduction mismatch')
    complete = reports['complete']
    require(complete['status'] == 'PASS' and complete['dma']['owner'] == 0 and
            not complete.get('cleanup_error') and complete['allocated_bytes'] == 266289152,
            'full request/arena/cleanup failure')
    for key, expected in (('bitstream', bit), ('hwh', hwh), ('firmware_file', sha(ROOT/FINAL/'m5_runtime.bin')),
                           ('firmware_readback', sha(ROOT/FINAL/'m5_runtime.bin')),
                           ('fixtures', policy['imported_seed']['reference_manifest_sha256'])):
        require(complete['sha256'][key] == expected, 'complete artifact mismatch: ' + key)
    complete_policy = json.loads(read('tests/m5_fast/complete_policy.json'))
    require(complete['policy'] == complete_policy and len(complete['runs']) == 3, 'complete matrix changed')
    require(complete_policy['parent_policy_sha256'] == sha(ROOT/'tests/m5_fast/performance_policy.json') and
            complete['sha256']['policy'] == sha(ROOT/'tests/m5_fast/complete_policy.json'), 'complete policy identity')
    for key in ('model', 'layout'):
        require(complete['sha256'][key] == baseline['complete']['sha256'][key], 'model/arena representation changed')
    references = {r['id']: r for r in json.loads(read('build/m4_runtime_fixtures/manifest.json'))['generation']}
    for run, trial in zip(complete['runs'], complete_policy['matrix']):
        reference = references[trial['prompt']]; count = trial['new_tokens']; expected = reference['steps'][count-1]
        require(run['id'] == trial['prompt'] and run['generated_tokens'] ==
                [s['token'] for s in reference['steps'][:count]], 'complete generated token mismatch')
        require(run['logits_sha256'] == expected['logits_sha256'] and run['kv_sha256'] == expected['cache_sha256'] and
                run['cache_valid'] == len(reference['input_tokens'])+count-1, 'complete logits/KV mismatch')
        require(0 < run['firmware_seconds'] < run['request_through_delivery_seconds'] < 600, 'request timing boundary')
    require(complete['runs'][0]['traces'] == baseline['complete']['runs'][0]['traces'], 'affected traces changed')
    rejection = dict(complete['boundary_rejection']); rejection.pop('wall_seconds')
    old_rejection = dict(baseline['complete']['boundary_rejection']); old_rejection.pop('wall_seconds')
    require(rejection == old_rejection, 'overflow non-mutation/recovery mismatch')
    campaign = reports['campaign']
    require(campaign['status'] == 'PASS' and campaign['watchdog_seconds'] == 1200 and
            0 < campaign['elapsed_seconds'] < 1200 and campaign['runner_sha256'] == sha(ROOT/'zynq/m5_fast_complete.py') and
            campaign['checked_runner_sha256'] == sha(ROOT/'zynq/m5_run.py'), 'campaign watchdog/identity failure')
    released = reports['release']['info_after_close_reopen']
    require(reports['release']['status'] == 'PASS' and
            released['owner'] == released['allocated_pages'] == released['pte_dma'] == 0 and
            reports['release']['runner_sha256'] == sha(ROOT/'zynq/m5_opt_release_check.py'), 'ownership/pages retained')
    require(read(FINAL+'/unload.log').strip() == 'M5 FAST NORMAL UNLOAD PASS', 'normal helper unload missing')
    require('M5 PHYSICAL PASS:' in read(FINAL+'/physical_complete.log') and
            'M5 FAST COMPLETE CAMPAIGN PASS' in read(FINAL+'/physical_complete.log'), 'terminal physical result missing')
    for name in ('requant_probe', 'requant_probe_slow', 'scalar_probe'):
        probe = reports[name]
        require(probe['status'] == 'PASS' and probe['returned']['owner'] == 0 and
                0 < probe['host_seconds'] < 120 and len(probe['records']) == 8, name+' failure')
        runner = 'm5_opt_probe.py' if name == 'scalar_probe' else 'm5_fast_probe.py'
        require(probe['sha256'][runner] == sha(ROOT/'zynq'/runner) and
                probe['sha256']['m5_run.py'] == sha(ROOT/'zynq/m5_run.py'), name+' harness mismatch')
        if name != 'requant_probe_slow':
            require(probe['sha256']['m5_pynq.bit'] == bit and probe['sha256']['m5_pynq.hwh'] == hwh,
                    name+' wrong fast overlay')
        if name.startswith('requant_probe'):
            require(probe['sha256']['probe.bin'] == sha(ROOT/'build/m5_fast_requant_v2/probe.bin'), 'requant probe identity')
            for cpu, sfpu in zip(probe['records'][::2], probe['records'][1::2]):
                require(cpu['checksum'] == sfpu['checksum'] and cpu['elements'] == sfpu['elements'] and
                        0 < sfpu['cycles'] < cpu['cycles'], 'requant exactness/net benefit failed')
    require(reports['scalar_probe']['sha256']['probe.bin'] == baseline['probes']['sha256']['probe.bin'],
            'scalar helper ablation changed firmware')
    for name, marker in ((FINAL+'/native_test.log', 'M5 NUMERICAL FOUNDATION PASS'),
                         (FINAL+'/exact_numerics.log', 'M5 OPT EXACT NUMERICS PASS'),
                         (REPRO+'/native_test.log', 'M5 NUMERICAL FOUNDATION PASS'),
                         ('build/m5_fast_memory.ljzJvY/test.log', 'M5 ACTUAL DUAL-IBEX MEMORY SIMULATION PASS boots=2 aborted_boots=1'),
                         ('build/m5_fast_accelerators.cbbJNX/test.log', 'M5 ACTUAL DUAL-IBEX ACCELERATOR PASS boots=2 packet_abort=1'),
                         ('build/m5_fast_accelerators.cbbJNX/delayed.log', 'M5 ACTUAL DUAL-IBEX ACCELERATOR PASS boots=2 packet_abort=1'),
                         ('build/m5_fast_compliance.xEIhne/result.log', 'rv32imc=25/25 rv32im=8/8 rv32i=44/48+4-xfail rv32Zicsr=6/6 rv32Zifencei=1/1')):
        require(marker in read(name), 'required regression missing: ' + name)
    require(evidence['decisions'] == {'persistent_cache': 'BOUNDED_DEFERMENT',
                                     'new_locality_or_fused_rtl': 'BOUNDED_DEFERMENT',
                                     'prepare': 'RETAIN', 'requant8': 'RETAIN'}, 'candidate disposition missing')


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--evidence', default='docs/m5_fast_evidence.json')
    args = parser.parse_args()
    subprocess.run([sys.executable, '-m', 'scripts.audit_m5_opt'], cwd=ROOT, check=True)
    subprocess.run([sys.executable, '-m', 'scripts.m5_fast_sources', SYNTH+'/resolved_sources'], cwd=ROOT, check=True)
    validate(json.loads(read(args.evidence)))
    print('M5 FAST AUDIT PASS: both fast harts, qualified timing, exact faster model, bounded physical and safe release')


if __name__ == '__main__':
    main()
