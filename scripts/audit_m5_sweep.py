"""Read-only chained audit of bounded frozen-release characterization evidence."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

from scripts.m5_sweep_policy import ROOT, BUILD, sha
from scripts.analyze_m5_sweep import summarize, csv_text, continuation_csv, tables


def require(condition, message):
    if not condition:
        raise ValueError(message)


def finite_positive(value):
    return isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def paths():
    sources = {str(p.relative_to(ROOT)) for pattern in ('scripts/*m5_sweep*.py',
        'zynq/m5_sweep.py', 'tests/m5_sweep/*.py', 'docs/M5_SWEEP*.md') for p in ROOT.glob(pattern)}
    artifacts = {str(p.relative_to(ROOT)) for p in BUILD.rglob('*') if p.is_file()}
    artifacts.update(('docs/m5_sweep_samples.csv', 'docs/m5_sweep_continuation.csv'))
    return sources, artifacts


def validate(evidence, files=True):
    require(evidence['schema'] == 1 and evidence['status'] == 'PASS', 'unclosed sweep')
    report, refs = evidence['campaign'], evidence['references']
    policy = evidence['policy']
    require(policy == report['policy'] and policy['board_budget_seconds'] == 3600 and
            policy['cleanup_reserve_seconds'] == 120 and policy['reference_budget_seconds'] == 600,
            'budget/policy changed')
    require(policy['frozen_git'] == 'e5883bcc99ad61bba381714781febb873a1101e3' and
            policy['clock_hz'] == report['clock_hz'] == 91000000, 'release changed')
    require(report['status'] == refs['status'] == 'PASS' and report['within_budget'] and
            0 < report['elapsed_seconds'] <= 3600 and 0 < refs['elapsed_seconds'] <= 601,
            'failed or over-budget campaign/reference preparation')
    require(report['normal_unload'] and not report.get('cleanup_error') and
            report['dma_after_return']['owner'] == 0 and
            all(report['info_after_close_reopen'][k] == 0 for k in ('owner', 'pte_dma', 'allocated_pages')),
            'unsafe/leaking cleanup')
    require(report['allocated_bytes'] == 266289152, 'mapped memory changed')
    require(report['policy_sha256'] == refs['policy_sha256'], 'reference policy binding changed')
    for name, digest in policy['pinned'].items():
        require(report['sha256'][name] == digest, 'measured pinned file changed: '+name)
    require([i['trial'] for i in report['trials']] == policy['matrix'], 'missing/reordered sample or skip')
    passed = []
    for item in report['trials']:
        trial = item['trial']
        require(item['status'] in ('PASS', 'SKIP'), 'failed experiment cannot close PASS')
        if item['status'] == 'SKIP':
            require(item.get('reason') in ('independent reference unavailable within preparation guard',
                'conservative case bound would consume cleanup reserve'), 'unexplained skip')
            continue
        passed.append(trial)
        require(finite_positive(item['case_elapsed_seconds']) and
                item['bound_exceeded'] == (item['case_elapsed_seconds'] > trial['bound_seconds']),
                'slow-case accounting changed')
        require(item['started_campaign_seconds'] >= 0 and item['started_campaign_seconds'] +
                trial['bound_seconds'] + 120 <= 3600, 'inadmissible case was started')
        r = item['result']
        if trial['kind'] == 'full':
            case = refs['cases'][trial['case']]
            n = trial['new_tokens']
            expected = case['steps'][n-1]
            require(r['id'] == case['id'] and r['prompt_tokens'] == case['input_tokens'] and
                    r['generated_tokens'] == [s['token'] for s in case['steps'][:n]] and
                    r['cache_valid'] == len(case['input_tokens'])+n-1, 'full request identity/tokens/cache changed')
            model, delivered = r['firmware_seconds'], r['request_through_delivery_seconds']
            require(len(r['decode_seconds']) == n-1 and all(finite_positive(t) for t in r['decode_seconds']),
                    'missing finite-run continuation intervals')
            require(0 < r['prefill_forward_seconds'] <= r['ttft_seconds'] <= model and
                    math.isclose(r['ttft_seconds']+sum(r['decode_seconds']), model, abs_tol=.001),
                    'model timing boundaries do not reconcile')
            require(r['device_wall_seconds'] <= r['request_wall_seconds'] <= delivered and
                    r['request_tokens_per_second'] == n/delivered, 'delivery accounting changed')
            if trial['capture']:
                require(len(r['traces']) == 5, 'original traces omitted')
        else:
            seed = refs['seeds'][str(trial['past'])]
            expected = seed['expected']
            require(r['status'] == 'PASS' and r['token'] == expected['token'] and
                    r['cache_valid'] == trial['past']+1 and
                    r['firmware_sha256'] == policy['pinned']['m5_profile.bin'], 'cached result identity changed')
            model, delivered = r['model_seconds'], r['host_request_through_delivery_seconds']
            require(model == r['model_cycles']/91000000 and r['profile_enabled'] == trial['profile'],
                    'profile/model cycle accounting changed')
            if trial['profile']:
                order = [(1, 0)] + [(kind, layer) for layer in range(12) for kind in range(2, 10)]
                order += [(10, 0), (11, 0), (12, 0)]
                require([(p['kind'], p['layer']) for p in r['phases']] == order, 'missing phase coverage')
                for p in r['phases']:
                    require(0 <= p['gemm_cycles']+p['sfpu_cycles'] <= p['service_cycles'] <= p['cycles'] and
                            p['cpu_remainder_cycles'] == p['cycles']-p['service_cycles'], 'nested phase times invalid')
                for counter, metric in (('service_cycles', 'service_seconds'), ('gemm_cycles', 'gemm_compute_seconds'),
                                         ('sfpu_cycles', 'sfpu_compute_seconds')):
                    require(sum(p[counter] for p in r['phases'])/91000000 == r[metric], 'profile totals changed')
                require(math.isclose(r['service_seconds']+r['cpu_remainder_seconds'], model, abs_tol=1e-9),
                        'remainder accounting changed')
            else:
                require(not r['phases'] and r['service_seconds'] is None, 'diagnostics contaminate plain samples')
        require(finite_positive(model) and finite_positive(delivered) and model < delivered <= item['case_elapsed_seconds'],
                'invalid measurement boundary')
        require(r['logits_sha256'] == expected['logits_sha256'] and r['kv_sha256'] == expected['cache_sha256'],
                'all-logit/complete-valid-KV check changed')
    require(sum(t['role'] == 'original_anchor' for t in passed) == 3 and
            sum(t['role'] == 'uninterrupted_generation' for t in passed) >= 2, 'required request gates missing')
    require(sum(t['kind'] == 'cached' and t['past'] == 13 and not t['profile'] for t in passed) == 3,
            'repeated matched anchor missing')
    require(evidence['summary'] == summarize(report), 'summary changed or cherry-picked')
    if files:
        require(evidence['reused_hardware'] == json.loads((ROOT/'docs/m5_fast_evidence.json').read_text())['hardware'],
                'reused hardware timing/resources changed')
        sources, artifacts = paths()
        require(set(evidence['sources']) == sources and set(evidence['artifacts']) == artifacts, 'incomplete manifest')
        for category in ('sources', 'artifacts'):
            for path, digest in evidence[category].items():
                require(sha(ROOT/path) == digest, 'changed file: '+path)
        require(evidence['baseline_sha256'] == sha(ROOT/'docs/m5_tenth_evidence.json'), 'qualified baseline changed')
        for key, name in (('policy', 'policy.json'), ('campaign', 'campaign.json'),
                          ('references', 'references/manifest.json'), ('summary', 'summary.json')):
            require(evidence[key] == json.loads((BUILD/name).read_text()), 'embedded evidence changed: '+key)
        require(report['reference_manifest_sha256'] == sha(BUILD/'references/manifest.json') and
                report['policy_sha256'] == sha(BUILD/'policy.json'), 'measured manifest hash mismatch')
        require(report['sha256']['m5_sweep.py'] == sha(ROOT/'zynq/m5_sweep.py'), 'executed harness changed')
        old = json.loads((ROOT/'docs/m5_tenth_evidence.json').read_text())['reports']['complete']
        require(report['sha256']['layout.json'] == old['sha256']['layout'] and
                report['sha256']['model.bin'] == old['sha256']['model'], 'model layout changed')
        for k, v in old['boundary_rejection'].items():
            if k != 'wall_seconds':
                require(report['boundary_rejection'][k] == v, 'overflow non-mutation/recovery changed')
        anchor = next(i['result'] for i in report['trials'] if i['trial']['capture'])
        require(anchor['traces'] == old['runs'][0]['traces'], 'qualified internal traces changed')
        original = json.loads((ROOT/'build/m4_runtime_fixtures/manifest.json').read_text())
        for case in original['generation']:
            require(refs['cases'][case['id']] == case, 'qualified original oracle changed')
        for name, seed in refs['seeds'].items():
            require(seed['past'] == int(name) and seed['continuation_checked'] and
                    set(seed['arrays']) == {'k', 'v', 'k8', 'kunits'}, 'invalid independent seed')
            for array, entry in seed['arrays'].items():
                path = BUILD/f'references/p{name}/seed'/entry['file']
                require(path.stat().st_size == entry['bytes'] and sha(path) == entry['sha256'], 'seed image changed')
        for path, digest in refs['sources'].items():
            require(sha(ROOT/path) == digest, 'independent oracle source changed')
        require((BUILD/'samples.csv').read_text() == csv_text(evidence['summary']).replace('\r\n', '\n'), 'CSV differs from all samples')
        require((BUILD/'continuation.csv').read_text() == continuation_csv(report).replace('\r\n', '\n'), 'per-token CSV changed')
        require((BUILD/'tables.md').read_text() == tables(evidence['summary']), 'generated tables changed')
        require((ROOT/'docs/m5_sweep_samples.csv').read_text() == (BUILD/'samples.csv').read_text(), 'published samples changed')
        require((ROOT/'docs/m5_sweep_continuation.csv').read_text() == (BUILD/'continuation.csv').read_text(), 'published intervals changed')


def collect():
    sources, artifacts = paths()
    evidence = dict(schema=1, status='PASS', baseline_sha256=sha(ROOT/'docs/m5_tenth_evidence.json'),
                    reused_hardware=json.loads((ROOT/'docs/m5_fast_evidence.json').read_text())['hardware'],
                    sources={p: sha(ROOT/p) for p in sorted(sources)},
                    artifacts={p: sha(ROOT/p) for p in sorted(artifacts)})
    for key, name in (('policy', 'policy.json'), ('campaign', 'campaign.json'),
                      ('references', 'references/manifest.json'), ('summary', 'summary.json')):
        evidence[key] = json.loads((BUILD/name).read_text())
    validate(evidence)
    return evidence


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--collect', action='store_true')
    args = parser.parse_args()
    path = ROOT/'docs/m5_sweep_evidence.json'
    if args.collect:
        path.write_text(json.dumps(collect(), indent=2)+'\n')
    validate(json.loads(path.read_text()))
    subprocess.run([sys.executable, '-m', 'scripts.audit_m5_tenth'], cwd=ROOT, check=True)
    subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests/m5_sweep', '-v'], cwd=ROOT, check=True)
    print('M5 SWEEP AUDIT PASS: frozen release, exact bounded characterization, safe normal release')


if __name__ == '__main__':
    main()
