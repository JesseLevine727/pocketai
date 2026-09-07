"""Bounded three-cycle comparison on the unchanged qualified boundaries."""
import argparse
import json
from pathlib import Path
import struct

import m5_opt_profile as base
m = base.m


def validate(stage, policy, seed):
    imported = policy['imported_seed']
    if (m.FABRIC_HZ != policy['hardware']['clock_hz'] or seed['status'] != 'PASS' or
            imported['manifest_sha256'] != m.sha256_file(stage / 'seed/manifest.json') or
            seed['policy_sha256'] != imported['original_policy_sha256'] or
            seed['fixture_sha256'] != imported['reference_manifest_sha256'] or
            seed['past'] != policy['fixed_decode']['past'] or
            seed['input_token'] != policy['fixed_decode']['input_token'] or
            seed['expected']['token'] != policy['fixed_decode']['expected_token'] or
            seed['past'] + 1 != policy['fixed_decode']['valid_cache'] or
            set(seed['arrays']) != {'k', 'v', 'k8', 'kunits'}):
        raise ValueError('imported seed identity mismatch')
    for suffix in ('bit', 'hwh'):
        if m.sha256_file(stage / ('m5_pynq.' + suffix)) != policy['hardware'][suffix + '_sha256']:
            raise ValueError('qualified hardware identity mismatch')


def main():
    from pynq import MMIO, Overlay
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('diagnostic', 'measure'), required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('use a fresh output report')
    stage = args.stage.resolve()
    policy = json.loads((stage / 'iteration_policy.json').read_text())
    seed = json.loads((stage / 'seed/manifest.json').read_text())
    validate(stage, policy, seed)
    roles = policy['fixed_decode']['diagnostic_roles' if args.mode == 'diagnostic' else 'final_roles']
    layout = json.loads((stage / 'layout.json').read_text())
    report = dict(schema=1, status='FAIL', mode=args.mode, policy=policy, runs=[],
                  sha256={name: m.sha256_file(stage / name) for name in
                          ('m5_pynq.bit', 'm5_pynq.hwh', 'm5_profile.bin', 'm5_iterate_profile.py',
                           'm5_opt_profile.py', 'm5_run.py', 'iteration_policy.json', 'seed/manifest.json')},
                  memory_before=m.memory_observation())
    arena = m.DmaArena(Path('/dev/pocketai_m5'), layout)
    cluster = None
    try:
        Overlay(str(stage / 'm5_pynq.bit'), download=True)
        arena.ioctl(m.IOC_PREPARE)
        arena.allocate()
        m.load_model(arena.maps['model'], stage / 'model.bin', layout['model_sha256'])
        cluster = MMIO(m.CLUSTER_BASE, m.CLUSTER_BYTES)
        for ordinal, role in enumerate(roles, 1):
            run = base.run_one(arena, cluster, stage, seed, role == 'profiled_diagnostic', ordinal,
                               policy['fixed_decode']['timeout_seconds'])
            run['role'] = role
            report['runs'].append(run)
            print(f'M5 ITERATE {role} EXACT PASS model={run["model_seconds"]:.6f}s', flush=True)
        report['status'] = 'PASS'
    except BaseException as error:
        report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        try:
            if arena.info()['owner']:
                arena.ioctl(m.IOC_RETURN)
            if report['status'] != 'PASS' and cluster is not None:
                report['failure_control'] = list(struct.unpack_from('<25I', arena.maps['work']))
                report['failure_hart_results'] = [int(x) for x in cluster.array[0xd000//4:0xd080//4]]
            report['dma_after_return'] = arena.info()
            arena.close()
            report['cleanup'] = 'safe ownership return and mappings/file closed'
        except BaseException as error:
            report['status'] = 'FAIL'
            report['cleanup_error'] = str(error)
            raise
        finally:
            report['memory_after'] = m.memory_observation()
            args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('M5 ITERATE PROFILE PASS', args.output, flush=True)


if __name__ == '__main__':
    main()
