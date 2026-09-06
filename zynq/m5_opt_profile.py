"""Short, exact fixed-context M5 profiling; requires normally loaded DMA helper."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import time

import numpy as np
try:
    import m5_run as m
except ImportError:
    from zynq import m5_run as m

CONTROL_MAGIC = 0x3554504f
PROFILE_MAGIC = 0x35524650
LOGITS_OFFSET = 0x3000
RECORD_OFFSET = 0x20000
RECORD = struct.Struct('<IIQQQQIIII')
NAMES = {1: 'embedding', 2: 'ln1', 3: 'qkv', 4: 'attention',
         5: 'smooth_attention_projection_residual', 6: 'ln2', 7: 'mlp_up',
         8: 'gelu', 9: 'smooth_mlp_down_residual', 10: 'final_norm',
         11: 'lm_head', 12: 'selection_and_return'}


def parse_profile(header, raw, enabled, clock_hz):
    if (header[:4] != (PROFILE_MAGIC, 1, LOGITS_OFFSET, 50257) or
            header[6:8] != (RECORD_OFFSET, RECORD.size) or
            header[4] > 30 or header[5] > 104 or clock_hz <= 0):
        raise ValueError('invalid profile header')
    start = header[8] | header[9] << 32
    end = header[10] | header[11] << 32
    if end <= start:
        raise ValueError('invalid model clock interval')
    count = header[5]
    if len(raw) != count * RECORD.size:
        raise ValueError('truncated profile records')
    phases = []
    sums = [0] * 7
    for index in range(count):
        kind, layer, elapsed, service, gemm, sfpu, jobs, inputs, outputs, reserved = RECORD.unpack_from(raw, index * RECORD.size)
        if kind not in NAMES or layer >= 12 or reserved or not elapsed or service > elapsed or gemm + sfpu > service:
            raise ValueError('invalid nested profile interval')
        fields = (elapsed, service, gemm, sfpu, jobs, inputs, outputs)
        sums = [a + b for a, b in zip(sums, fields)]
        phases.append({'kind': kind, 'layer': layer, 'name': NAMES[kind],
                       'cycles': elapsed, 'seconds': elapsed / clock_hz,
                       'service_cycles': service, 'cpu_remainder_cycles': elapsed - service,
                       'gemm_cycles': gemm, 'sfpu_cycles': sfpu,
                       'jobs': jobs, 'input_bytes': inputs * 4, 'output_bytes': outputs * 4})
    service = header[16] | header[17] << 32
    gemm = header[18] | header[19] << 32
    sfpu = header[20] | header[21] << 32
    if enabled:
        order = [(1, 0)] + [(kind, layer) for layer in range(12) for kind in range(2, 10)]
        order += [(10, 0), (11, 0), (12, 0)]
        if [(p['kind'], p['layer']) for p in phases] != order:
            raise ValueError('profile phase coverage/order mismatch')
        if (sums[0] > end - start or sums[1:4] != [service, gemm, sfpu] or
                sums[4:] != list(header[12:15]) or (gemm + sfpu) & 0xffffffff != header[22]):
            raise ValueError('profile totals do not reconcile')
    elif count or service or gemm or sfpu:
        raise ValueError('disabled profiling contains counters')
    return {'model_cycles': end - start, 'model_seconds': (end - start) / clock_hz,
            'profile_enabled': enabled, 'phases': phases,
            'service_seconds': service / clock_hz if enabled else None,
            'cpu_remainder_seconds': ((end - start) - service) / clock_hz if enabled else None,
            'gemm_compute_seconds': gemm / clock_hz if enabled else None,
            'sfpu_compute_seconds': sfpu / clock_hz if enabled else None,
            'unassigned_profile_tail_cycles': end - start - sums[0] if enabled else None,
            'jobs': header[12], 'mover_input_bytes': header[13] * 4,
            'mover_output_bytes': header[14] * 4, 'workspace_high_water': header[15]}


def restore_seed(arena, seed_directory, seed):
    for name, entry in seed['arrays'].items():
        if name not in ('k', 'v', 'k8', 'kunits') or entry['bytes'] != len(arena.maps[name]):
            raise ValueError('wrong seed region/capacity')
        path = seed_directory / entry['file']
        m.load_model(arena.maps[name], path, entry['sha256'])
    if m.cache_digest(arena, seed['past']) != seed['prefill_kv_sha256']:
        raise ValueError('seed cache readback mismatch')


def run_one(arena, cluster, stage, seed, enabled, ordinal, timeout):
    arena.ioctl(m.IOC_PREPARE)
    firmware_hash = m.load_firmware(cluster, stage / 'm5_profile.bin')
    restore_seed(arena, stage / 'seed', seed)
    work, trace = arena.maps['work'], arena.maps['trace']
    work[:0x3000] = bytes(0x3000)
    trace[:256] = bytes(256)
    words = [CONTROL_MAGIC, 1, ordinal, 2, 1, 1, int(enabled), 100_000_000]
    words += [0] * (25 - len(words))
    words[10] = seed['past']
    struct.pack_into('<25I', work, 0, *words)
    struct.pack_into('<I', work, m.WORK_PROMPT, seed['input_token'])
    begin = time.monotonic()
    arena.ioctl(m.IOC_START)
    while True:
        info = arena.info()
        if info['status'] & (1 << 5):
            break
        if info['status'] & ((1 << 3) | (1 << 4)):
            raise RuntimeError(f'fabric fault: {info}')
        if time.monotonic() - begin > timeout:
            raise TimeoutError('short cached decode exceeded watchdog')
        time.sleep(.01)
    arena.ioctl(m.IOC_RETURN)
    token = struct.unpack_from('<I', work, m.WORK_GENERATED)[0]
    delivered = time.monotonic()
    words = struct.unpack_from('<25I', work)
    if words[8:12] != (4, 0, seed['past'] + 1, 1) or words[23:25] != (3, 0):
        raise ValueError(f'firmware completion mismatch: {words}')
    header = struct.unpack_from('<64I', trace)
    result = parse_profile(header, bytes(trace[RECORD_OFFSET:RECORD_OFFSET + header[5] * RECORD.size]),
                           enabled, m.FABRIC_HZ)
    logits = np.frombuffer(trace, dtype='<i2', count=50257, offset=LOGITS_OFFSET).copy()
    logical = np.ldexp(logits.astype(np.float64), int(header[4])) / 256
    logits_hash = hashlib.sha256(logical.astype('<f8').tobytes()).hexdigest()
    kv_hash = m.cache_digest(arena, words[10])
    expected = seed['expected']
    if (token != expected['token'] or int(np.argmax(logits)) != token or
            logits_hash != expected['logits_sha256'] or kv_hash != expected['cache_sha256']):
        raise ValueError('seeded decode differs from independent frozen result')
    result.update({'status': 'PASS', 'ordinal': ordinal, 'token': token,
                   'firmware_sha256': firmware_hash, 'logits_sha256': logits_hash,
                   'kv_sha256': kv_hash, 'cache_valid': words[10],
                   'host_request_through_delivery_seconds': delivered - begin})
    return result


def main():
    from pynq import MMIO, Overlay
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('use a fresh output report')
    stage = args.stage.resolve()
    policy = json.loads((stage / 'opt_policy.json').read_text())
    seed = json.loads((stage / 'seed/manifest.json').read_text())
    if (policy['clock_hz'] != m.FABRIC_HZ or seed['status'] != 'PASS' or
            seed['fixture_sha256'] != policy['reference_manifest_sha256'] or
            seed['past'] != policy['fixed_decode']['past'] or
            seed['input_token'] != policy['fixed_decode']['input_token'] or
            seed['policy_sha256'] != m.sha256_file(stage / 'opt_policy.json') or
            set(seed['arrays']) != {'k', 'v', 'k8', 'kunits'}):
        raise ValueError('seed/policy identity mismatch')
    layout = json.loads((stage / 'layout.json').read_text())
    report = {'schema': 1, 'status': 'FAIL', 'policy': policy, 'runs': [],
              'seed_manifest_sha256': m.sha256_file(stage / 'seed/manifest.json'),
              'sha256': {name: m.sha256_file(stage / name) for name in
                         ('m5_pynq.bit', 'm5_pynq.hwh', 'm5_profile.bin', 'm5_opt_profile.py', 'm5_run.py')},
              'memory_before': m.memory_observation()}
    arena = m.DmaArena(Path('/dev/pocketai_m5'), layout)
    cluster = None
    try:
        Overlay(str(stage / 'm5_pynq.bit'), download=True)
        arena.ioctl(m.IOC_PREPARE)
        arena.allocate()
        m.load_model(arena.maps['model'], stage / 'model.bin', layout['model_sha256'])
        cluster = MMIO(m.CLUSTER_BASE, m.CLUSTER_BYTES)
        for ordinal, name in enumerate(policy['fixed_decode']['initial_order']):
            enabled = name == 'profiled_diagnostic'
            run = run_one(arena, cluster, stage, seed, enabled, ordinal + 1,
                          policy['fixed_decode']['timeout_seconds'])
            run['role'] = name
            report['runs'].append(run)
            print(f'M5 OPT {name} EXACT PASS model={run["model_seconds"]:.6f}s', flush=True)
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
                report['failure_hart_results'] = [int(x) for x in cluster.array[0xd000 // 4:0xd080 // 4]]
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
    print('M5 OPT PROFILE CAMPAIGN PASS', args.output, flush=True)


if __name__ == '__main__':
    main()
