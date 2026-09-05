"""Native CPU arithmetic vs independent frozen Python integer packet reference."""
import argparse
import json
from pathlib import Path
import numpy as np
from ref.m4_cpu_sfpu import CpuSfpu
from ref.m4_model_pack import file_sha256
from ref.sfpu_stream import SfpuDescriptor, Op, evaluate_and_pack


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('refusing to overwrite CPU SFPU evidence')
    cpu = CpuSfpu(args.library)
    rng = np.random.default_rng(0x4d345343)
    count = 0
    for op in Op:
        for length in (1, 17, 64, 768, 1024 if op == Op.SOFTMAX else 3072):
            for mode in ('random', 'constant', 'near_constant', 'extreme'):
                x = rng.integers(-32768, 32768, length, dtype=np.int32)
                if mode == 'constant': x.fill(32767)
                if mode == 'near_constant': x[:] = np.arange(length) % 2 - 32768
                if mode == 'extreme': x[:] = np.where(np.arange(length) % 2, 32767, -32768)
                d = SfpuDescriptor(op, length)
                if op == Op.LAYERNORM:
                    planes = (x, rng.integers(-32768, 32768, length, dtype=np.int32),
                              rng.integers(-32768, 32768, length, dtype=np.int32))
                elif op == Op.SOFTMAX:
                    valid = rng.integers(0, 2, length).astype(bool)
                    if mode == 'constant': valid.fill(True)
                    if mode == 'extreme': valid.fill(False)
                    planes = (x, valid)
                elif op in (Op.AFFINE, Op.AFFINE_GELU):
                    x = rng.integers(-(1 << 31), 1 << 31, length, dtype=np.int64)
                    mult = rng.integers(0, 1 << 31, length, dtype=np.int64)
                    bias = rng.integers(-(1 << 31), 1 << 31, length, dtype=np.int64)
                    d = SfpuDescriptor(op, length, shift=int(rng.integers(0, 32)))
                    planes = (x, mult, bias)
                elif op == Op.REQUANT8:
                    x[0] = 32768  # unsigned probability endpoint stays positive
                    d = SfpuDescriptor(op, length, shift=int(rng.integers(0, 32)), multiplier=int(rng.integers(0, 1 << 31)))
                    planes = (x,)
                elif op == Op.ADD:
                    planes = (x, rng.integers(-32768, 32768, length, dtype=np.int32))
                else:
                    planes = (x,)
                words, expected = evaluate_and_pack(d, planes)
                actual = cpu(d, words)
                np.testing.assert_array_equal(actual.view(np.uint32), expected)
                count += 1
    report = {'status': 'PASS', 'cases': count, 'library_sha256': file_sha256(args.library),
              'runner_sha256': file_sha256(__file__), 'numpy': np.__version__,
              'limitation': 'Native CPU SFPU arithmetic, not FPGA equivalence or model performance.'}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('M4 NATIVE CPU SFPU PASS', json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
