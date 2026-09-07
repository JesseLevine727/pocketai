"""Read-only audit of exact maximum-context performance and its measurement boundary."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
from scripts.m5_sweep_policy import ROOT, sha
from scripts.audit_m5_sweep import require, finite_positive

FINAL = 'build/m5_context_masked_v2'
REPRO = 'build/m5_context_masked_repro_v1'
CAMPAIGNS = {
    'original_attention_detail': 'build/m5_context_diagnostic_v1',
    **{name: f'build/m5_context_{name}_diag_v1' for name in
       ('ready', 'score', 'smooth', 'product', 'local', 'parallel', 'dual', 'direct')},
    'qualification_attempt': 'build/m5_context_final_story_v1',
    'direct_story_plain': 'build/m5_context_final_story_v2',
    'direct_science_miss': 'build/m5_context_final_science_v1',
    **{name+'_science': f'build/m5_context_{name}_science_diag_v1' for name in
       ('position', 'combined', 'masked')},
    'final_story': 'build/m5_context_masked_final_story_v1',
    'final_science': 'build/m5_context_masked_final_science_v1',
    'matched_baseline': 'build/m5_context_matched_baseline_v1',
}


def stats(values):
    return dict(count=len(values), mean=sum(values)/len(values), minimum=min(values),
                maximum=max(values), pooled_tokens_per_second=len(values)/sum(values))


def summary(reports):
    result = {}
    for name, report in reports.items():
        cached = [i['result'] for i in report['trials'] if i['trial']['kind'] == 'cached']
        warm = [r for r in cached if r.get('context_role') == 'warm_last_slot']
        cold = [r for r in cached if r.get('context_role') == 'cold_initialization_in_model']
        result[name] = dict(status=report['status'], campaign_seconds=report['elapsed_seconds'],
            trials=len(report['trials']),
            warm_delivered=stats([r['host_request_through_delivery_seconds'] for r in warm]) if warm else None,
            warm_model=stats([r['model_seconds'] for r in warm]) if warm else None,
            cold_delivered=stats([r['host_request_through_delivery_seconds'] for r in cold]) if cold else None,
            full_requests=[dict(id=i['trial']['id'], tokens=i['trial']['new_tokens'],
                model_seconds=i['result']['firmware_seconds'],
                delivered_seconds=i['result']['request_through_delivery_seconds'],
                tokens_per_second=i['trial']['new_tokens']/i['result']['request_through_delivery_seconds'])
                for i in report['trials'] if i['trial']['kind'] == 'full' and i['status'] == 'PASS'])
    return result


def manifest_paths():
    sources = set()
    for pattern in ('runtime/m5_context/*', 'scripts/*m5_context*', 'zynq/m5_context*.py',
                    'tests/m5_context/*.py', 'tests/m5_context/*.c', 'docs/M5_CONTEXT*.md'):
        sources.update(str(p.relative_to(ROOT)) for p in ROOT.glob(pattern) if p.is_file())
    artifacts = set()
    for directory in ROOT.glob('build/m5_context_*'):
        if directory.is_dir():
            for p in directory.rglob('*'):
                if p.is_file() and '__pycache__' not in p.parts:
                    artifacts.add(str(p.relative_to(ROOT)))
    return sources, artifacts


def validate_campaign(report, refs, failed_attempt=False):
    policy = report['policy']
    require(report['status'] == ('FAIL' if failed_attempt else 'PASS') and refs['status'] == 'PASS' and report['within_budget'] and
            0 < report['elapsed_seconds'] <= 3600 and policy['board_budget_seconds'] == 3600 and
            policy['cleanup_reserve_seconds'] == 120 and policy['reference_budget_seconds'] == 600,
            'campaign failed or exceeded bounded budget')
    require(report['clock_hz'] == policy['clock_hz'] == 91000000 and report['allocated_bytes'] == 266289152,
            'clock/arena changed')
    require(policy['pinned']['m5_pynq.bit'] == '6c647a3dc2f0305b9add96d6a8240be2ada9c6d91ac526feb8376a124551c9bc' and
            policy['pinned']['m5_pynq.hwh'] == 'e05c696a5b196cf8e9a3c564108286679b1afb9cc989945bcc71bdbb0342f514',
            'qualified overlay changed')
    require(report['normal_unload'] and not report.get('cleanup_error') and
            report['dma_after_return']['owner'] == 0 and
            all(report['info_after_close_reopen'][k] == 0 for k in ('owner', 'allocated_pages', 'pte_dma')),
            'unsafe or incomplete DMA release')
    require(report['policy_sha256'] == refs['policy_sha256'], 'reference/policy mismatch')
    rejection = report['boundary_rejection']
    require(rejection['state'] == 5 and rejection['error'] == 1 and rejection['cache_valid'] == 17 and
            rejection['generated_count'] == 19 and rejection['output_sentinel_unchanged'] and
            set(rejection['cache_regions_unchanged']) == {'k', 'v', 'k8', 'kunits'} and
            rejection['recovery'] == 'subsequent accepted runs', 'overflow/non-mutation/recovery gate missing')
    for name, digest in policy['pinned'].items():
        require(report['sha256'][name] == digest, 'executed file differs from policy')
    expected_matrix = policy['matrix'][:8] if failed_attempt else policy['matrix']
    require([i['trial'] for i in report['trials']] == expected_matrix, 'missing/reordered experiments')
    if failed_attempt:
        require(report['error'] == "FileNotFoundError(2, 'No such file or directory')" and
                len(report['trials']) == 8 and report['trials'][-1]['trial']['id'] == 'full_science_True' and
                report['trials'][-1]['status'] == 'FAIL', 'unexplained qualification failure')
    previous = None
    for index, item in enumerate(report['trials']):
        missing_trace = failed_attempt and index == 7
        trial, r = item['trial'], item['partial_result'] if missing_trace else item['result']
        require(item['status'] == ('FAIL' if missing_trace else 'PASS') and not item['bound_exceeded'] and
                0 < item['case_elapsed_seconds'] <= trial['bound_seconds'] and
                item['started_campaign_seconds'] >= 0 and
                item['started_campaign_seconds']+trial['bound_seconds']+120 <= 3600,
                'failed/skipped/over-bound experiment')
        if trial['kind'] == 'cached':
            seed = refs['seeds'][str(trial['past'])]; expected = seed['expected']
            require(r['status'] == 'PASS' and r['cache_valid'] == trial['past']+1 and
                    r['token'] == expected['token'] and r['firmware_sha256'] == policy['pinned']['m5_profile.bin'],
                    'cached identity/token changed')
            model, delivered = r['model_seconds'], r['host_request_through_delivery_seconds']
            require(model == r['model_cycles']/91000000 and r['profile_enabled'] == trial['profile'],
                    'model/profile boundary changed')
            if r.get('context_role') == 'warm_last_slot':
                require(previous is not None and previous['cache_valid'] == seed['past'] and
                        previous['token'] == seed['input_token'] and previous['kv_sha256'] == seed['prefill_kv_sha256'],
                        'warm sample uses hidden/future/unmatched state')
            if 'derived_cache' in r:
                state = r['derived_cache']
                require(state['cold_heads'] == 144 and state['appended_vectors'] ==
                        (288 if r['context_role'] == 'warm_last_slot' else 144), 'derived-cache lifecycle changed')
                if r['context_role'] == 'warm_last_slot':
                    require(state['updated_columns'] >= previous['derived_cache']['updated_columns'], 'cache counters rewound')
            if trial['profile']:
                order = [(1, 0)]+[(kind, layer) for layer in range(12) for kind in range(2, 10)]+[(10, 0), (11, 0), (12, 0)]
                require([(p['kind'], p['layer']) for p in r['phases']] == order, 'profile phase coverage changed')
                for p in r['phases']:
                    require(0 <= p['gemm_cycles']+p['sfpu_cycles'] <= p['service_cycles'] <= p['cycles'] and
                            p['cpu_remainder_cycles'] == p['cycles']-p['service_cycles'] and
                            p['seconds'] == p['cycles']/91000000, 'nested costs double counted')
                for counter, metric in (('service_cycles', 'service_seconds'), ('gemm_cycles', 'gemm_compute_seconds'),
                                        ('sfpu_cycles', 'sfpu_compute_seconds')):
                    require(sum(p[counter] for p in r['phases'])/91000000 == r[metric], 'service/engine totals changed')
                require(math.isclose(r['cpu_remainder_seconds']+r['service_seconds'], model, abs_tol=1e-9), 'profile sum changed')
                details = r['attention_detail']
                require(len(details) == 9 and [d['calls'] for d in details] == [12]+[144]*8 and
                        all(d['seconds'] == d['cycles']/91000000 for d in details) and
                        sum(d['cycles'] for d in details)+r['attention_unassigned_cycles'] ==
                        sum(p['cycles'] for p in r['phases'] if p['name'] == 'attention'), 'detail intervals inconsistent')
            else:
                require(not r['phases'] and r['service_seconds'] is None and 'attention_detail' not in r,
                        'instrumentation contaminated primary sample')
            previous = r
        else:
            case = refs['cases'][trial['case']]; n = trial['new_tokens']; expected = case['steps'][n-1]
            require(r['id'] == case['id'] and r['prompt_tokens'] == case['input_tokens'] and
                    r['generated_tokens'] == [s['token'] for s in case['steps'][:n]] and
                    r['cache_valid'] == len(case['input_tokens'])+n-1, 'full request changed')
            model, delivered = r['firmware_seconds'], r['request_through_delivery_seconds']
            require(len(r['decode_seconds']) == n-1 and
                    math.isclose(r['ttft_seconds']+sum(r['decode_seconds']), model, abs_tol=.001), 'full-request accounting changed')
            if trial['capture'] and not missing_trace: require(len(r['traces']) == 5, 'original trace checks omitted')
            previous = None
        require(finite_positive(model) and finite_positive(delivered) and model < delivered <= item['case_elapsed_seconds'],
                'invalid timing interval')
        require(r['logits_sha256'] == expected['logits_sha256'] and r['kv_sha256'] == expected['cache_sha256'],
                'all logits/complete valid KV changed')


def validate(evidence, files=True):
    require(evidence['schema'] == 1 and evidence['status'] == 'PASS' and evidence['m6_started'] is False, 'goal not properly closed')
    require(set(evidence['reports']) == set(CAMPAIGNS), 'missing candidate/final/baseline evidence')
    for name, report in evidence['reports'].items():
        validate_campaign(report, evidence['references'][name], name == 'qualification_attempt')
    require(evidence['summary'] == summary(evidence['reports']), 'statistics omit/change samples')
    for name, count in (('final_story', 3), ('final_science', 3)):
        report = evidence['reports'][name]
        warm = [i for i in report['trials'] if i['trial'].get('past') == 1023]
        require(len(warm) == count and all(not i['trial']['profile'] and
                i['result']['host_request_through_delivery_seconds'] <= 10.0 for i in warm), 'max-context speed gate not passed')
        require(report['policy']['pinned']['m5_profile.bin'] == evidence['binaries']['m5_profile.bin'], 'final binary changed')
        require(report['policy']['pinned']['m5_runtime.bin'] == evidence['binaries']['m5_runtime.bin'], 'final full-request binary changed')
        for item in report['trials']:
            if item['trial']['kind'] == 'cached':
                require('derived_cache' in item['result'] and not item['result'].get('matched_original_baseline'),
                        'final derived-state accounting missing')
    original = evidence['reports']['matched_baseline']['policy']['pinned']
    require(original['m5_runtime.bin'] == '40f93fd566fbbd0d59e6e1cea3c13ccf2e98785da37376be3cae52188590fb17' and
            original['m5_profile.bin'] == '1e3a48c4cabb0e0505e9e4a62835ffeb905c1d52bd6fbf838adebe42f7014097',
            'matched baseline is not the frozen original firmware')
    require(evidence['reports']['masked_science']['policy']['pinned']['m5_profile.bin'] ==
            evidence['binaries']['m5_detail.bin'], 'retained diagnostic binary changed')
    full = [i['trial'] for i in evidence['reports']['final_story']['trials'] if i['trial']['kind'] == 'full']
    require([(i['case'], i['new_tokens'], i['capture']) for i in full] ==
            [('story', 2, True), ('science', 1, False), ('computing', 1, False), ('story', 2, False)], 'full/traced/optimized gates missing')
    baseline = evidence['references']['matched_baseline']['seeds']
    final = evidence['references']['final_story']['seeds']
    for past in ('1022', '1023'):
        require(baseline[past]['expected'] == final[past]['expected'] and
                baseline[past]['prefill_kv_sha256'] == final[past]['prefill_kv_sha256'] and
                baseline[past]['input_token'] == final[past]['input_token'], 'baseline is not matched')
    if files:
        require(evidence['baseline_evidence_sha256'] == sha(ROOT/'docs/m5_sweep_evidence.json'), 'prior closure changed')
        require(evidence['hardware'] == json.loads((ROOT/'docs/m5_fast_evidence.json').read_text())['hardware'], 'qualified hardware changed')
        sources, artifacts = manifest_paths()
        require(set(evidence['sources']) == sources and set(evidence['artifacts']) == artifacts, 'manifest coverage changed')
        for category in ('sources', 'artifacts'):
            for path, digest in evidence[category].items(): require(sha(ROOT/path) == digest, 'changed '+path)
        for name, directory in CAMPAIGNS.items():
            require(evidence['reports'][name] == json.loads((ROOT/directory/'campaign.json').read_text()), 'embedded report changed')
            require(evidence['references'][name] == json.loads((ROOT/directory/'references/manifest.json').read_text()), 'embedded oracle changed')
            require(evidence['reports'][name]['reference_manifest_sha256'] == sha(ROOT/directory/'references/manifest.json'), 'measured oracle binding changed')
            require(evidence['reports'][name]['policy_sha256'] == sha(ROOT/directory/'policy.json'), 'measured policy binding changed')
            if name in ('final_story', 'final_science', 'matched_baseline'):
                for filename in ('m5_context_ready_run.py', 'm5_context_run.py', 'm5_run.py', 'm5_opt_profile.py', 'm5_sweep.py'):
                    require(evidence['reports'][name]['policy']['pinned'][filename] == sha(ROOT/'zynq'/filename), 'final measurement code changed')
        for name, digest in evidence['binaries'].items():
            require(sha(ROOT/FINAL/name) == sha(ROOT/REPRO/name) == digest, 'binary reproduction mismatch')
        for directory in (FINAL, REPRO):
            derivation = json.loads((ROOT/directory/'generated/context_derivation.json').read_text())
            require(derivation['variant'] == 'masked', 'wrong final variant')
            for name, digest in derivation['files'].items(): require(sha(ROOT/directory/'generated'/name) == digest, 'generated source changed')
        for name, marker in (('native_test.log', 'M5 NUMERICAL FOUNDATION PASS'), ('ready_test.log', 'CONTEXT READY FULL MODEL EXACT PASS 60'),
                ('score_test.log', 'CONTEXT SCORE METADATA EXACT PASS 115'),
                ('product_test.log', 'CONTEXT TWO-ROUNDING PRODUCT EXACT PASS 197918'),
                ('local_score_test.log', 'CONTEXT LOCAL SCORES EXACT PASS 40'),
                ('combined_test.log', 'CONTEXT COMBINED SCORES EXACT PASS 84')):
            require(marker in (ROOT/REPRO/name).read_text(), 'native exactness gate missing')
        for directory in ('build/m5_context_story_reference_v2', 'build/m5_context_science_reference_v1'):
            refs = json.loads((ROOT/directory/'manifest.json').read_text())
            require(refs['status'] == 'PASS' and 0 < refs['elapsed_seconds'] <= 600, 'independent prep failed or exceeded bound')
            for path, digest in refs['sources'].items(): require(sha(ROOT/path) == digest, 'independent oracle code changed')
            for entry in refs['seeds']['1022']['arrays'].values():
                path = ROOT/directory/'seed'/entry['file']
                require(path.stat().st_size == entry['bytes'] and sha(path) == entry['sha256'], 'independent seed changed')


def collect():
    sources, artifacts = manifest_paths()
    evidence = dict(schema=1, status='PASS', m6_started=False,
        baseline_evidence_sha256=sha(ROOT/'docs/m5_sweep_evidence.json'),
        hardware=json.loads((ROOT/'docs/m5_fast_evidence.json').read_text())['hardware'],
        sources={p: sha(ROOT/p) for p in sorted(sources)}, artifacts={p: sha(ROOT/p) for p in sorted(artifacts)},
        binaries={name: sha(ROOT/FINAL/name) for name in ('m5_runtime.bin', 'm5_profile.bin', 'm5_detail.bin')},
        reports={name: json.loads((ROOT/directory/'campaign.json').read_text()) for name, directory in CAMPAIGNS.items()},
        references={name: json.loads((ROOT/directory/'references/manifest.json').read_text()) for name, directory in CAMPAIGNS.items()})
    evidence['summary'] = summary(evidence['reports'])
    validate(evidence)
    return evidence


def main():
    p = argparse.ArgumentParser(__doc__); p.add_argument('--collect', action='store_true'); args = p.parse_args()
    path = ROOT/'docs/m5_context_evidence.json'
    if args.collect: path.write_text(json.dumps(collect(), indent=2)+'\n')
    validate(json.loads(path.read_text()))
    subprocess.run([sys.executable, '-m', 'scripts.audit_m5_sweep'], cwd=ROOT, check=True)
    subprocess.run([str(ROOT/'build/m4_venv/bin/python'), '-m', 'unittest', 'discover',
                    '-s', 'tests/m5_context', '-v'], cwd=ROOT, check=True)
    print('M5 MAXIMUM-CONTEXT AUDIT PASS: exact repeated <=10-s delivery, charged cold preparation, unchanged fast hardware, safe release')


if __name__ == '__main__': main()
