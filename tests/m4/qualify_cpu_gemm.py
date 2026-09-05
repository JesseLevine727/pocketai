"""Native kernel checks runnable unchanged on host and physical A9."""
import argparse
import json
from pathlib import Path
import numpy as np
from ref.m4_cpu import CpuGemm
from ref.m4_model_pack import file_sha256, tile_weights


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('refusing to overwrite native qualification evidence')
    cpu = CpuGemm(args.library)
    rng = np.random.default_rng(0x4d344350)
    count = 0
    for m, k, n in ((1, 1, 1), (3, 7, 17), (16, 768, 33), (3, 3072, 17), (1, 768, 50257)):
        for mode in ('random', 'positive_max', 'negative_max', 'cancellation'):
            a = rng.integers(-128, 128, (m, k), dtype=np.int8)
            b = rng.integers(-128, 128, (k, n), dtype=np.int8)
            if mode != 'random':
                a.fill(-128)
                b.fill(127 if mode == 'negative_max' else -128)
                if mode == 'cancellation':
                    b[k // 2:] = 127
            # Exact integer NumPy reference, never a native self-generated golden.
            # Bound the temporary int64 B conversion on the 491-MiB board;
            # converting the whole 768x50257 matrix would require >294 MiB.
            expected = np.empty((m, n), dtype=np.int64)
            for start in range(0, n, 128):
                expected[:, start:start + 128] = a.astype(np.int64) @ b[:, start:start + 128].astype(np.int64)
            tiles = tile_weights(b)
            result = cpu(a, tiles, n)
            np.testing.assert_array_equal(result, expected)
            count += 1
    report = {'status': 'PASS', 'backend': cpu.backend, 'cases': count,
              'library_sha256': file_sha256(args.library), 'runner_sha256': file_sha256(__file__),
              'numpy': np.__version__, 'limitation': 'Kernel correctness only; no full-model or performance claim.'}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('M4 NATIVE CPU GEMM PASS', json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
