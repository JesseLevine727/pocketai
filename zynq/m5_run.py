#!/usr/bin/env python3
"""Lean physical acceptance runner for autonomous M5 GPT-2 firmware."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import mmap
import os
import platform
import struct
import time
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
if TYPE_CHECKING:
    from pynq import MMIO

ARENA_BYTES = 0x10000000
PAGE_BYTES = 4096
CLUSTER_BASE = 0x43C00000
CLUSTER_BYTES = 0x00020000
WORK_PROMPT = 0x1000
WORK_GENERATED = 0x2000
TRACE_LOGITS = 0x3000
TRACE_RECORDS = 0x1C000
CONTROL_MAGIC = 0x35545250
TRACE_MAGIC = 0x35435254
FABRIC_HZ = 91_000_000

IOC_WRITE = 1
IOC_READ = 2


def _ioc(direction: int, number: int, size: int) -> int:
    return (direction << 30) | (ord('P') << 8) | number | (size << 16)


IOC_ALLOC = _ioc(IOC_WRITE, 0x01, 16)
IOC_INFO = _ioc(IOC_READ, 0x02, 32)
IOC_PREPARE = _ioc(0, 0x03, 0)
IOC_START = _ioc(0, 0x04, 0)
IOC_RETURN = _ioc(0, 0x05, 0)

TRACE_NAMES = {1: 'embedding', 3: 'qkv', 4: 'context', 9: 'output'}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(4 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


class DmaArena:
    def __init__(self, device: Path, layout: dict):
        self.fd = os.open(device, os.O_RDWR | os.O_CLOEXEC)
        self.layout = layout
        self.maps: dict[str, mmap.mmap] = {}

    def ioctl(self, request: int) -> None:
        fcntl.ioctl(self.fd, request)

    def info(self) -> dict:
        raw = bytearray(32)
        fcntl.ioctl(self.fd, IOC_INFO, raw, True)
        values = struct.unpack('<8I', raw)
        return dict(zip(('abi', 'arena_bytes', 'pte_dma', 'allocated_pages',
                         'owner', 'status', 'control', 'reserved'), values))

    def allocate(self) -> None:
        for region in self.layout['regions']:
            if not region['permissions']:
                continue
            flags = 1 if region['permissions'] & 2 else 0
            request = struct.pack('<4I', region['offset'], region['bytes'], flags, 0)
            fcntl.ioctl(self.fd, IOC_ALLOC, request)
            self.maps[region['name']] = mmap.mmap(
                self.fd, region['bytes'], flags=mmap.MAP_SHARED,
                prot=mmap.PROT_READ | mmap.PROT_WRITE, offset=region['offset'])

    def close(self) -> None:
        for mapping in self.maps.values():
            mapping.close()
        self.maps.clear()
        os.close(self.fd)


def load_model(destination: mmap.mmap, source_path: Path, expected: str) -> str:
    digest = hashlib.sha256()
    cursor = 0
    with source_path.open('rb', buffering=0) as source:
        while True:
            chunk = source.read(4 << 20)
            if not chunk:
                break
            destination[cursor:cursor + len(chunk)] = chunk
            digest.update(chunk)
            cursor += len(chunk)
    if cursor != len(destination):
        raise RuntimeError(f'model size {cursor} != mapped size {len(destination)}')
    actual = digest.hexdigest()
    if actual != expected:
        raise RuntimeError(f'model digest {actual} != {expected}')
    return actual


def load_firmware(cluster: MMIO, firmware_path: Path) -> str:
    image = firmware_path.read_bytes()
    if len(image) != 65536 or len(image) % 4:
        raise RuntimeError('firmware must be one exact 64-KiB scratchpad image')
    words = np.frombuffer(image, dtype='<u4')
    cluster.array[:len(words)] = words
    readback = np.asarray(cluster.array[:len(words)], dtype='<u4').tobytes()
    if readback != image:
        raise RuntimeError('firmware readback mismatch')
    return hashlib.sha256(image).hexdigest()


def cache_digest(arena: DmaArena, length: int) -> str:
    k = np.ndarray((12, 12, 1024, 64), dtype='<i2', buffer=arena.maps['k'])
    v = np.ndarray((12, 12, 1024, 64), dtype='<i2', buffer=arena.maps['v'])
    digest = hashlib.sha256()
    for layer in range(12):
        keys = np.ascontiguousarray(k[layer, :, :length])
        values = np.ascontiguousarray(v[layer, :, :length])
        digest.update(f'{layer}:{keys.shape}:<i2'.encode())
        digest.update(keys.tobytes())
        digest.update(values.tobytes())
    return digest.hexdigest()


def check_traces(trace_map: mmap.mmap, fixtures: Path, case: dict) -> list[dict]:
    header = struct.unpack_from('<64I', trace_map, 0)
    if header[0] != TRACE_MAGIC or header[1] != 1 or header[6] != TRACE_RECORDS:
        raise RuntimeError('invalid trace header')
    cursor = header[6]
    checked = []
    for _ in range(header[7]):
        kind, layer, rows, columns, exponent_bytes, value_bytes, r0, r1 = \
            struct.unpack_from('<8I', trace_map, cursor)
        if r0 or r1 or exponent_bytes != rows * 4 or value_bytes != rows * columns * 2:
            raise RuntimeError('invalid trace record')
        base = TRACE_NAMES.get(kind)
        if base is None:
            raise RuntimeError(f'unexpected trace kind {kind}')
        name = base if kind == 1 else f'h.{layer}.{base}'
        offset = cursor + 32
        exponents = np.frombuffer(trace_map, dtype='<u4', count=rows, offset=offset).copy()
        values = np.frombuffer(trace_map, dtype='<i2', count=rows * columns,
                               offset=offset + exponent_bytes).copy().reshape(rows, columns)
        logical = np.ldexp(values.astype(np.float64), exponents.astype(np.int64)[:, None]) / 256.0
        expected_entry = case['tensors'][name]
        if sha256_file(fixtures / expected_entry['file']) != expected_entry['sha256']:
            raise RuntimeError(f'reference file digest mismatch: {name}')
        expected = np.load(fixtures / expected_entry['file'], allow_pickle=False)
        if not np.array_equal(logical, expected):
            raise RuntimeError(f'trace mismatch: {name}')
        checked.append({'name': name, 'shape': [rows, columns],
                        'sha256': hashlib.sha256(logical.astype('<f8').tobytes()).hexdigest()})
        cursor = (offset + exponent_bytes + value_bytes + 63) & ~63
    expected_names = ['embedding', 'h.0.qkv', 'h.0.context',
                      'h.0.output', 'h.11.output']
    if [entry['name'] for entry in checked] != expected_names:
        raise RuntimeError(f'trace coverage mismatch: {[entry["name"] for entry in checked]}')
    return checked


def run_rejection(arena: DmaArena, timeout: float) -> dict:
    """Exercise the 1024-position boundary, then leave a reusable clean system."""
    work = arena.maps['work']
    work[:] = b'\0' * len(work)
    control = [CONTROL_MAGIC, 1, 0, 1, 1, 1024, 0, 100_000_000]
    control += [0] * (25 - len(control))
    control[10], control[11] = 17, 19
    struct.pack_into('<25I', work, 0, *control)
    struct.pack_into('<I', work, WORK_PROMPT, 0)
    struct.pack_into('<I', work, WORK_GENERATED, 0xDEADBEEF)
    cache_names = ('k', 'v', 'k8', 'kunits')
    before = {name: hashlib.sha256(arena.maps[name]).hexdigest() for name in cache_names}

    start = time.monotonic()
    arena.ioctl(IOC_START)
    deadline = start + timeout
    while not arena.info()['status'] & (1 << 5):
        if time.monotonic() >= deadline:
            raise TimeoutError('boundary-rejection run timed out')
        time.sleep(0.01)
    arena.ioctl(IOC_RETURN)
    words = struct.unpack_from('<25I', work, 0)
    after = {name: hashlib.sha256(arena.maps[name]).hexdigest() for name in cache_names}
    if (words[8] != 5 or words[9] != 1 or words[10:12] != (17, 19) or
            struct.unpack_from('<I', work, WORK_GENERATED)[0] != 0xDEADBEEF or before != after):
        raise RuntimeError(
            f'boundary rejection state={words[8]} error={words[9]} '
            f'cache={words[10]} generated={words[11]}')
    return {
        'case': 'prompt_count=1,generation_count=1024',
        'expected': 'prompt_count + generation_count > 1024',
        'state': words[8], 'error': words[9],
        'cache_valid': words[10], 'generated_count': words[11],
        'cache_regions_unchanged': before,
        'output_sentinel_unchanged': True,
        'wall_seconds': time.monotonic() - start,
        'recovery': 'subsequent accepted runs',
    }


def run_case(arena: DmaArena, fixtures: Path, case: dict, trace_case: dict,
             generation_count: int, capture: bool, request_id: int,
             timeout: float) -> dict:
    steps = case['steps']
    if generation_count < 1 or generation_count > len(steps):
        raise RuntimeError('generation count is outside frozen reference')
    work = arena.maps['work']
    trace = arena.maps['trace']
    work[:] = b'\0' * len(work)
    trace[:] = b'\0' * len(trace)
    control = [CONTROL_MAGIC, 1, request_id, 1, len(case['input_tokens']),
               generation_count, 1 if capture else 0, 100_000_000]
    control += [0] * (25 - len(control))
    struct.pack_into('<25I', work, 0, *control)
    struct.pack_into(f'<{len(case["input_tokens"])}I', work, WORK_PROMPT,
                     *case['input_tokens'])

    start_wall = time.monotonic()
    arena.ioctl(IOC_START)
    deadline = start_wall + timeout
    while True:
        info = arena.info()
        if info['status'] & (1 << 5):
            break
        if info['status'] & ((1 << 3) | (1 << 4)):
            raise RuntimeError(f'fabric failure status=0x{info["status"]:02x}')
        if time.monotonic() >= deadline:
            raise TimeoutError(f'autonomous run exceeded {timeout:.1f}s')
        time.sleep(0.01)
    done_wall = time.monotonic()
    arena.ioctl(IOC_RETURN)
    returned_wall = time.monotonic()

    words = struct.unpack_from('<25I', work, 0)
    if words[8] != 4 or words[9] or words[11] != generation_count:
        raise RuntimeError(f'firmware result state={words[8]} error=0x{words[9]:08x} generated={words[11]}')
    generated = list(struct.unpack_from(f'<{generation_count}I', work, WORK_GENERATED))
    delivered_wall = time.monotonic()
    expected_tokens = [step['token'] for step in steps[:generation_count]]
    if generated != expected_tokens:
        raise RuntimeError(f'token mismatch {generated} != {expected_tokens}')

    trace_header = struct.unpack_from('<64I', trace, 0)
    exponent = trace_header[4]
    if (trace_header[0:4] != (TRACE_MAGIC, 1, TRACE_LOGITS, 50257) or
            trace_header[5] != generation_count or
            words[10] != len(case['input_tokens']) + generation_count - 1 or
            words[23] != 3 or words[24] or words[14] != words[15]):
        raise RuntimeError('inconsistent firmware completion metadata')
    logits = np.frombuffer(trace, dtype='<i2', count=50257, offset=TRACE_LOGITS).copy()
    logical_logits = np.ldexp(logits.astype(np.float64), int(exponent)) / 256.0
    logits_hash = hashlib.sha256(logical_logits.astype('<f8').tobytes()).hexdigest()
    expected_final = steps[generation_count - 1]
    if logits_hash != expected_final['logits_sha256']:
        raise RuntimeError(f'logits digest {logits_hash} != {expected_final["logits_sha256"]}')
    kv_hash = cache_digest(arena, words[10])
    if kv_hash != expected_final['cache_sha256']:
        raise RuntimeError(f'KV digest {kv_hash} != {expected_final["cache_sha256"]}')

    cycle_start = trace_header[8] | trace_header[9] << 32
    cycle_end = trace_header[10] | trace_header[11] << 32
    first_token = trace_header[18] | trace_header[19] << 32
    prefill_cycles = trace_header[20] | trace_header[21] << 32
    if not cycle_start < first_token <= cycle_end:
        raise RuntimeError('invalid firmware cycle timestamps')
    count = trace_header[5]
    intervals = []
    for index in range(count):
        low, high = struct.unpack_from('<2I', trace, 256 + index * 8)
        intervals.append((low | high << 32) / FABRIC_HZ)
    result = {
        'id': case['id'], 'prompt_tokens': case['input_tokens'],
        'generated_tokens': generated, 'cache_valid': words[10],
        'logits_sha256': logits_hash, 'kv_sha256': kv_hash,
        'firmware_seconds': (cycle_end - cycle_start) / FABRIC_HZ,
        'ttft_seconds': (first_token - cycle_start) / FABRIC_HZ,
        'prefill_forward_seconds': prefill_cycles / FABRIC_HZ,
        'decode_seconds': intervals[1:],
        'firmware_tokens_per_second': generation_count / ((cycle_end - cycle_start) / FABRIC_HZ),
        'device_wall_seconds': done_wall - start_wall,
        'request_wall_seconds': returned_wall - start_wall,
        'request_through_delivery_seconds': delivered_wall - start_wall,
        'request_tokens_per_second': generation_count / (delivered_wall - start_wall),
        'transfers': words[14], 'tensor_bytes_read': words[20],
        'tensor_bytes_written': words[21], 'work_high_water': words[18],
        'engine_cycles_modulo_2_32': trace_header[15],
        'engine_work_mixed_mac_and_sfpu_elements': trace_header[16] | trace_header[17] << 32,
    }
    if capture:
        result['traces'] = check_traces(trace, fixtures, trace_case)
    return result


def main() -> None:
    from pynq import MMIO, Overlay

    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', type=Path, default=Path('.'))
    parser.add_argument('--device', type=Path, default=Path('/dev/pocketai_m5'))
    parser.add_argument('--output', type=Path, default=Path('m5_physical.json'))
    parser.add_argument('--timeout', type=float, default=600.0)
    args = parser.parse_args()
    stage = args.stage.resolve()
    layout = json.loads((stage / 'layout.json').read_text())
    manifest = json.loads((stage / 'fixtures' / 'manifest.json').read_text())
    generations = {entry['id']: entry for entry in manifest['generation']}
    fixture_cases = {entry['id']: entry for entry in manifest['cases']}
    model_expected = layout['model_sha256']
    policy_path = stage / 'performance_policy.json'
    policy = json.loads(policy_path.read_text())
    if policy['schema'] != 1 or policy['clock_hz'] != FABRIC_HZ:
        raise RuntimeError('performance policy schema/clock mismatch')
    if layout['arena_bytes'] != ARENA_BYTES:
        raise RuntimeError('unexpected arena size')

    report = {
        'schema': 1, 'status': 'FAIL', 'clock_hz': FABRIC_HZ,
        'platform': platform.platform(), 'kernel': platform.release(),
        'policy': policy,
        'sha256': {}, 'runs': [],
    }
    report['sha256']['bitstream'] = sha256_file(stage / 'm5_pynq.bit')
    report['sha256']['firmware_file'] = sha256_file(stage / 'm5_runtime.bin')
    report['sha256']['model'] = sha256_file(stage / 'model.bin')
    report['sha256']['layout'] = sha256_file(stage / 'layout.json')
    report['sha256']['policy'] = sha256_file(policy_path)
    report['sha256']['fixtures'] = sha256_file(stage / 'fixtures' / 'manifest.json')
    report['sha256']['hwh'] = sha256_file(stage / 'm5_pynq.hwh')

    arena = DmaArena(args.device, layout)
    overlay_ready = False
    try:
        provision_start = time.monotonic()
        Overlay(str(stage / 'm5_pynq.bit'), download=True)
        overlay_ready = True
        arena.ioctl(IOC_PREPARE)
        arena.allocate()
        load_model(arena.maps['model'], stage / 'model.bin', model_expected)
        cluster = MMIO(CLUSTER_BASE, CLUSTER_BYTES)
        firmware_path = stage / 'm5_runtime.bin'
        report['sha256']['firmware_readback'] = load_firmware(cluster, firmware_path)
        report['provision_seconds'] = time.monotonic() - provision_start
        report['allocated_bytes'] = arena.info().get('allocated_pages', 0) * PAGE_BYTES
        report['boundary_rejection'] = run_rejection(arena, args.timeout)
        for request_id, trial in enumerate(policy['matrix'], 1):
            name, count = trial['prompt'], trial['new_tokens']
            run = generations[name]
            # Trace fixtures share the same frozen prompt IDs.
            if fixture_cases[name]['input_tokens'] != run['input_tokens']:
                raise RuntimeError(f'{name} prompt mismatch between fixture sections')
            # BRAM survives reset: restore BSS, stacks and the shared hart job
            # before every boot so hart 1 cannot observe the previous magic.
            arena.ioctl(IOC_PREPARE)
            if load_firmware(cluster, firmware_path) != report['sha256']['firmware_readback']:
                raise RuntimeError('firmware changed between requests')
            report['runs'].append(run_case(arena, stage / 'fixtures', run, fixture_cases[name],
                                           count, trial['capture_prefill'], request_id,
                                           args.timeout))
        report['status'] = 'PASS'
        report['dma'] = arena.info()
    except BaseException as error:
        report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        try:
            try:
                if overlay_ready and arena.info()['owner'] != 0:
                    arena.ioctl(IOC_RETURN)
            finally:
                arena.close()
            report['cleanup'] = 'ownership returned and mappings/file closed'
        except BaseException as error:
            report['status'] = 'FAIL'
            report['cleanup_error'] = f'{type(error).__name__}: {error}'
            raise
        finally:
            args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f'M5 PHYSICAL {report["status"]}: {args.output}')


if __name__ == '__main__':
    main()
