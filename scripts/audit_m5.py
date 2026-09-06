"""Read-only audit of the user-selected lean M5 closure evidence."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from scripts.check_m5_sources import check as check_cpu_sources

ROOT = Path(__file__).resolve().parents[1]


def require(value, message):
    if not value:
        raise ValueError(message)


def read(name):
    return json.loads((ROOT / name).read_text())


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(4 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', default='docs/m5_closure_evidence.json')
    args = parser.parse_args()
    evidence = read(args.evidence)
    require(evidence['schema'] == 1, 'unknown evidence schema')
    require(evidence['status'] == 'PASS', 'closure is not marked qualified')
    for section in ('sources', 'artifacts'):
        for name, expected in evidence[section].items():
            require(sha(ROOT / name) == expected, f'stale {section}: {name}')
    hardware = evidence['hardware']
    work = ROOT / hardware['directory'] / 'resolved_sources'
    check_cpu_sources(work)
    lines = ''.join(f'{sha(path)}  {path.relative_to(work).as_posix()}\n'
                    for path in sorted((work / 'src').rglob('*')) if path.is_file())
    require(hashlib.sha256(lines.encode()).hexdigest() == hardware['resolved_sources_sha256'],
            'resolved hardware source tree changed')
    require(hardware['terminal_exit'] == 0 and hardware['warning_review_terminal_exit'] == 0,
            'hardware build/review did not complete')
    require(hardware['clock_hz'] == 91000000 and hardware['setup_wns_ns'] >= .250
            and hardware['setup_tns_ns'] == 0 and hardware['hold_wns_ns'] > 0
            and hardware['hold_tns_ns'] == 0 and hardware['dsp'] == 0
            and hardware['routing_errors'] == 0 and hardware['drc_errors'] == 0
            and hardware['drc_critical'] == 0 and hardware['methodology_errors'] == 0
            and hardware['methodology_critical'] == 0, 'hardware gate failed')

    foundation = read('docs/m5_runtime_foundation_evidence.json')
    for name, expected in foundation['sources'].items():
        require(sha(ROOT / name) == expected, f'numerical foundation invalidated: {name}')
    require(foundation['host']['generation_tokens'] == 60 and
            foundation['host']['trace_tensors'] == 396 and
            foundation['actual_ibex']['errors'] == 0, 'numerical foundation incomplete')

    allocation = read(evidence['physical']['allocation'])
    require(allocation['status'] == 'PASS' and allocation['allocated']['allocated_pages'] == 65012,
            'full physical allocation missing')
    require(allocation['after_close_reopen']['allocated_pages'] == 0 and
            allocation['after_close_reopen']['owner'] == 0, 'allocation cleanup failed')
    startup = read(evidence['physical']['startup'])
    require(startup['status'] == 'PASS' and startup['control'][23] == 3 and
            startup['hart_results'][:4] == [5, 0x80000000, 5, 0x40010000] and
            startup['dma_after_return']['owner'] == 0, 'physical precise-fault startup missing')

    report = read(evidence['physical']['model'])
    require(report == read('docs/m5_physical_evidence.json'),
            'committed physical report differs from accepted original')
    require(report['status'] == 'PASS' and report.get('cleanup_error') is None and
            report['cleanup'] == 'ownership returned and mappings/file closed' and
            report['dma']['owner'] == 0, 'physical model or cleanup incomplete')
    require(evidence['physical']['terminal_exit'] == 0 and
            evidence['physical']['normal_unload'] is True, 'board lifecycle did not finish')
    policy = read('tests/m5/performance_policy.json')
    require(report['policy'] == policy and report['sha256']['policy'] ==
            'fe614e2d33764cb0f1a6ae587573e80c94abbc4af391267e65116adf8a3ad36f',
            'premeasurement policy changed')
    require(report['clock_hz'] == hardware['clock_hz'], 'physical clock mismatch')
    require(report['sha256']['bitstream'] == sha(ROOT / hardware['directory'] / 'm5_pynq.bit') and
            report['sha256']['hwh'] == sha(ROOT / hardware['directory'] / 'm5_pynq.hwh'),
            'physical hardware differs from qualified build')
    require(report['sha256']['firmware_readback'] == startup['firmware_sha256'] ==
            report['sha256']['firmware_file'], 'firmware identity/readback mismatch')
    require(report['allocated_bytes'] == 266289152, 'model/cache capacity reduced')
    require(report['sha256']['fixtures'] ==
            '7324fb3a88c9b7340e9aa65ea6dd43f77253f0ddf7e7aca9fb100f47f963c537',
            'reference identity changed')
    fixture = read('build/m4_runtime_fixtures/manifest.json')
    reference = {case['id']: case for case in fixture['generation']}
    require(len(report['runs']) == len(policy['matrix']) == 3, 'short campaign incomplete')
    for run, trial in zip(report['runs'], policy['matrix']):
        case = reference[trial['prompt']]
        count = trial['new_tokens']
        final = case['steps'][count - 1]
        require(run['id'] == trial['prompt'] and run['prompt_tokens'] == case['input_tokens'] and
                run['generated_tokens'] == [step['token'] for step in case['steps'][:count]],
                'non-exact token sequence')
        require(run['logits_sha256'] == final['logits_sha256'] and
                run['kv_sha256'] == final['cache_sha256'], 'non-exact full logits/KV')
        require(run['cache_valid'] == len(case['input_tokens']) + count - 1 and
                run['work_high_water'] <= 4194304 - 12288 and run['transfers'] > 0,
                'runtime capacity/counters inconsistent')
        require(len(run['decode_seconds']) == count - 1, 'decode sample count inconsistent')
        duration = run['request_through_delivery_seconds']
        require(math.isfinite(duration) and duration > 0 and
                math.isclose(run['request_tokens_per_second'], count / duration) and
                0 < run['firmware_seconds'] <= duration and
                0 < run['ttft_seconds'] <= run['firmware_seconds'],
                'invalid throughput boundary')
        if trial['capture_prefill']:
            require([trace['name'] for trace in run['traces']] ==
                    ['embedding', 'h.0.qkv', 'h.0.context', 'h.0.output', 'h.11.output'],
                    'selected trace coverage incomplete')
    rejected = report['boundary_rejection']
    require(rejected['state'] == 5 and rejected['error'] == 1 and
            rejected['cache_valid'] == 17 and rejected['generated_count'] == 19 and
            rejected['output_sentinel_unchanged'] and len(rejected['cache_regions_unchanged']) == 4,
            'overflow non-mutation check incomplete')
    print('M5 LEAN CLOSURE AUDIT PASS: exact physical model, safe ownership, qualified sources/timing')


if __name__ == '__main__':
    main()
