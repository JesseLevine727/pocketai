"""Read-only evidence audit for three bounded scalar-search cycles."""
import argparse
import json
import subprocess
import sys

from scripts.audit_m5_opt import ROOT, sha, require, statistics_for
from scripts.audit_m5_scalar import validate_runs

FINAL = 'build/m5_search_product_v1'
REPRO = 'build/m5_search_repro_v1'
CANDIDATES = dict(lto='build/m5_search_lto_v1', fusion='build/m5_search_fusion_v2', product=FINAL)
DECISIONS = dict(lto='REJECT_NO_GAIN', fusion='RETAIN', product='RETAIN')
REPORTS = {name: directory+'/diagnostic.json' for name, directory in CANDIDATES.items()}
REPORTS.update({name: FINAL+'/'+file for name, file in (
    ('measurement', 'measurement.json'), ('complete', 'physical_complete.json'),
    ('campaign', 'campaign.json'), ('release', 'release.json'))})


def read(path):
    return (ROOT/path).read_text()


def manifest_paths():
    sources = set()
    for pattern in ('runtime/m5_search/*', 'tests/m5_search/*.py', 'tests/m5_search/*.c',
                    'scripts/*m5_search*', 'docs/M5_SEARCH*.md'):
        sources.update(str(p.relative_to(ROOT)) for p in ROOT.glob(pattern) if p.is_file())
    sources.update(('scripts/m5_scalar_sources.py', 'scripts/build_m5_scalar.sh',
                    'scripts/audit_m5_scalar.py', 'tests/m5_iterate/performance_policy.json',
                    'zynq/m5_iterate_profile.py', 'zynq/m5_opt_profile.py', 'zynq/m5_run.py',
                    'zynq/m5_fast_complete.py', 'zynq/m5_opt_release_check.py'))
    artifacts = {'docs/m5_scalar_evidence.json'}
    for directory in set(CANDIDATES.values()) | {REPRO}:
        for pattern in ('*.bin', '*.elf', '*.so', '*.log', '*.txt', '*.json', '*.sha256', 'generated/*'):
            artifacts.update(str(p.relative_to(ROOT)) for p in (ROOT/directory).glob(pattern) if p.is_file())
    return sources, artifacts


def validate(evidence, check_files=True):
    require(evidence['schema'] == 1 and evidence['status'] == 'PASS', 'goal not closed')
    require(evidence['decisions'] == DECISIONS, 'unexpected retained combination')
    old = json.loads(read('docs/m5_scalar_evidence.json'))
    require(evidence['baseline_sha256'] == sha(ROOT/'docs/m5_scalar_evidence.json'), 'baseline changed')
    require(evidence['measured_configurations'] == list(CANDIDATES), 'search scope changed')
    if check_files:
        sources, artifacts = manifest_paths()
        require(set(evidence['sources']) == sources and set(evidence['artifacts']) == artifacts, 'manifest incomplete')
        for key in ('sources', 'artifacts'):
            for path, digest in evidence[key].items():
                require(sha(ROOT/path) == digest, 'changed '+key+': '+path)
        for name, path in REPORTS.items():
            require(evidence['reports'][name] == json.loads(read(path)), 'embedded report changed')
    policy = json.loads(read('tests/m5_iterate/performance_policy.json'))
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
        validate_runs(report, expected['m5_profile.bin'], 2026052, roles)
        if not measured:
            elapsed = report['runs'][1]['model_seconds']
            if name == 'lto':
                require(elapsed >= previous, 'compiler rejection lacks measured basis')
            else:
                require(elapsed < previous, 'retained candidate lacks measured improvement')
                previous = elapsed
    stats = statistics_for(reports['measurement'])
    require(evidence['statistics'] == {'baseline': old['statistics']['final'], 'final': stats}, 'statistics changed')
    for key in ('model_seconds', 'host_request_through_delivery_seconds'):
        require(stats[key]['mean'] < old['statistics']['final'][key]['mean'], 'no final improvement')
    for name in ('m5_runtime.bin', 'm5_profile.bin', 'm5_fine.bin'):
        require(sha(ROOT/FINAL/name) == sha(ROOT/REPRO/name), 'firmware reproduction mismatch')
    for directory in (FINAL, REPRO):
        require(sha(ROOT/directory/'generated/hardware.c') == sha(ROOT/'runtime/m5/pa_m5_hw.c'), 'controller/WFI changed')
        derivation = json.loads(read(directory+'/generated/search_derivation.json'))
        require(derivation['variant'] == 'product', 'wrong release variant')
        for file, digest in derivation['files'].items():
            require(sha(ROOT/directory/'generated'/file) == digest, 'generated source changed')
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
    for file, marker in (('specialization_test.log', 'M5 SEARCH I32 BINARY64 EXACT PASS 1033040'),
                         ('specialization_test.log', 'M5 SEARCH FUSION EXACT PASS 2916'),
                         ('attention_test.log', 'M5 SCALAR ATTENTION LAYOUT EXACT PASS 15'),
                         ('uniform_test.log', 'M5 SCALAR UNIFORM EXACT PASS 1188')):
        require(marker in read(FINAL+'/'+file), 'operator gate missing')
    complete, prior = reports['complete'], old['reports']['complete']
    require(complete['status'] == 'PASS' and complete['clock_hz'] == 91000000 and complete['dma']['owner'] == 0 and
            not complete.get('cleanup_error') and complete['allocated_bytes'] == 266289152,
            'complete model/arena/cleanup failed')
    require(complete['policy'] == prior['policy'] and len(complete['runs']) == 3, 'complete scope changed')
    expected = dict(prior['sha256'])
    expected['firmware_file'] = expected['firmware_readback'] = sha(ROOT/FINAL/'m5_runtime.bin')
    require(complete['sha256'] == expected, 'complete source/artifact identity changed')
    for run, original in zip(complete['runs'], prior['runs']):
        for key in ('id', 'prompt_tokens', 'generated_tokens', 'logits_sha256', 'kv_sha256', 'cache_valid', 'traces',
                    'work_high_water', 'transfers', 'tensor_bytes_read', 'tensor_bytes_written'):
            require(run.get(key) == original.get(key), 'complete exact result changed: '+key)
        require(0 < run['firmware_seconds'] < run['request_through_delivery_seconds'] < 600, 'complete time invalid')
    for key, value in prior['boundary_rejection'].items():
        if key != 'wall_seconds': require(complete['boundary_rejection'][key] == value, 'overflow/recovery changed')
    campaign = reports['campaign']
    require(campaign['status'] == 'PASS' and campaign['watchdog_seconds'] == 1200 and 0 < campaign['elapsed_seconds'] < 1200 and
            campaign['runner_sha256'] == sha(ROOT/'zynq/m5_fast_complete.py') and
            campaign['checked_runner_sha256'] == sha(ROOT/'zynq/m5_run.py'), 'campaign gate failed')
    release = reports['release']; info = release['info_after_close_reopen']
    require(release['status'] == 'PASS' and info['owner'] == info['allocated_pages'] == info['pte_dma'] == 0 and
            release['runner_sha256'] == sha(ROOT/'zynq/m5_opt_release_check.py'), 'DMA resources retained')
    require(read(FINAL+'/unload.log').strip() == 'M5 SEARCH NORMAL UNLOAD PASS', 'normal unload missing')
    require('M5 PHYSICAL PASS:' in read(FINAL+'/physical_complete.log'), 'terminal board pass missing')


def collect():
    sources, artifacts = manifest_paths()
    reports = {name: json.loads(read(path)) for name, path in REPORTS.items()}
    old = json.loads(read('docs/m5_scalar_evidence.json'))
    evidence = dict(schema=1, status='PASS', baseline_sha256=sha(ROOT/'docs/m5_scalar_evidence.json'),
                    decisions=DECISIONS, measured_configurations=list(CANDIDATES), reports=reports,
                    sources={p: sha(ROOT/p) for p in sorted(sources)}, artifacts={p: sha(ROOT/p) for p in sorted(artifacts)},
                    statistics={'baseline': old['statistics']['final'], 'final': statistics_for(reports['measurement'])},
                    accounting='Per-forward lazy table initialization/misses remain inside model time; no persistent cache or untimed preparation.',
                    limitations='Three bounded configurations; short fixed-context samples, not sustained/tail/long-context performance or a global optimum.')
    validate(evidence)
    return evidence


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--collect', action='store_true')
    parser.add_argument('--evidence', default='docs/m5_search_evidence.json')
    args = parser.parse_args()
    subprocess.run([sys.executable, '-m', 'scripts.audit_m5_scalar'], cwd=ROOT, check=True)
    if args.collect:
        target = ROOT/args.evidence
        if target.exists(): raise ValueError('use a fresh evidence output')
        target.write_text(json.dumps(collect(), indent=2)+'\n')
    else:
        validate(json.loads(read(args.evidence)))
    print('M5 SEARCH AUDIT PASS: three measured cycles, exact faster firmware, unchanged hardware and safe release')


if __name__ == '__main__':
    main()
