#!/usr/bin/env python3
"""Generate deterministic binary vectors consumed by the Verilator M2 test."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ref.gemm_ref import Descriptor, evaluate_packed


MAGIC = 0x324D4547  # "GEM2" in a little-endian uint32
SEED = 0x50414D32
RANDOM_CASES = 1_000


def directed_cases() -> list[tuple[Descriptor, np.ndarray, np.ndarray]]:
    return [
        (
            Descriptor(16, 16, 1, tag=1),
            np.arange(-8, 8, dtype=np.int8).reshape(16, 1),
            np.arange(-8, 8, dtype=np.int8).reshape(1, 16),
        ),
        (
            Descriptor(3, 5, 7, tag=2),
            np.arange(21, dtype=np.int16).reshape(3, 7).astype(np.int8) - 10,
            np.arange(35, dtype=np.int16).reshape(7, 5).astype(np.int8) - 17,
        ),
        (
            Descriptor(1, 1, 768, tag=3),
            np.full((1, 768), 127, dtype=np.int8),
            np.full((768, 1), 127, dtype=np.int8),
        ),
        (
            Descriptor(1, 1, 768, tag=4),
            np.full((1, 768), -128, dtype=np.int8),
            np.full((768, 1), 127, dtype=np.int8),
        ),
        (
            Descriptor(2, 3, 9, tag=5),
            np.zeros((2, 9), dtype=np.int8),
            np.full((9, 3), -128, dtype=np.int8),
        ),
        (
            Descriptor(16, 16, 768, tag=6),
            np.full((16, 768), -128, dtype=np.int8),
            np.full((768, 16), -128, dtype=np.int8),
        ),
        # A large positive partial sum followed by cancellation proves that
        # int16 saturation occurs only at the end of the dot product.
        (
            Descriptor(13, 15, 768, tag=7),
            np.full((13, 768), 127, dtype=np.int8),
            np.concatenate((np.full((384, 15), 127, dtype=np.int8),
                            np.full((384, 15), -127, dtype=np.int8))),
        ),
    ]


def make_cases(count: int) -> list[tuple[Descriptor, np.ndarray, np.ndarray]]:
    cases = directed_cases()
    rng = np.random.default_rng(SEED)
    k_choices = np.array([1, 2, 3, 4, 7, 8, 15, 16, 31, 32, 63, 64,
                          127, 128, 191, 192, 255, 256, 511, 512, 767, 768])
    for index in range(count):
        m = int(rng.integers(1, 17))
        n = int(rng.integers(1, 17))
        k = int(rng.choice(k_choices))
        descriptor = Descriptor(m, n, k, tag=0x1000 + index)
        a = rng.integers(-128, 128, size=(m, k), dtype=np.int16).astype(np.int8)
        b = rng.integers(-128, 128, size=(k, n), dtype=np.int16).astype(np.int8)
        cases.append((descriptor, a, b))
    return cases


def write_vectors(path: Path, random_cases: int) -> None:
    cases = make_cases(random_cases)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.write(struct.pack("<III", MAGIC, len(cases), SEED))
        for descriptor, a, b in cases:
            inputs, outputs = evaluate_packed(descriptor, a, b)
            # Poison inactive lanes: RTL must ignore them rather than rely on
            # the reference packer's usual zero padding.
            if descriptor.k % 4:
                for row in range(descriptor.m):
                    word = (row + 1) * descriptor.a_words_per_row - 1
                    for lane in range(descriptor.k % 4, 4):
                        inputs[word] |= 0xA5 << (8 * lane)
            b_start = descriptor.m * descriptor.a_words_per_row
            for inner in range(descriptor.k):
                for column in range(descriptor.n, 16):
                    word = b_start + inner * 4 + column // 4
                    inputs[word] |= 0x5A << (8 * (column % 4))
            stream.write(
                struct.pack(
                    "<IIIIIII",
                    descriptor.m,
                    descriptor.n,
                    descriptor.k,
                    descriptor.tag,
                    descriptor.flags,
                    len(inputs),
                    len(outputs),
                )
            )
            stream.write(struct.pack(f"<{len(inputs)}I", *inputs))
            stream.write(struct.pack(f"<{len(outputs)}I", *outputs))
    print(
        f"M2 VECTORS PASS cases={len(cases)} random={random_cases} "
        f"seed=0x{SEED:08x} path={path}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--random-cases", type=int, default=RANDOM_CASES)
    args = parser.parse_args()
    if args.random_cases < RANDOM_CASES:
        raise SystemExit(f"at least {RANDOM_CASES} randomized cases are required")
    write_vectors(args.output, args.random_cases)


if __name__ == "__main__":
    main()
