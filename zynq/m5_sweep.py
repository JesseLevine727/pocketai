"""Budgeted characterization wrapper around unchanged, hash-pinned M5 runners."""
import argparse
import json
from pathlib import Path
import platform
import signal
import subprocess
import time


def admitted(elapsed, bound, policy):
    return (bound > 0 and elapsed >= 0 and
            elapsed + bound + policy['cleanup_reserve_seconds'] <= policy['board_budget_seconds'])


def safe_close(arena, return_request):
    """Never close mappings after a failed drain; the driver retains unsafe pages."""
    if arena.info()['owner']:
        arena.ioctl(return_request)
    info = arena.info()
    if info['owner']:
        raise RuntimeError('ownership not safely returned; do not unload helper')
    arena.close()
    return info


def expired(*_):
    raise TimeoutError('aggregate campaign measurement deadline reached; reserve cleanup')


def checkpoint(path, report):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, indent=2)+'\n')
    temporary.replace(path)


def main():
    import m5_run as m
    import m5_opt_profile as profiler
    from pynq import MMIO, Overlay
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--campaign-start', type=float, required=True,
                        help='board monotonic timestamp before staging/module load')
    args = parser.parse_args()
    stage = args.stage.resolve()
    output = stage/'campaign.json'
    if output.exists():
        raise ValueError('fresh stage/report required')
    policy = json.loads((stage/'policy.json').read_text())
    refs = json.loads((stage/'references/manifest.json').read_text())
    fixtures = json.loads((stage/'fixtures/manifest.json').read_text())
    traces = {c['id']: c for c in fixtures['cases']}
    layout = json.loads((stage/'layout.json').read_text())
    report = dict(schema=1, status='FAIL', policy=policy, trials=[],
                  campaign_start_monotonic=args.campaign_start,
                  policy_sha256=m.sha256_file(stage/'policy.json'),
                  reference_manifest_sha256=m.sha256_file(stage/'references/manifest.json'),
                  sha256={}, platform=platform.platform(), clock_hz=m.FABRIC_HZ,
                  memory_before_kib=m.memory_observation())
    arena = None
    loaded = False
    previous = signal.signal(signal.SIGALRM, expired)
    try:
        remaining = policy['board_budget_seconds'] - policy['cleanup_reserve_seconds'] - (time.monotonic()-args.campaign_start)
        if remaining <= 0 or remaining > 3480:
            raise ValueError('invalid/expired campaign start')
        signal.setitimer(signal.ITIMER_REAL, remaining)
        if policy['clock_hz'] != m.FABRIC_HZ or refs['status'] != 'PASS' or refs['policy_sha256'] != report['policy_sha256']:
            raise ValueError('reference/policy mismatch')
        for name, expected in policy['pinned'].items():
            actual = m.sha256_file(stage/name)
            if actual != expected:
                raise ValueError('pinned file changed: '+name)
            report['sha256'][name] = actual
        for name in ('m5_sweep.py', 'layout.json'):
            report['sha256'][name] = m.sha256_file(stage/name)
        if (m.sha256_file(Path(m.__file__)) != policy['pinned']['m5_run.py'] or
                m.sha256_file(Path(profiler.__file__)) != policy['pinned']['m5_opt_profile.py'] or
                layout['arena_bytes'] != m.ARENA_BYTES):
            raise ValueError('imported runner/arena identity mismatch')
        if Path('/sys/module/pa_m5_dma').exists():
            raise RuntimeError('helper already loaded; refuse to take over another campaign')
        subprocess.run(['insmod', '/home/xilinx/pocketai_m5_helper_build/pa_m5_dma.ko'], check=True)
        loaded = True
        arena = m.DmaArena(Path('/dev/pocketai_m5'), layout)
        provision = time.monotonic()
        Overlay(str(stage/'m5_pynq.bit'), download=True)
        arena.ioctl(m.IOC_PREPARE)
        arena.allocate()
        m.load_model(arena.maps['model'], stage/'model.bin', layout['model_sha256'])
        report['sha256']['model.bin'] = layout['model_sha256']
        cluster = MMIO(m.CLUSTER_BASE, m.CLUSTER_BYTES)
        m.load_firmware(cluster, stage/'m5_runtime.bin')
        report['provision_seconds'] = time.monotonic()-provision
        report['allocated_bytes'] = arena.info()['allocated_pages']*m.PAGE_BYTES
        report['memory_provisioned_kib'] = m.memory_observation()
        report['boundary_rejection'] = m.run_rejection(arena, 30)
        checkpoint(output, report)
        print('SWEEP PROVISION / OVERFLOW NON-MUTATION PASS', flush=True)
        for ordinal, trial in enumerate(policy['matrix'], 1):
            item = dict(trial=trial, status='SKIP')
            elapsed = time.monotonic()-args.campaign_start
            available = (trial['case'] in refs['cases'] if trial['kind'] == 'full'
                         else str(trial['past']) in refs['seeds'])
            if not available:
                item['reason'] = 'independent reference unavailable within preparation guard'
            elif not admitted(elapsed, trial['bound_seconds'], policy):
                item['reason'] = 'conservative case bound would consume cleanup reserve'
            else:
                begin = time.monotonic()
                item.update(status='FAIL', started_campaign_seconds=elapsed)
                report['trials'].append(item)
                checkpoint(output, report)
                try:
                    if trial['kind'] == 'full':
                        arena.ioctl(m.IOC_PREPARE)
                        m.load_firmware(cluster, stage/'m5_runtime.bin')
                        case = refs['cases'][trial['case']]
                        result = m.run_case(arena, stage/'fixtures', case,
                                            traces.get(case['id'], {}), trial['new_tokens'],
                                            trial['capture'], ordinal, trial['bound_seconds'])
                    else:
                        seed = refs['seeds'][str(trial['past'])]
                        result = profiler.run_one(arena, cluster, stage/'references'/f'p{trial["past"]}',
                                                  seed, trial['profile'], ordinal, trial['bound_seconds'])
                    item.update(status='PASS', result=result)
                except BaseException as error:
                    item['error'] = repr(error)
                    if hasattr(error, 'm5_partial_result'):
                        item['partial_result'] = error.m5_partial_result
                    raise
                finally:
                    item['case_elapsed_seconds'] = time.monotonic()-begin
                    item['bound_exceeded'] = item['case_elapsed_seconds'] > trial['bound_seconds']
                    report['elapsed_seconds'] = time.monotonic()-args.campaign_start
                    checkpoint(output, report)
                print('SWEEP EXACT PASS', trial['id'], round(item['case_elapsed_seconds'], 3), flush=True)
                continue
            report['trials'].append(item)
            checkpoint(output, report)
            print('SWEEP SKIP', trial['id'], item['reason'], flush=True)
        report['status'] = 'PASS'
    except BaseException as error:
        report['error'] = repr(error)
        raise
    finally:
        # An expired alarm must not interrupt the driver's cancellation/drain.
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        try:
            if arena is not None:
                report['dma_after_return'] = safe_close(arena, m.IOC_RETURN)
                reopened = m.DmaArena(Path('/dev/pocketai_m5'), {})
                try:
                    report['info_after_close_reopen'] = info = reopened.info()
                    if any(info[k] for k in ('owner', 'allocated_pages', 'pte_dma')):
                        raise RuntimeError('DMA allocation/ownership retained; do not unload')
                finally:
                    reopened.close()
            if loaded:
                subprocess.run(['rmmod', 'pa_m5_dma'], check=True)
                if Path('/sys/module/pa_m5_dma').exists() or Path('/dev/pocketai_m5').exists():
                    raise RuntimeError('normal helper unload incomplete')
                report['normal_unload'] = True
        except BaseException as error:
            report.update(status='FAIL', cleanup_error=repr(error))
            raise
        finally:
            report['elapsed_seconds'] = time.monotonic()-args.campaign_start
            report['within_budget'] = 0 < report['elapsed_seconds'] <= policy['board_budget_seconds']
            report['memory_after_kib'] = m.memory_observation()
            if not report['within_budget']:
                report['status'] = 'FAIL'
            checkpoint(output, report)
    print('SWEEP CAMPAIGN', report['status'], report['elapsed_seconds'], flush=True)


if __name__ == '__main__':
    main()
