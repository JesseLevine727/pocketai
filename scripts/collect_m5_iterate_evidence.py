"""Collect finished three-cycle evidence without board access or overwriting."""
import argparse
import json

from scripts.audit_m5_iterate import ROOT, FINAL, REPRO, VARIANTS, REPORT_PATHS, validate
from scripts.audit_m5_fast import hardware_from_reports
from scripts.audit_m5_opt import sha, statistics_for


def manifest_paths():
    sources = set()
    for pattern in ('runtime/m5_iterate/*', 'firmware/m5_iterate/*', 'scripts/*m5_iterate*.py',
                    'scripts/*m5_iterate*.sh', 'zynq/m5_iterate*.py', 'tests/m5_iterate/*.py',
                    'tests/m5_iterate/*.c', 'tests/m5_iterate/*.json', 'docs/M5_ITERATE*.md'):
        sources.update(str(p.relative_to(ROOT)) for p in ROOT.glob(pattern) if p.is_file())
    sources.update(('scripts/m5_fast_firmware_sources.py', 'scripts/m5_fast_sources.py',
                    'runtime/m5_fast/exact_power2.c.inc', 'runtime/m5_fast/pa_m5_requant.c',
                    'runtime/m5_fast/pa_m5_requant.h', 'runtime/m5/pa_m5_hw.c',
                    'runtime/m5/pa_m5_runtime.c', 'runtime/m5/pa_m5_model.c',
                    'firmware/m5/runtime_firmware.c', 'firmware/m5/memory_test.c',
                    'firmware/m5/memory_test_start.S', 'firmware/m5/memory_test.ld',
                    'zynq/m5_opt_profile.py', 'zynq/m5_run.py', 'zynq/m5_fast_complete.py',
                    'zynq/m5_opt_release_check.py', 'tests/m5/test_numerics.py',
                    'tests/m5/model_ops_host.c', 'zynq/m4_cpu_sfpu.c',
                    'rtl/soc/pa_mailbox.sv', 'rtl/ibex-orig/rtl/ibex_top.sv',
                    'rtl/ibex-orig/rtl/ibex_controller.sv', 'rtl/ibex-orig/rtl/ibex_cs_registers.sv'))
    artifacts = set(REPORT_PATHS.values())
    directories = set(VARIANTS.values()) | {REPRO, 'build/m5_iterate_c2_v1',
                  'build/m5_iterate_wait_v1', 'build/m5_iterate_wait_v2', 'build/m5_iterate_clock_v1'}
    for directory in directories:
        for pattern in ('*.bin', '*.elf', '*.so', '*.log', '*.txt', '*.sha256', '*.json', 'generated/*'):
            artifacts.update(str(p.relative_to(ROOT)) for p in (ROOT/directory).glob(pattern) if p.is_file())
    artifacts.update(('docs/m5_fast_evidence.json', 'build/m5_iterate_unit_tests_v1.log',
                      'build/m5_opt_seed_v1/manifest.json',
                      'build/m4_runtime_fixtures/manifest.json',
                      'build/m5_fast_memory.ljzJvY/sim/Vpa_m5_cluster_top',
                      'build/m5_fast_pynq_finish_v2/m5_pynq.bit',
                      'build/m5_fast_pynq_finish_v2/m5_pynq.hwh'))
    return sources, artifacts


def collect():
    sources, artifacts = manifest_paths()
    reports = {name: json.loads((ROOT/path).read_text()) for name, path in REPORT_PATHS.items()}
    baseline = json.loads((ROOT/'docs/m5_fast_evidence.json').read_text())
    evidence = dict(schema=1, status='PASS', gates={key: 'PASS' for key in
                    ('scope', 'cycle1', 'cycle2', 'cycle3', 'final_decode', 'complete_board', 'release', 'reproduction')},
                    policy=json.loads((ROOT/'tests/m5_iterate/performance_policy.json').read_text()),
                    sources={p: sha(ROOT/p) for p in sorted(sources)},
                    artifacts={p: sha(ROOT/p) for p in sorted(artifacts)},
                    hardware=hardware_from_reports(), reports=reports,
                    statistics={'baseline': baseline['statistics']['requant'],
                                'final': statistics_for(reports['measurement'])},
                    decisions={'cycle1': 'RETAIN', 'cycle2_both_sleep': 'REJECT_TIMER_UNDERCOUNT',
                               'cycle2_hart1_sleep': 'DEFER_NO_MATERIAL_GAIN', 'cycle3': 'RETAIN',
                               'new_rtl': 'NOT_NEEDED', 'persistent_model_cache': 'DEFER'},
                    limitations='Three bounded cycles, one rejected timing diagnostic retained, exact original '
                    'seeded warmup+3 and original complete 2/1/1 requests. No tail, sustained, long-context '
                    'or power claim. No hidden preparation, precision change, RTL change or push.')
    validate(evidence)
    return evidence


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output', default='docs/m5_iterate_evidence.json')
    args = parser.parse_args()
    target = ROOT/args.output
    if target.exists():
        raise ValueError('use a fresh evidence output')
    target.write_text(json.dumps(collect(), indent=2)+'\n')
    print('M5 ITERATE EVIDENCE COLLECTED', target)


if __name__ == '__main__':
    main()
