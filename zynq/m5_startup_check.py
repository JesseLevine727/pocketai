#!/usr/bin/env python3
"""Physical production-startup/precise-fault check on an already loaded M5 overlay.

Provision only the exact 64-KiB model header plus full work/trace regions. The
first embedding load must fault on the deliberately unmapped model payload,
after model binding and both-hart readiness. Never an inference benchmark.
"""
import argparse
import hashlib
import json
import struct
import time
from pathlib import Path

from pynq import MMIO
import m5_run as m


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    stage = args.stage
    layout = json.loads((stage / 'layout.json').read_text())
    layout['regions'] = [dict(region) for region in layout['regions']
                         if region['name'] in ('model', 'work', 'trace')]
    next(region for region in layout['regions'] if region['name'] == 'model')['bytes'] = 65536
    arena = m.DmaArena(Path('/dev/pocketai_m5'), layout)
    cluster = MMIO(m.CLUSTER_BASE, m.CLUSTER_BYTES)
    report = {'status': 'FAIL', 'kind': 'deliberately_unmapped_first_embedding_load'}
    try:
        arena.ioctl(m.IOC_PREPARE)
        arena.allocate()
        with (stage / 'model.bin').open('rb') as source:
            header = source.read(65536)
        if len(header) != 65536:
            raise RuntimeError('short model header')
        arena.maps['model'][:] = header
        report['model_header_sha256'] = hashlib.sha256(header).hexdigest()
        report['firmware_sha256'] = m.load_firmware(cluster, stage / 'm5_runtime.bin')
        struct.pack_into('<8I', arena.maps['work'], 0,
                         m.CONTROL_MAGIC, 1, 1, 1, 1, 1, 0, 100000000)
        arena.ioctl(m.IOC_START)
        deadline = time.monotonic() + 10
        while not arena.info()['status'] & ((1 << 5) | (1 << 4) | (1 << 3)):
            if time.monotonic() > deadline:
                raise TimeoutError('production startup exceeded 10 seconds')
            time.sleep(.01)
        arena.ioctl(m.IOC_RETURN)
        report['control'] = list(struct.unpack_from('<25I', arena.maps['work']))
        report['hart_results'] = [int(value) for value in cluster.array[0xd000 // 4:0xd080 // 4]]
        control, result = report['control'], report['hart_results']
        if (control[8] != 3 or control[23] != 3 or
                result[:4] != [5, 0x80000000, 5, 0x40010000]):
            raise RuntimeError(f'unexpected startup/fault: {report}')
        report['status'] = 'PASS'
    except BaseException as error:
        report['error'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        try:
            if arena.info()['owner']:
                arena.ioctl(m.IOC_RETURN)
            report['dma_after_return'] = arena.info()
            arena.close()
            report['cleanup'] = 'ownership returned and all mappings closed'
        except BaseException as error:
            report['status'] = 'FAIL'
            report['cleanup_error'] = f'{type(error).__name__}: {error}'
            raise
        finally:
            args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f'M5 PRODUCTION STARTUP/PRECISE FAULT {report["status"]}: {args.output}')


if __name__ == '__main__':
    main()
