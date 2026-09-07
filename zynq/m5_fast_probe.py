"""Complete CPU/SFPU quantization ablation; no model or long experiment."""
import argparse
import json
from pathlib import Path
import struct
import time
import m5_run as m


def main():
    from pynq import MMIO, Overlay
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): raise ValueError('use a fresh report')
    layout = json.loads((args.stage / 'layout.json').read_text())
    layout['regions'] = [r for r in layout['regions'] if r['name'] in ('work', 'trace')]
    report = dict(status='FAIL', sha256={name: m.sha256_file(args.stage / name) for name in
                  ('probe.bin', 'm5_fast_probe.py', 'm5_run.py', 'm5_pynq.bit', 'm5_pynq.hwh')})
    arena = m.DmaArena(Path('/dev/pocketai_m5'), layout)
    cluster = None
    try:
        Overlay(str(args.stage / 'm5_pynq.bit'), download=True)
        arena.ioctl(m.IOC_PREPARE); arena.allocate()
        cluster = MMIO(m.CLUSTER_BASE, m.CLUSTER_BYTES)
        m.load_firmware(cluster, args.stage / 'probe.bin')
        arena.maps['trace'][:512] = bytes(512)
        begin = time.monotonic(); arena.ioctl(m.IOC_START)
        while not arena.info()['status'] & (1 << 5):
            if arena.info()['status'] & ((1 << 3) | (1 << 4)): raise RuntimeError('fabric fault')
            if time.monotonic() - begin > 120: raise TimeoutError('probe watchdog')
            time.sleep(.01)
        arena.ioctl(m.IOC_RETURN)
        if struct.unpack_from('<4I', arena.maps['trace']) != (0x31505152, 1, 8, 0):
            raise ValueError('requant probe failed')
        records = []
        for index in range(8):
            kind, low, high, checksum, count, engine, jobs, status = struct.unpack_from('<8I', arena.maps['trace'], 32+index*32)
            cycles = low | high << 32
            if kind != index or not cycles or status or count != [256, 3072, 12288, 49152][index//2]:
                raise ValueError('invalid requant record')
            records.append(dict(shape=index//2, mode='sfpu' if index%2 else 'cpu',
                                cycles=cycles, seconds=cycles/m.FABRIC_HZ, elements=count,
                                cycles_per_element=cycles/count, checksum=checksum, engine_cycles=engine, jobs=jobs))
        for index in range(0, 8, 2):
            if records[index]['checksum'] != records[index+1]['checksum']: raise ValueError('differential mismatch')
        report.update(status='PASS', records=records, host_seconds=time.monotonic()-begin)
    finally:
        if arena.info()['owner']: arena.ioctl(m.IOC_RETURN)
        report['returned'] = arena.info()
        if cluster is not None: report['hart_results'] = [int(x) for x in cluster.array[0xd000//4:0xd080//4]]
        arena.close(); report['cleanup'] = 'safe return, mappings and file closed'
        args.output.write_text(json.dumps(report, indent=2)+'\n')
    print('M5 FAST REQUANT PROBE PASS', json.dumps(records), flush=True)


if __name__ == '__main__': main()
