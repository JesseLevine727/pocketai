#!/usr/bin/env python3
"""Reproducible numerical packets for the complete SFPU RTL shell."""
import argparse
import json
from pathlib import Path
import struct
import numpy as np
from ref.sfpu_stream import Op, SfpuDescriptor, evaluate_and_pack, expected_compute_cycles
from ref.sfpu_ref import (gelu_high, layernorm_high, softmax_high, dynamic_int8_parameters,
                         affine_int)

SEED = 0x53465033


def cases(random_cases):
    rng = np.random.default_rng(SEED)
    # Exhaust the entire scalar GELU domain with packets large enough to test
    # address/count boundaries as well as lookup/tail values.
    for base in range(-32768, 32768, 1024):
        yield SfpuDescriptor(Op.GELU, 1024), (np.arange(base, base + 1024, dtype=np.int32),)
    for length in (1, 2, 3, 15, 16, 17, 767, 768, 1023, 1024, 3071, 3072):
        yield SfpuDescriptor(Op.GELU, length), (np.arange(length, dtype=np.int32) - length // 2,)
        for mode in ("zero", "near_constant", "extremes", "outlier"):
            x = np.zeros(length, dtype=np.int32)
            if mode == "near_constant":
                x[:] = 32767
                x[-1] -= 1
            elif mode == "extremes":
                x[::2], x[1::2] = -32768, 32767
            elif mode == "outlier":
                x[-1] = -32768
            gain = rng.integers(-32768, 32768, length, dtype=np.int32)
            bias = rng.integers(-32768, 32768, length, dtype=np.int32)
            yield SfpuDescriptor(Op.LAYERNORM, length), (x, gain, bias)
            yield SfpuDescriptor(Op.ADD, length), (x, bias)
        if length <= 1024:
            for spread in (0, 16, 4096, 65535):
                x = np.full(length, -32768, dtype=np.int32)
                x[-1] += spread
                for masking in ("none", "prefix", "all"):
                    valid = np.ones(length, dtype=bool)
                    if masking == "prefix":
                        valid[length // 2:] = False
                    elif masking == "all":
                        valid[:] = False
                    yield SfpuDescriptor(Op.SOFTMAX, length), (x, valid)
        for shift in (0, 1, 15, 24, 31):
            x = rng.integers(-(1 << 31), 1 << 31, length, dtype=np.int64)
            scale = rng.integers(0, 1 << 31, length, dtype=np.int64)
            bias = rng.integers(-(1 << 31), 1 << 31, length, dtype=np.int64)
            for op in (Op.AFFINE, Op.AFFINE_GELU):
                yield SfpuDescriptor(op, length, shift=shift), (x, scale, bias)
            yield SfpuDescriptor(Op.REQUANT8, length, shift=shift, multiplier=0x7fffffff), (x,)
    lengths = [1, 2, 3, 15, 16, 17, 31, 32, 63, 64, 767, 768, 1023, 1024, 3071, 3072]
    for index in range(random_cases):
        length = int(rng.choice(lengths))
        spread = (1, 2, 16, 256, 4096, 32768)[index % 6]
        x = rng.integers(-spread, spread, length, dtype=np.int32)
        gain = rng.integers(-32768, 32768, length, dtype=np.int32)
        bias = rng.integers(-32768, 32768, length, dtype=np.int32)
        yield SfpuDescriptor(Op.LAYERNORM, length), (x, gain, bias)
        soft_length = min(length, 1024)
        scores = x[:soft_length]
        valid = rng.random(soft_length) > (index % 10) / 10
        yield SfpuDescriptor(Op.SOFTMAX, soft_length), (scores, valid)
        if index % 4 == 0:
            multiplier, shift = dynamic_int8_parameters(x)
            yield SfpuDescriptor(Op.REQUANT8, length, shift=shift, multiplier=multiplier), (x,)
            yield SfpuDescriptor(Op.ADD, length), (x, bias)
            scales = rng.integers(0, 1 << 24, length, dtype=np.int32)
            for op in (Op.AFFINE, Op.AFFINE_GELU):
                yield SfpuDescriptor(op, length, shift=24), (x, scales, bias)


def check_accuracy(d, planes, packed):
    observed = packed.view("<i4").astype(np.float64)
    if d.op == Op.GELU:
        error = float(np.max(np.abs(observed / 256 - gelu_high(planes[0] / 256))))
        assert error <= 1 / 512 + 1e-12
    elif d.op == Op.LAYERNORM:
        error = float(np.max(np.abs(observed / 256 - layernorm_high(*planes))))
        assert error <= 1 / 128
    elif d.op == Op.SOFTMAX:
        gold = softmax_high(*planes)
        error = float(np.max(np.abs(observed / 32768 - gold)))
        assert error <= 1 / 2048
        assert np.sum(np.abs(observed / 32768 - gold)) <= np.count_nonzero(planes[1]) / 32768 + 1 / 1024
        assert int(observed.sum()) == (32768 if np.any(planes[1]) else 0)
        assert np.all(observed[~planes[1]] == 0)
    elif d.op in (Op.AFFINE, Op.REQUANT8, Op.AFFINE_GELU):
        denominator = 1 << d.shift
        raw_output = affine_int(*planes, d.shift) if d.op == Op.AFFINE_GELU else packed.view("<i4")
        clipped_targets = []
        for index, raw in enumerate(planes[0]):
            multiplier = d.multiplier if d.op == Op.REQUANT8 else int(planes[1][index])
            bias = 0 if d.op == Op.REQUANT8 else int(planes[2][index])
            numerator = int(raw) * multiplier + bias * denominator
            low, high = (-128, 127) if d.op == Op.REQUANT8 else (-32768, 32767)
            clipped = max(low * denominator, min(high * denominator, numerator))
            assert 2 * abs(int(raw_output[index]) * denominator - clipped) <= denominator
            clipped_targets.append(clipped / denominator)
        if d.op == Op.AFFINE_GELU:
            error = float(np.max(np.abs(observed / 256 - gelu_high(np.asarray(clipped_targets) / 256))))
            assert error <= 1 / 128
        else:
            error = float(np.max(np.abs(raw_output.astype(np.float64) - clipped_targets)))
    else:
        gold = np.clip(planes[0].astype(np.int64) + planes[1].astype(np.int64), -32768, 32767)
        assert np.array_equal(observed, gold)
        error = 0.0
    return error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--random-cases", type=int, default=1000)
    args = parser.parse_args()
    if args.random_cases < 1000:
        parser.error("at least 1000 randomized vectors per reduction op required")
    vectors = list(cases(args.random_cases))
    summary = {"seed": SEED, "cases": len(vectors), "operations": {}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("wb") as stream:
        stream.write(struct.pack("<III", 0x33504653, len(vectors), SEED))
        for index, (d, planes) in enumerate(vectors):
            d = SfpuDescriptor(d.op, d.length, d.shift, d.multiplier, tag=index + 1)
            inputs, outputs = evaluate_and_pack(d, planes)
            error = check_accuracy(d, planes, outputs)
            stats = summary["operations"].setdefault(d.op.name, {"vectors": 0, "elements": 0, "max_error": 0.0})
            stats["vectors"] += 1
            stats["elements"] += d.length
            stats["max_error"] = max(stats["max_error"], error)
            stream.write(struct.pack("<8I", d.op, d.length, d.shift, d.multiplier, d.tag,
                                     len(inputs), len(outputs), expected_compute_cycles(d, planes)))
            stream.write(inputs.tobytes())
            stream.write(outputs.tobytes())
    args.output.with_suffix(".json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"M3 SFPU VECTORS PASS cases={len(vectors)} random_per_reduction={args.random_cases} seed=0x{SEED:x}")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
