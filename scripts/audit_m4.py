"""Read-only mandatory evidence audit; never turns partial progress into closure.

Run with --allow-incomplete during qualification. Even a complete machine
audit still requires the documented G7 evidence/limitations review and commit.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import numpy as np
from ref.m4_model_pack import file_sha256
from zynq.m4_benchmark import POLICY_SHA, summarize
from zynq.m4_driver import BIT_SHA, HWH_SHA
from zynq.m4_offload import CANDIDATE_SHA, PACK_SHA

ROOT = Path(__file__).resolve().parents[1]
FROZEN = {
    'build/m4_float_qualification.json': '095ad37bbb38aea4ef5e9baf3fc7e1289648423d16b649aaa547a0aef685d0b5',
    'build/m4_v3_heldout_quality.json': 'ee4bc98220d0a2c3e0ab5a92f4615bf859188c0d93af3467ea2f0587ce3eaf81',
    'build/m4_v3_generation.json': '188c2b6e790ce214ba05e629da94ff74105e388f1859af52b262f4420cb6c1b7',
    'build/m4_v3_development.json': 'f71bf0ca59d3b9e63c30358423ee8882c5bb7935e53a55e2f1db91be9bef831b',
    'build/m4_runtime_fixtures/manifest.json': '7324fb3a88c9b7340e9aa65ea6dd43f77253f0ddf7e7aca9fb100f47f963c537',
    'tests/m4/adaptive_candidate.json': CANDIDATE_SHA,
    'tests/m4/performance_policy.json': POLICY_SHA,
    'build/m4_pack_v3/manifest.json': PACK_SHA,
    'build/m3_qual3/m3_pynq.bit': BIT_SHA,
    'build/m3_qual3/m3_pynq.hwh': HWH_SHA,
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read_json(name):
    return json.loads((ROOT / name).read_text())


def assert_no_process_swap(memory):
    status = memory['/proc/self/status']
    match = re.search(r'^VmSwap:\s+(\d+) kB$', status, re.M)
    require(match is not None and int(match[1]) == 0, 'missing or nonzero process swap')
    require(memory['max_rss_kib'] > 0, 'missing peak-memory measurement')


def check_sources(bundle):
    hashes = bundle['sha256']
    for name in ('zynq/m4_offload.py', 'zynq/m4_driver.py', 'zynq/m4_run.py',
                 'zynq/m4_cpu_gemm.c', 'zynq/m4_cpu_sfpu.c', 'ref/m4_model_pack.py',
                 'ref/m4_cpu.py', 'ref/m4_cpu_sfpu.py', 'ref/sfpu_ref.py', 'ref/sfpu_stream.py'):
        require(hashes[name] == file_sha256(ROOT / name), 'stale physical source: ' + name)
    for name, expected in (('m3_pynq.bit', BIT_SHA), ('m3_pynq.hwh', HWH_SHA),
                           ('pack/manifest.json', PACK_SHA),
                           ('fixtures/manifest.json', FROZEN['build/m4_runtime_fixtures/manifest.json'])):
        require(hashes[name] == expected, 'wrong staged artifact: ' + name)
    for name in ('m4_cpu_gemm.so', 'm4_cpu_sfpu.so'):
        require(hashes[name] == file_sha256(ROOT / 'build/m4_arm_libs' / name), 'wrong ARM binary: ' + name)


def check_runtime(name, backend, boundary=False):
    report = read_json(name)
    require(report['status'] == 'RUNTIME_CORRECTNESS_PASS_NOT_PERFORMANCE_OR_M4_CLOSURE', 'runtime did not finish exactly')
    require(report['backend'] == backend, 'wrong physical backend')
    require(report['native_cpu_backend'] == 'ARMv7 NEON int8 widening multiply/int32 accumulate, N16 tiled', 'not physical ARM native CPU')
    require(report['cache_bytes'] == 48365568 and report['cma_bytes'] == (110592 if backend == 'fpga' else 0), 'unexpected memory allocation')
    check_sources(report['sources'])
    assert_no_process_swap(report['after_memory'])
    if boundary:
        require(report['boundary'] == 'EXACT_1024_PASS_OVERFLOW_REJECTED', 'full context not qualified')
    else:
        require({case['id']: (case['tensors'], case['status']) for case in report['tensor_cases']} ==
                {name: (99, 'EXACT_PASS') for name in ('single', 'story', 'science', 'computing')},
                'missing full tensor cases')
        fixtures = read_json('build/m4_runtime_fixtures/manifest.json')
        expected = {case['id']: [step['token'] for step in case['steps']] for case in fixtures['generation']}
        require(len(report['generation']) == 3, 'missing generation cases')
        for case in report['generation']:
            require(case['tokens'] == expected.pop(case['id']) and case['status'] == 'EXACT_20_TOKEN_LOGIT_KV_PASS',
                    'incomplete/non-exact 20-token generation')
        require(not expected, 'duplicate generation case')
    return name


def check_frozen():
    for name, expected in FROZEN.items():
        require(file_sha256(ROOT / name) == expected, 'frozen identity changed: ' + name)
    # Includes checkpoint, calibration/data, immutable references and host tools.
    from tests.m4.qualify_scaled_quality import verify_frozen
    verify_frozen(str(ROOT / 'tests/m4/adaptive_candidate.json'))
    from scripts.verify_m4_deployment import verify_deployment
    verify_deployment(ROOT)  # actual tokenizer/license/fixture bytes, not manifest identity alone
    quality = read_json('build/m4_v3_heldout_quality.json')
    require(quality['aggregate']['tokens'] == 8192 and all(quality['aggregate_limits'].values()), 'quality gate not passed')
    require(quality['unintended_clipping'] == {}, 'unintended clipping')
    return list(FROZEN)


def check_unchanged_hardware():
    result = subprocess.run(['git', 'diff', '68da8f8', '--name-only', '--', 'rtl', 'sim', 'sw', 'fpga',
                             'zynq/*.tcl', 'zynq/*.v', 'zynq/*.sv', 'zynq/*.core', 'zynq/build_m*.sh',
                             'zynq/eda_to_vivado.py', 'zynq/constraints', 'ref/sfpu_ref.py', 'ref/sfpu_stream.py'],
                            cwd=ROOT, check=True, capture_output=True, text=True)
    require(not result.stdout.strip(), 'hardware/numerics changed: two independent implementation builds/requalification required')
    return 'Exact accepted M3 qual3 bit/HWH; no new timing result inferred.'


def check_local():
    log = (ROOT / 'build/m4_complete_local_regression.log').read_text()
    for marker in ('M3 WIDE LIFECYCLE PASS interruptions=82', 'M3 ALU RTL PASS cases=15120',
                   'M3 SFPU LIFECYCLE PASS reset_abort_checkpoints=682', 'M3 SFPU RTL PASS cases=3472',
                   'M3 CLUSTER CHAINS PASS steps=315', 'M2 GEMM RTL PASS cases=1007',
                   'M1 LOCAL PASS', 'M2 LOCAL PASS', 'M3 LINT PASS',
                   'M1 COMPLIANCE PASS rv32imc=25/25 rv32im=8/8 rv32i=44/48+4-xfail rv32Zicsr=6/6 rv32Zifencei=1/1'):
        require(marker in log, 'missing local regression: ' + marker)
    require(read_json('build/m4_m3_numerics_regression.json')['status'] == 'PASS', 'M3 numerical budget regression')
    for name, count in (('build/m4_deployment_host_tests.log', 40), ('build/m4_m3_host_regression.log', 24)):
        text = (ROOT / name).read_text()
        require(f'Ran {count} tests' in text and text.rstrip().endswith('OK'), 'missing host tests: ' + name)
    boundary = read_json('build/m4_runtime_host_boundary.json')
    require(boundary['boundary'] == 'EXACT_1024_PASS_OVERFLOW_REJECTED', 'host full-context runtime not passed')
    require(boundary['sources']['sha256']['zynq/m4_offload.py'] == file_sha256(ROOT / 'zynq/m4_offload.py'), 'stale host boundary source')
    return 'Clean local M1/M2/M3/ISA; frozen M3 numeric budgets; host runtime full context.'


def check_controls():
    report = read_json('build/m4_driver_board_control.json')
    require(report['status'] == 'PASS' and report['driver_sha256'] == file_sha256(ROOT / 'zynq/m4_driver.py'), 'stale/unpassed driver controls')
    require(set(report['checks']) == {'busy_route_0', 'busy_route_1', 'descriptor_rejection_and_recovery',
                                    'actual_dma_timeout_buffer_retention_restart', 'wide_3072_tail_after_recovery'}, 'missing lifecycle control test')
    single = read_json('build/m4_runtime_fpga_single.json')
    require(single['status'] == 'RUNTIME_CORRECTNESS_PASS_NOT_PERFORMANCE_OR_M4_CLOSURE' and single['operator_checks'] == 1569,
            'actual-operand cross-check not passed')
    check_sources(single['sources'])
    return 'Physical DMA lifecycle and 1569 actual-operand full-model cross-checks.'


def check_compatibility():
    log = (ROOT / 'build/m4_m1_m2_m3_m1_board_tty.log').read_text()
    require(log.count('M1 BOARD PASS') == 2 and 'M2 BOARD PASS' in log and 'M3 BOARD PASS' in log, 'physical compatibility sequence incomplete')
    report = read_json('build/m4_m3_board_regression.json')
    require(report['status'] == 'PASS' and report['fabric_hz'] == 95000000, 'physical M3 regression not passed')
    require(report['manifest']['sha256']['m3_pynq.bit'] == BIT_SHA, 'regression ran wrong overlay')
    require(report['wide_mixed_gemm_qualification']['cases'] == 1007 and report['sfpu_qualification']['cases'] == 3472,
            'incomplete physical corpus')
    return 'M1/M2/M3/M1 on exact 95 MHz overlay.'


def check_benchmark_rows(report, policy):
    """Independent inventory/profile checks; no outlier deletion is permitted."""
    counts, paired = Counter(), {}
    for row in report['trials']:
        require(row['backend'] in ('cpu', 'fpga'), 'unexpected measured backend')
        require(row['status'].startswith('EXACT_') and row['status'].endswith('PASS'), 'unvalidated timing sample')
        require(np.isfinite(row['seconds']) and row['seconds'] > 0, 'invalid latency')
        profile = row['wall_profile']
        require(all(np.isfinite(v) and v >= 0 for v in profile.values()), 'invalid/overlapping wall spans')
        require(abs(sum(profile.values()) - row['seconds']) < max(1e-9, row['seconds'] * 1e-12), 'profile double-counts time')
        key = row['workload'], row['backend'], row['iteration'], row['warmup']
        counts[key] += 1
        work_counts = row['counts']
        if row['backend'] == 'fpga':
            require(work_counts.get('dma_input_bytes', 0) > 0 and work_counts.get('dma_output_bytes', 0) > 0,
                    'missing physical transfer accounting')
        else:
            require(work_counts.get('dma_input_bytes', 0) == 0 and work_counts.get('dma_output_bytes', 0) == 0,
                    'CPU baseline unexpectedly used DMA')
        comparable = {name: work_counts.get(name, 0) for name in ['gemm_macs'] + [f'sfpu_{i}' for i in range(1, 8)]}
        pair = row['workload'], row['iteration'], row['warmup']
        if pair in paired:
            require(paired[pair] == comparable, 'CPU/FPGA measured arithmetic workloads differ')
        else:
            paired[pair] = comparable
    names = ['gemm_down_projection_tile', 'gemm_vocabulary_tail']
    names += ['sfpu_' + name for name in ('gelu', 'layernorm', 'softmax', 'affine', 'requant8', 'affine_gelu', 'add')]
    names += [f'v_bridge_{length}x64_{method}' for length in (13, 32, 1024) for method in ('scalar', 'batched')]
    names += policy['fixed_workloads']
    expected = Counter()
    for name in names:
        for backend in ('cpu', 'fpga'):
            for iteration in range(policy['warmups'] + policy['fixed_workload_trials']):
                expected[name, backend, iteration, iteration < policy['warmups']] = 1
    for backend in ('cpu', 'fpga'):
        for iteration in range(policy['warmups']):
            expected['generation_two_token_warmup', backend, iteration, True] = 1
        for iteration in range(policy['full_generation_trials']):
            expected['generation_20_tokens', backend, iteration, False] = 1
    require(counts == expected, 'missing, extra, duplicate, mislabelled or filtered timing observations')
    require(report['summary_seconds'] == summarize(report['trials']), 'summary differs from raw observations')


def check_performance():
    report = read_json('build/m4_benchmark_board.json')
    policy = read_json('tests/m4/performance_policy.json')
    require(report['status'] == 'BENCHMARK_SELECTED_PHASES_EXACT_PASS' and report['phase'] == 'all', 'benchmark phases incomplete')
    require(report['policy_sha256'] == POLICY_SHA and report['policy'] == policy, 'sampling policy changed')
    require(report['runner_sha256'] == file_sha256(ROOT / 'zynq/m4_benchmark.py'), 'stale benchmark source')
    check_sources(report['bundle'])
    check_benchmark_rows(report, policy)
    require(report['cache_bytes'] == 48365568 and report['cma_bytes'] == 110592, 'wrong benchmark allocations')
    assert_no_process_swap(report['after_memory'])
    for name in ('fixed_backend_memory', 'generation_backend_memory'):
        require(set(report[name]) == {'cpu', 'fpga'}, 'missing backend memory snapshot')
        for snapshot in report[name].values():
            assert_no_process_swap(snapshot)
    return 'All predetermined raw samples, exact result checks and non-overlapping wall accounting pass; no speedup requirement.'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-incomplete', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('refusing to overwrite evidence audit')
    report = {'status': 'INCOMPLETE', 'checks': {}, 'limitation': 'Machine evidence audit is not the G7 documentation/limitations review or milestone commit.'}
    checks = [('G1_G2_frozen_model_quality', check_frozen), ('G4_unchanged_hardware', check_unchanged_hardware),
              ('G4_local_regressions', check_local), ('G3_G4_driver_controls', check_controls),
              ('G5_physical_compatibility', check_compatibility),
              ('G5_cpu_generation', lambda: check_runtime('build/m4_runtime_cpu_batched.json', 'cpu')),
              ('G5_fpga_generation', lambda: check_runtime('build/m4_runtime_fpga_acceptance.json', 'fpga')),
              ('G3_G5_cpu_full_context', lambda: check_runtime('build/m4_runtime_cpu_boundary.json', 'cpu', True)),
              ('G3_G5_fpga_full_context', lambda: check_runtime('build/m4_runtime_fpga_boundary.json', 'fpga', True)),
              ('G6_fair_performance', check_performance)]
    for name, function in checks:
        try:
            report['checks'][name] = {'status': 'PASS', 'detail': function()}
        except FileNotFoundError as error:
            report['checks'][name] = {'status': 'PENDING', 'detail': str(error)}
        except Exception as error:
            report['checks'][name] = {'status': 'FAIL', 'detail': repr(error)}
        print(name, report['checks'][name]['status'], flush=True)
    statuses = [check['status'] for check in report['checks'].values()]
    if all(status == 'PASS' for status in statuses):
        report['status'] = 'MANDATORY_MACHINE_EVIDENCE_PASS_REQUIRES_G7_REVIEW'
    elif 'FAIL' in statuses:
        report['status'] = 'FAIL'
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    if report['status'] == 'FAIL' or (report['status'] == 'INCOMPLETE' and not args.allow_incomplete):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
