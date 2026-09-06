"""Collect completed local reports only; refuses incomplete gates or overwrite."""
import json
from pathlib import Path
from scripts.audit_m5_opt import ROOT, REPORT_PATHS, sha, statistics_for, validate


def main():
    output = ROOT/'docs/m5_opt_evidence.json'
    if output.exists():
        raise ValueError('refusing to overwrite optimization evidence')
    paths = REPORT_PATHS
    raw = {key: json.loads((ROOT/path).read_text()) for key, path in paths.items()}
    sources = set()
    for pattern in ('runtime/m5_opt/*.c', 'runtime/m5/*.[ch]', 'firmware/m5_opt/*.c',
                    'tests/m5_opt/*.py', 'tests/m5_opt/*.json', 'zynq/m5_opt*.py',
                    'scripts/*m5_opt*.py', 'scripts/build_m5_opt*.sh'):
        sources.update(str(p.relative_to(ROOT)) for p in ROOT.glob(pattern))
    sources.update(('firmware/m5/runtime_firmware.c', 'firmware/m5/memory_test_start.S',
                    'firmware/m5/memory_test.ld', 'zynq/m5_run.py', 'tests/m5/test_numerics.py',
                    'tests/m5/model_ops_host.c', 'zynq/m4_cpu_sfpu.c'))
    artifacts = set(paths.values())
    for directory in ('m5_opt_profile', 'm5_opt_shift', 'm5_opt_metadata', 'm5_opt_reuse'):
        artifacts.update('build/'+directory+'/'+name for name in ('m5_profile.bin', 'm5_profile.elf', 'sha256.txt', 'size.txt'))
    artifacts.update('build/m5_opt_runtime/'+name for name in (
        'm5_runtime.bin', 'm5_runtime.elf', 'native.so', 'native_test.log', 'exact_test.log', 'exact_edge_test.log',
        'sha256.txt', 'attributes.txt', 'size.txt', 'unload.log', 'physical_complete.log'))
    artifacts.update('build/m5_opt_seed_v1/'+name for name in ('manifest.json', 'k.bin', 'v.bin', 'k8.bin', 'kunits.bin'))
    artifacts.update(('build/m5_opt_probe/probe.bin', 'build/m5_opt_probe/sha256.txt',
                      'build/m4_runtime_fixtures/manifest.json',
                      'build/m5_opt_runtime_repro/m5_runtime.bin',
                      'build/m5_opt_runtime_repro/sha256.txt'))
    report = {'schema': 1, 'status': 'PASS',
              'baseline_commit': 'd0398d39a0d6252a8c0148be06a2075b8c937049',
              'policy': json.loads((ROOT/'tests/m5_opt/performance_policy.json').read_text()),
              'sources': {p: sha(ROOT/p) for p in sorted(sources)},
              'artifacts': {p: sha(ROOT/p) for p in sorted(artifacts)},
              'decode': {k: raw[k] for k in ('baseline', 'shift', 'metadata', 'reuse')},
              'statistics': {k: statistics_for(raw[k]) for k in ('baseline', 'shift', 'metadata', 'reuse')},
              'complete': raw['complete'], 'release': raw['release'], 'probes': raw['probes'],
              'precision': raw['precision'],
              'six_points': {'1_profile': 'PASS', '2_software': 'PASS',
                             '3_new_bram_cache': 'MEASURED_DEFERMENT',
                             '4_asynchronous_dataflow': 'MEASURED_DEFERMENT',
                             '5_exact_arithmetic': 'PASS_NO_RTL_CHANGE',
                             '6_precision': 'W4A8_CANDIDATE_REJECTED_W4A4_DEFERRED'},
              'limitations': 'See docs/M5_OPTIMIZATION_RESULTS.md: small fixed-context samples and 2/1/1 complete requests, no new 1024 endurance, FPGA rebuild, packed W4 performance or M6.'}
    validate(report)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print('M5 OPT EVIDENCE COLLECTED', output)


if __name__ == '__main__':
    main()
