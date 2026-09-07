"""Bounded fast-controller comparison using the unchanged qualified boundaries."""
import argparse
import json
from pathlib import Path
import struct

import m5_opt_profile as base
m = base.m

FINE_NAMES = ['dynamic_quantize', 'layernorm_metadata', 'smooth_inclusive',
              'affine_row_inclusive', 'head_affine_row_inclusive', 'affine_metadata',
              'head_affine_metadata', 'project_inclusive', 'head_project_inclusive']


def parse_fine(trace, enabled):
    words = struct.unpack_from('<40I', trace, 0x24000)
    if words[:4] != (0x314e4946, 1, len(FINE_NAMES), int(enabled)):
        raise ValueError('fine profile header mismatch')
    records = []
    for index, name in enumerate(FINE_NAMES):
        kind, calls, low, high = words[4+index*4:8+index*4]
        cycles = low | high << 32
        if kind != index or (enabled and (not calls or not cycles)) or (not enabled and (calls or cycles)):
            raise ValueError('fine profile coverage mismatch')
        records.append(dict(name=name, calls=calls, cycles=cycles, seconds=cycles/m.FABRIC_HZ))
    return records


def main():
    from pynq import MMIO, Overlay
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('fine', 'measure'), required=True)
    args = parser.parse_args()
    if args.output.exists(): raise ValueError('use a fresh output report')
    stage = args.stage.resolve()
    policy = json.loads((stage / 'fast_policy.json').read_text())
    seed = json.loads((stage / 'seed/manifest.json').read_text())
    imported = policy['imported_seed']
    if (m.FABRIC_HZ != policy['hardware']['clock_hz'] or seed['status'] != 'PASS' or
            imported['manifest_sha256'] != m.sha256_file(stage / 'seed/manifest.json') or
            seed['policy_sha256'] != imported['original_policy_sha256'] or
            seed['fixture_sha256'] != imported['reference_manifest_sha256'] or
            seed['past'] != policy['fixed_decode']['past'] or
            seed['input_token'] != policy['fixed_decode']['input_token'] or
            set(seed['arrays']) != {'k', 'v', 'k8', 'kunits'}):
        raise ValueError('imported seed identity mismatch')
    layout = json.loads((stage / 'layout.json').read_text())
    roles = (['profiled_diagnostic', 'unprofiled_diagnostic'] if args.mode == 'fine' else
             ['profiled_diagnostic', 'unprofiled_warmup'] + [f'unprofiled_measured_{i}' for i in range(1, 4)])
    report = dict(schema=1, status='FAIL', mode=args.mode, policy=policy, runs=[],
                  sha256={name: m.sha256_file(stage / name) for name in
                          ('m5_pynq.bit', 'm5_pynq.hwh', 'm5_profile.bin', 'm5_fast_profile.py',
                           'm5_opt_profile.py', 'm5_run.py', 'fast_policy.json')},
                  fine_counter_semantics='Inclusive function intervals; nested callers/callees overlap. Never sum all counters.',
                  memory_before=m.memory_observation())
    arena = m.DmaArena(Path('/dev/pocketai_m5'), layout)
    cluster = None
    try:
        Overlay(str(stage / 'm5_pynq.bit'), download=True)
        arena.ioctl(m.IOC_PREPARE); arena.allocate()
        m.load_model(arena.maps['model'], stage / 'model.bin', layout['model_sha256'])
        cluster = MMIO(m.CLUSTER_BASE, m.CLUSTER_BYTES)
        for ordinal, role in enumerate(roles, 1):
            enabled = role == 'profiled_diagnostic'
            run = base.run_one(arena, cluster, stage, seed, enabled, ordinal,
                               policy['fixed_decode']['timeout_seconds'])
            run['role'] = role
            if args.mode == 'fine': run['fine'] = parse_fine(arena.maps['trace'], enabled)
            report['runs'].append(run)
            print(f'M5 FAST {role} EXACT PASS model={run["model_seconds"]:.6f}s', flush=True)
        report['status'] = 'PASS'
    except BaseException as error:
        report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        try:
            if arena.info()['owner']: arena.ioctl(m.IOC_RETURN)
            if report['status'] != 'PASS' and cluster is not None:
                report['failure_control'] = list(struct.unpack_from('<25I', arena.maps['work']))
                report['failure_hart_results'] = [int(x) for x in cluster.array[0xd000//4:0xd080//4]]
            report['dma_after_return'] = arena.info()
            arena.close()
            report['cleanup'] = 'safe ownership return and mappings/file closed'
        except BaseException as error:
            report['status'] = 'FAIL'; report['cleanup_error'] = str(error)
            raise
        finally:
            report['memory_after'] = m.memory_observation()
            args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('M5 FAST PROFILE PASS', args.output, flush=True)


if __name__ == '__main__': main()
