"""Reproducible analysis of a COMPLETED paired M4 benchmark, never partial data.

Preserves the distinction between token-ID delivery, model prefill, cached
decode, complete generation and primitive timing. Does not modify source data.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
from ref.m4_model_pack import file_sha256
from scripts.audit_m4 import check_benchmark_rows, check_sources, require
from zynq.m4_benchmark import POLICY_SHA, statistics


def memory_fields(snapshot):
    result = {'max_rss_kib': snapshot['max_rss_kib']}
    for source, fields in (('/proc/self/status', ('VmRSS', 'VmHWM', 'VmSwap', 'Threads')),
                           ('/proc/self/smaps_rollup', ('Rss', 'Pss', 'Swap', 'SwapPss'))):
        for field in fields:
            match = re.search(r'^' + re.escape(field) + r':\s+(\d+)(?: kB)?$', snapshot[source], re.M)
            require(match is not None, 'missing memory field: ' + field)
            result[field if field == 'Threads' else field + '_kib'] = int(match[1])
    return result


def analyze_group(rows):
    rows = sorted(rows, key=lambda row: row['iteration'])
    wall = sum(row['seconds'] for row in rows)
    keys = sorted({key for row in rows for key in row['wall_profile']})
    profile = {key: sum(row['wall_profile'].get(key, 0) for row in rows) for key in keys}
    require(abs(sum(profile.values()) - wall) < wall * 1e-12, 'wall profile is not a disjoint partition')
    result = {'latency_seconds': statistics([row['seconds'] for row in rows]),
              'profile_mean_seconds': {key: value / len(rows) for key, value in profile.items()},
              'profile_fraction_of_total_wall': {key: value / wall for key, value in profile.items()},
              'counts_per_trial': {key: statistics([row['counts'].get(key, 0) for row in rows])
                                   for key in sorted({key for row in rows for key in row['counts']})}}
    if 'model_before_greedy_seconds' in rows[0]:
        result['model_before_greedy_seconds'] = statistics([row['model_before_greedy_seconds'] for row in rows])
        result['delivered_tokens_per_second'] = statistics([1 / row['seconds'] for row in rows])
        if rows[0]['workload'] == 'prefill_first_token':
            result['prefill_input_tokens_per_second'] = statistics([13 / row['model_before_greedy_seconds'] for row in rows])
    if rows[0]['workload'] == 'generation_20_tokens':
        for row in rows:
            times = row['token_delivery_seconds']
            require(len(row['tokens']) == len(times) == 20 and all(t > 0 for t in times), 'invalid generation sample')
            require(sum(times) <= row['seconds'] * (1 + 1e-12), 'generation step spans exceed total wall')
            require(row['first_token_seconds'] == times[0] and row['cached_decode_seconds'] == sum(times[1:]), 'generation accounting differs')
        result.update(
            independent_chain_trials=len(rows),
            first_token_seconds=statistics([row['first_token_seconds'] for row in rows]),
            delivered_tokens_per_second=statistics([20 / row['seconds'] for row in rows]),
            cached_decode_tokens_per_second_per_chain=statistics([19 / row['cached_decode_seconds'] for row in rows]),
            cached_decode_latency_seconds_pooled=statistics([t for row in rows for t in row['token_delivery_seconds'][1:]]),
            pooled_decode_note='57 dependent step observations nested in 3 chains, at successive contexts 14..32; not 57 independent chain trials.',
            raw_chain_summary=[{'iteration': row['iteration'], 'total_seconds': row['seconds'],
                                'first_token_seconds': row['first_token_seconds'],
                                'cached_decode_seconds': row['cached_decode_seconds'],
                                'twenty_delivered_tokens_per_second': 20 / row['seconds']} for row in rows])
    return result


def paired_ratios(cpu, fpga):
    by_cpu = {row['iteration']: row['seconds'] for row in cpu}
    by_fpga = {row['iteration']: row['seconds'] for row in fpga}
    require(by_cpu.keys() == by_fpga.keys(), 'cannot pair different iteration sets')
    return statistics([by_cpu[i] / by_fpga[i] for i in sorted(by_cpu)])


def analyze(report):
    check_benchmark_rows(report, report['policy'])
    groups = defaultdict(list)
    warmups = []
    for row in report['trials']:
        if row['warmup']:
            warmups.append({'workload': row['workload'], 'backend': row['backend'],
                            'iteration': row['iteration'], 'seconds': row['seconds']})
        else:
            groups[row['workload'], row['backend']].append(row)
    workloads = {}
    for name in sorted({key[0] for key in groups}):
        cpu, fpga = groups[name, 'cpu'], groups[name, 'fpga']
        c, f = analyze_group(cpu), analyze_group(fpga)
        workloads[name] = {'cpu': c, 'fpga': f,
                           'cpu_over_fpga_ratio_of_latency_medians': c['latency_seconds']['median'] / f['latency_seconds']['median'],
                           'paired_cpu_over_fpga_latency_ratios': paired_ratios(cpu, fpga)}
    bridges = {}
    for length in (13, 32, 1024):
        bridges[str(length)] = {}
        for backend in ('cpu', 'fpga'):
            before = workloads[f'v_bridge_{length}x64_scalar'][backend]['latency_seconds']['median']
            after = workloads[f'v_bridge_{length}x64_batched'][backend]['latency_seconds']['median']
            bridges[str(length)][backend] = {'scalar_median_seconds': before, 'batched_median_seconds': after,
                                             'scalar_over_batched_ratio_of_medians': before / after}
    return {'status': 'ANALYSIS_OF_COMPLETED_VALIDATED_BENCHMARK_NOT_M4_CLOSURE',
            'ratio_direction': 'CPU/FPGA latency >1 means FPGA faster; <1 means FPGA slower. Scalar/batched latency >1 means batching faster.',
            'policy_sha256': POLICY_SHA, 'boundary': report['policy']['boundary'],
            'warmup_observations': warmups, 'workloads': workloads, 'controlled_bridge_comparison': bridges,
            'sampling_note': 'All raw samples retained; no outlier trimming. Fixed workloads n=20 per backend; full generation n=3 chains per backend.',
            'profile_note': 'Wall fractions use summed non-overlapping wall spans divided by summed total wall. Hardware compute-cycle counters overlap DMA and are not added.',
            'initialization_seconds': {key: report[key] for key in ('integrity_scan_seconds', 'cpu_runtime_init_seconds',
                                       'overlay_dma_init_seconds', 'untimed_cpu_prefix_setup_seconds')},
            'memory': {'cache_bytes': report['cache_bytes'], 'cma_bytes': report['cma_bytes'],
                       'untimed_cached_prefix_bytes': report['untimed_cached_prefix_bytes'],
                       'overall_after': memory_fields(report['after_memory']),
                       'fixed': {name: memory_fields(value) for name, value in report['fixed_backend_memory'].items()},
                       'generation': {name: memory_fields(value) for name, value in report['generation_backend_memory'].items()}},
            'instrumentation_note': 'One runtime/pack/cache is shared, switching backends; FPGA libraries and CMA remain resident for CPU samples too. Full generation retains 20 returned float64 logit arrays (8,041,120 payload bytes) for post-clock checking. List/timestamp/profiling overhead is inside the common timing boundary; retained validation-output memory is included in measured process memory. Prefix snapshot is outside cached-decode timing and explicitly counted.',
            'cold_note': 'Initialization includes integrity scans that warm OS page cache. These are not disk-cold measurements. No global OS/governor/cache settings changed.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, default=Path('build/m4_benchmark_board.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('refusing to overwrite performance analysis')
    report = json.loads(args.input.read_text())
    require(report['status'] == 'BENCHMARK_SELECTED_PHASES_EXACT_PASS' and report['phase'] == 'all', 'benchmark is not complete')
    require(report['policy_sha256'] == POLICY_SHA, 'not the frozen performance policy')
    root = Path(__file__).resolve().parents[1]
    require(report['policy'] == json.loads((root / 'tests/m4/performance_policy.json').read_text()), 'policy contents changed')
    require(report['runner_sha256'] == file_sha256(root / 'zynq/m4_benchmark.py'), 'benchmark source changed')
    check_sources(report['bundle'])
    result = analyze(report)
    result.update(input_sha256=file_sha256(args.input), analyzer_sha256=file_sha256(__file__))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print('M4 COMPLETED PERFORMANCE ANALYSIS READY', args.output, flush=True)


if __name__ == '__main__':
    main()
