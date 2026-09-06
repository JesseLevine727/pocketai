#!/usr/bin/env python3
"""Short physical allocation/ownership check; requires the M5 overlay loaded.

Never starts either hart or a DMA transfer. Run as root with the temporary
helper loaded, before the full model campaign. No board-global memory tuning.
"""
import argparse
import errno
import fcntl
import json
import mmap
import struct
import time
from pathlib import Path

from m5_run import DmaArena, IOC_ALLOC, IOC_PREPARE, IOC_START, PAGE_BYTES


def memory():
    keys = ('MemTotal', 'MemFree', 'MemAvailable', 'CmaTotal', 'CmaFree',
            'SwapTotal', 'SwapFree')
    return {key: int(value.split()[0]) for line in Path('/proc/meminfo').read_text().splitlines()
            for key, value in [line.split(':', 1)] if key in keys}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'status': 'FAIL', 'memory_before_kib': memory(), 'checks': []}
    arena = DmaArena(Path('/dev/pocketai_m5'),
                     json.loads((args.stage / 'layout.json').read_text()))

    def rejected(name, operation, expected):
        try:
            operation()
        except OSError as error:
            if error.errno != expected:
                raise
            report['checks'].append({'name': name, 'errno': expected})
        else:
            raise AssertionError(f'{name} unexpectedly accepted')

    def allocate(offset, size):
        fcntl.ioctl(arena.fd, IOC_ALLOC, struct.pack('<4I', offset, size, 0, 0))

    try:
        arena.ioctl(IOC_PREPARE)
        assert arena.info()['allocated_pages'] == 0
        rejected('exclusive_open', lambda: DmaArena(Path('/dev/pocketai_m5'), {}), errno.EBUSY)
        rejected('start_without_pages', lambda: arena.ioctl(IOC_START), errno.EINVAL)
        rejected('unaligned_region', lambda: allocate(1, PAGE_BYTES), errno.EINVAL)
        rejected('empty_region', lambda: allocate(0, 0), errno.EINVAL)
        rejected('arena_overflow', lambda: allocate(0x0ffff000, 8192), errno.EINVAL)
        start = time.monotonic()
        arena.allocate()
        report['allocation_seconds'] = time.monotonic() - start
        report['allocated'] = arena.info()
        report['memory_allocated_kib'] = memory()
        expected_pages = sum(r['bytes'] // PAGE_BYTES for r in arena.layout['regions']
                             if r['permissions'])
        assert report['allocated']['allocated_pages'] == expected_pages
        rejected('overlapping_region', lambda: allocate(0, PAGE_BYTES), errno.EEXIST)
        guard = next(r for r in arena.layout['regions'] if not r['permissions'])
        rejected('unmapped_guard', lambda: mmap.mmap(arena.fd, PAGE_BYTES,
                 offset=guard['offset']), errno.ENXIO)
        for name, mapping in arena.maps.items():
            for offset in (0, len(mapping) - 4):
                struct.pack_into('<I', mapping, offset, 0x31544150 ^ offset)
                assert struct.unpack_from('<I', mapping, offset)[0] == 0x31544150 ^ offset
            report['checks'].append({'name': f'{name}_mapping_ends', 'bytes': len(mapping)})
        report['status'] = 'PASS'
    except BaseException as error:
        report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        try:
            arena.close()
            reopened = DmaArena(Path('/dev/pocketai_m5'), {})
            try:
                report['after_close_reopen'] = reopened.info()
                assert report['after_close_reopen']['allocated_pages'] == 0
                assert report['after_close_reopen']['owner'] == 0
            finally:
                reopened.close()
        except BaseException as error:
            report['status'] = 'FAIL'
            report['cleanup_error'] = f'{type(error).__name__}: {error}'
            raise
        finally:
            report['memory_after_kib'] = memory()
            args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f'M5 ALLOCATION {report["status"]}: {args.output}')


if __name__ == '__main__':
    main()
