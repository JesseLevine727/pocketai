"""Collect finished fast-controller evidence; never accesses hardware or overwrites."""
import argparse
import json

from scripts.audit_m5_fast import (ROOT, HW, SYNTH, FINAL, REPRO, REPORT_PATHS,
                                   FIRMWARE, hardware_from_reports, validate)
from scripts.audit_m5_opt import sha, statistics_for


def manifest_paths():
    sources = set()
    for pattern in ('rtl/m5_fast/*', 'runtime/m5_fast/*', 'firmware/m5_fast/*',
                    'scripts/*m5_fast*.py', 'scripts/*m5_fast*.sh', 'sim/run_m5_fast.sh',
                    'zynq/*m5_fast*.py', 'zynq/*m5_fast*.tcl', 'zynq/*m5_fast*.sh',
                    'tests/m5_fast/*.py', 'tests/m5_fast/*.c', 'tests/m5_fast/*.json',
                    'runtime/m5/*.[ch]', 'runtime/m5_opt/*.[ch]'):
        sources.update(str(p.relative_to(ROOT)) for p in ROOT.glob(pattern) if p.is_file())
    sources.update(('zynq/m5_run.py', 'zynq/m5_opt_profile.py', 'zynq/m5_opt_probe.py',
                    'zynq/m5_opt_release_check.py', 'firmware/m5/runtime_firmware.c',
                    'firmware/m5/memory_test_start.S', 'firmware/m5/memory_test.ld',
                    'firmware/m5/memory_test.c', 'firmware/m5/accelerator_test.c',
                    'tests/m5/test_numerics.py', 'tests/m5/model_ops_host.c', 'zynq/m4_cpu_sfpu.c',
                    'scripts/check_m5_sources.py', 'zynq/build_m5.tcl',
                    'docs/M5_FAST_PLAN.md', 'docs/M5_FAST_DECISIONS.md', 'docs/M5_FAST_RESULTS.md'))
    artifacts = set(REPORT_PATHS.values()) | set(FIRMWARE.values())
    for directory in ('build/m5_fast_runtime_v1', FINAL, REPRO,
                      'build/m5_fast_final_fine_v1', 'build/m5_fast_prepare_v2',
                      'build/m5_fast_fine_v1', 'build/m5_fast_requant_v2'):
        for pattern in ('*.bin', '*.elf', '*.log', '*.txt', '*.sha256', '*.so', 'generated/*'):
            artifacts.update(str(p.relative_to(ROOT)) for p in (ROOT/directory).glob(pattern) if p.is_file())
    for directory in ('build/m5_fast_memory.ljzJvY', 'build/m5_fast_accelerators.cbbJNX',
                      'build/m5_fast_compliance.xEIhne'):
        for pattern in ('*.log', '*.bin', '*.elf', '*.sha256', 'sim/*.eda.yml', 'sim/*.vc',
                        'sim/*__Syms.h', 'sim/*ibex_core*.h', 'sim/*___024root.h',
                        'sim/src/**/*.sv', 'work/**/*.signature.output'):
            artifacts.update(str(p.relative_to(ROOT)) for p in (ROOT/directory).glob(pattern) if p.is_file())
    for pattern in ('reports/*', 'build_scripts/*', 'build_scripts.sha256',
                    'source_configuration.log', 'vivado.log', 'm5_candidate.dcp',
                    'resolved_sources/**/*.sv', 'resolved_sources/**/*.v',
                    'resolved_sources/**/*.svh', 'resolved_sources/**/*.yml',
                    'resolved_sources/**/*.tcl'):
        artifacts.update(str(p.relative_to(ROOT)) for p in (ROOT/SYNTH).glob(pattern) if p.is_file())
    for pattern in ('reports/*', 'm5_pynq.bit', 'm5_pynq.hwh', 'm5_pynq.xsa', 'm5_pynq_final.dcp'):
        artifacts.update(str(p.relative_to(ROOT)) for p in (ROOT/HW).glob(pattern) if p.is_file())
    artifacts.update(('build/m5_fast_finish_v2_stdout.log', 'build/m5_fast_finish_v2.log',
                      'build/m5_fast_finish_tail.tcl', 'build/m5_fast_reset_review_stdout.log',
                      'build/m5_fast_pipeline_compliance.sh', 'build/m5_fast_pipeline_compliance_launch.log',
                      FINAL+'/physical_complete.log', FINAL+'/unload.log',
                      'build/m5_fast_requant_v1/probe.bin', 'build/m5_fast_unit_tests.log',
                      'build/m4_runtime_fixtures/manifest.json', 'build/m5_opt_seed_v1/manifest.json',
                      'docs/m5_opt_evidence.json'))
    for pattern in ('m5_pynq.gen/**/bd_51f2_psr_aclk_0_board.xdc',
                    'm5_pynq.gen/**/bd_de2b_psr_aclk_0_board.xdc'):
        artifacts.update(str(p.relative_to(ROOT)) for p in (ROOT/SYNTH).glob(pattern))
    return sources, artifacts


def collect():
    raw = {key: json.loads((ROOT/path).read_text()) for key, path in REPORT_PATHS.items()}
    baseline = json.loads((ROOT/'docs/m5_opt_evidence.json').read_text())
    sources, artifacts = manifest_paths()
    evidence = dict(schema=1, status='PASS', gates={f'F{i}': 'PASS' for i in range(8)},
                    baseline_commit='c40d7cd7effd3e03dfc0d42232f8c4ebb61d4f9c',
                    policy=json.loads((ROOT/'tests/m5_fast/performance_policy.json').read_text()),
                    sources={p: sha(ROOT/p) for p in sorted(sources)},
                    artifacts={p: sha(ROOT/p) for p in sorted(artifacts)},
                    hardware=hardware_from_reports(), reports=raw,
                    statistics={'slow': baseline['statistics']['reuse'],
                                **{key: statistics_for(raw[key]) for key in ('fast_only', 'prepared', 'requant')}},
                    decisions={'persistent_cache': 'BOUNDED_DEFERMENT',
                               'new_locality_or_fused_rtl': 'BOUNDED_DEFERMENT',
                               'prepare': 'RETAIN', 'requant8': 'RETAIN'},
                    limitations='Three measured seeded decodes and complete 2/1/1 requests; no tail or long-context speed claim. Pipelined RV32MFast 9/12 execute cycles, not stock 3/4. See M5_FAST_RESULTS.md; no push or M6.')
    validate(evidence)
    return evidence


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output', default='docs/m5_fast_evidence.json')
    args = parser.parse_args()
    output = ROOT/args.output
    if output.exists():
        raise ValueError('refusing to overwrite fast-controller evidence')
    evidence = collect()
    output.write_text(json.dumps(evidence, indent=2)+'\n')
    print('M5 FAST EVIDENCE COLLECTED', output)


if __name__ == '__main__':
    main()
