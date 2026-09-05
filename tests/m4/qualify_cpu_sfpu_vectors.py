"""Replay all immutable accepted M3 SFPU vectors against the native CPU backend."""
import argparse
import json
from pathlib import Path
import numpy as np
from ref.m3_packets import read_packets
from ref.sfpu_stream import SfpuDescriptor
from ref.m4_cpu_sfpu import CpuSfpu
from ref.m4_model_pack import file_sha256


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--vectors', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('refusing to overwrite evidence')
    vectors_hash = file_sha256(args.vectors)
    if vectors_hash != '79a3933da00f82a796acdfe90fde4147dd5548b5abb702d060c4b201bec6b082':
        raise ValueError('not the accepted M3 SFPU packet corpus')
    packets, seed = read_packets(args.vectors)
    if len(packets) != 3472 or {p.parameters[0] for p in packets} != set(range(1, 8)):
        raise ValueError('incomplete SFPU corpus')
    cpu = CpuSfpu(args.library)
    for packet in packets:
        descriptor = SfpuDescriptor(*packet.parameters, tag=packet.tag)
        actual = cpu(descriptor, packet.inputs).view(np.uint32)
        np.testing.assert_array_equal(actual, packet.expected, err_msg=f'SFPU tag {packet.tag}')
    report = {'status': 'PASS', 'cases': len(packets), 'vectors_sha256': vectors_hash,
              'library_sha256': file_sha256(args.library), 'runner_sha256': file_sha256(__file__),
              'seed': seed, 'numpy': np.__version__, 'limitation': 'Native CPU arithmetic, not new FPGA verification.'}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('M4 NATIVE CPU ALL M3 SFPU PASS', json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
