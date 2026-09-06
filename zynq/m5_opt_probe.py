"""Subsecond-to-seconds scalar probes on the accepted overlay, no model run."""
import argparse
import json
from pathlib import Path
import struct
import time

try:
    import m5_run as m
except ImportError:
    from zynq import m5_run as m


def main():
    from pynq import MMIO, Overlay
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('use fresh probe report')
    layout = json.loads((args.stage / 'layout.json').read_text())
    layout['regions'] = [r for r in layout['regions'] if r['name'] in ('work', 'trace')]
    report = {'status': 'FAIL', 'sha256': {p: m.sha256_file(args.stage / p) for p in (
        'probe.bin', 'm5_opt_probe.py', 'm5_run.py', 'm5_pynq.bit', 'm5_pynq.hwh')}}
    arena = m.DmaArena(Path('/dev/pocketai_m5'), layout)
    cluster = None
    try:
        Overlay(str(args.stage / 'm5_pynq.bit'), download=True)
        arena.ioctl(m.IOC_PREPARE); arena.allocate()
        cluster = MMIO(m.CLUSTER_BASE, m.CLUSTER_BYTES)
        m.load_firmware(cluster, args.stage / 'probe.bin')
        arena.maps['trace'][:256] = bytes(256)
        started = time.monotonic(); arena.ioctl(m.IOC_START)
        while not arena.info()['status'] & (1 << 5):
            if arena.info()['status'] & ((1 << 3) | (1 << 4)):
                raise RuntimeError('probe fabric fault')
            if time.monotonic() - started > 120:
                raise TimeoutError('probe watchdog')
            time.sleep(.01)
        arena.ioctl(m.IOC_RETURN)
        if struct.unpack_from('<3I', arena.maps['trace']) != (0x35425250, 1, 8):
            raise ValueError('probe header mismatch')
        names = ['scalar_read_sram', 'scalar_read_ddr', 'rne_divide_baseline', 'rne_shift_exact',
                 'affine_baseline_sram', 'affine_exact_sram', 'affine_baseline_ddr', 'affine_exact_ddr']
        records = []
        for index, name in enumerate(names):
            i, low, high, clow, chigh, operations = struct.unpack_from('<6I', arena.maps['trace'], 32 + index*24)
            cycles = low | high << 32
            if i != index or not cycles or not operations:
                raise ValueError('invalid probe record')
            records.append({'name': name, 'cycles': cycles, 'seconds': cycles/m.FABRIC_HZ,
                            'operations': operations, 'cycles_per_operation': cycles/operations,
                            'checksum': clow | chigh << 32})
        if (records[0]['checksum'] != 64*512*513//2 or
                records[1]['checksum'] != records[0]['checksum'] or
                records[2]['checksum'] != records[3]['checksum'] or
                len({r['checksum'] for r in records[4:]}) != 1 or
                records[4]['checksum'] == 2**64-1):
            raise ValueError('probe differential checksum mismatch')
        report.update(status='PASS', records=records, host_seconds=time.monotonic()-started)
    finally:
        if arena.info()['owner']:
            arena.ioctl(m.IOC_RETURN)
        report['returned'] = arena.info()
        if cluster is not None:
            report['hart_results'] = [int(x) for x in cluster.array[0xd000//4:0xd080//4]]
        arena.close()
        report['cleanup'] = 'safe return, mappings and file closed'
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('M5 OPT SCALAR PROBES PASS', json.dumps(records), flush=True)


if __name__ == '__main__':
    main()
