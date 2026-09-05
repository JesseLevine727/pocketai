#!/usr/bin/env python3
"""Mixed legacy/wide vectors for M3 GEMM, including all K=3072 corner cases."""
import argparse
from pathlib import Path
import struct

import numpy as np
from ref.gemm_ref import gemm_int8_int16
from ref.gemm_v3_ref import (M3GemmDescriptor, WIDE_RESULT_V1, gemm_wide_int32,
                             pack_input_v3, pack_output_v3)

SEED = 0x50414733


def make_cases(count):
    rng = np.random.default_rng(SEED)
    cases = []
    directed = [(16, 16, 1, 0, "small"), (3, 5, 769, 0x100, "random"),
                (1, 1, 3072, 0x100, "positive"), (1, 1, 3072, 0x100, "negative"),
                (2, 3, 1023, 0x100, "zero"), (16, 16, 3072, 0x100, "positive"),
                (13, 15, 3072, 0x100, "cancellation")]
    for index, (m, n, k, flags, mode) in enumerate(directed):
        a = rng.integers(-128, 128, (m, k), dtype=np.int16).astype(np.int8)
        b = rng.integers(-128, 128, (k, n), dtype=np.int16).astype(np.int8)
        if mode in ("positive", "negative"):
            a.fill(-128)
            b.fill(-128 if mode == "positive" else 127)
        elif mode == "zero":
            a.fill(0)
        elif mode == "cancellation":
            a.fill(127)
            b.fill(127)
            b[1536:] = -127
            b[-1] = -126
        cases.append((M3GemmDescriptor(m, n, k, tag=index + 1, flags=flags), a, b))
    lengths = [1, 2, 3, 4, 7, 31, 32, 255, 256, 767, 768, 769,
               1023, 1024, 2047, 2048, 3071, 3072]
    for index in range(count):
        flags = 0 if index % 4 == 0 else WIDE_RESULT_V1
        m, n = (int(v) for v in rng.integers(1, 17, 2))
        k = int(rng.choice(lengths[:11] if flags == 0 else lengths))
        a = rng.integers(-128, 128, (m, k), dtype=np.int16).astype(np.int8)
        b = rng.integers(-128, 128, (k, n), dtype=np.int16).astype(np.int8)
        cases.append((M3GemmDescriptor(m, n, k, tag=0x3000 + index, flags=flags), a, b))
    return cases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--random-cases", type=int, default=1000)
    args = parser.parse_args()
    if args.random_cases < 1000:
        parser.error("at least 1000 random cases required")
    cases = make_cases(args.random_cases)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("wb") as stream:
        stream.write(struct.pack("<III", 0x324d4547, len(cases), SEED))
        for d, a, b in cases:
            inputs = pack_input_v3(d, a, b)
            result = gemm_wide_int32(a, b) if d.flags else gemm_int8_int16(a, b)
            outputs = pack_output_v3(d, result)
            # Inactive input bytes are deliberately nonzero.
            byte_input = inputs.view(np.uint8)
            a_plane = byte_input[:d.m * d.a_words_per_row * 4].reshape(d.m, -1)
            a_plane[:, d.k:] = 0xa5
            b_plane = byte_input[d.m * d.a_words_per_row * 4:].reshape(d.k, 16)
            b_plane[:, d.n:] = 0x5a
            stream.write(struct.pack("<IIIIIII", d.m, d.n, d.k, d.tag, d.flags,
                                     len(inputs), len(outputs)))
            stream.write(inputs.tobytes())
            stream.write(outputs.tobytes())
    print(f"M3 GEMM VECTORS PASS cases={len(cases)} random={args.random_cases} seed=0x{SEED:08x}")


if __name__ == "__main__":
    main()
