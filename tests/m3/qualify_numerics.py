#!/usr/bin/env python3
"""Gate M3 v1 operator formats against the frozen numerical budgets.

Writes reproducible numerical evidence, not a fabric/board acceptance result.
Accuracy is against the high-precision operation on represented inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from ref.sfpu_ref import (gelu_high, gelu_int, layernorm_high, layernorm_int,
                         softmax_high, softmax_int, dynamic_int8_parameters,
                         requantize_int8, affine_int, ACT_SCALE, PROB_SCALE)

SEED = 0x50414D33
# Frozen in docs/NUMERICS.md before arithmetic RTL. Changes need versioned
# rationale and requalification; do not enlarge a limit to hide a failure.
GELU_ABS = 1 / 512 + 1e-12
LAYERNORM_ABS = 1 / 128
SOFTMAX_ABS = 1 / 2048


def qualify(random_cases=1000):
    rng = np.random.default_rng(SEED)
    report = {"status": "PASS", "stage": "G2 frozen v1 reference qualification, not RTL",
              "seed": SEED, "random_cases_per_vector_op": random_cases,
              "reference_sha256": hashlib.sha256(Path("ref/sfpu_ref.py").read_bytes()).hexdigest(),
              "gelu": {"values": 65536, "max_abs": 0.0, "budget": GELU_ABS},
              "layernorm": {"vectors": 0, "elements": 0, "max_abs": 0.0,
                            "budget": LAYERNORM_ABS},
              "softmax": {"vectors": 0, "elements": 0, "max_abs": 0.0,
                          "max_l1": 0.0, "budget_abs": SOFTMAX_ABS,
                          "budget_l1": "valid_count/32768 + 1/1024",
                          "exact_mass": True},
              "requantization": {"vectors": 0, "max_code_error": 0.0, "budget": 0.5},
              "affine": {"vectors": 0, "exact_half_lsb_bound": True},
              "affine_gelu": {"vectors": 0, "max_abs": 0.0, "budget": 1 / 128}}
    for base in range(-32768, 32768, 1024):
        x = np.arange(base, base + 1024, dtype=np.int32)
        fixed = gelu_int(x).astype(np.float64) / ACT_SCALE
        gold = gelu_high(x / ACT_SCALE)
        error = float(np.max(np.abs(fixed - gold)))
        report["gelu"]["max_abs"] = max(report["gelu"]["max_abs"], error)
        if error > GELU_ABS:
            raise AssertionError(f"GELU abs error {error}")

    def check_ln(x, g, b, label):
        fixed = layernorm_int(x, g, b).astype(np.float64) / ACT_SCALE
        gold = layernorm_high(x, g, b)
        error = float(np.max(np.abs(fixed - gold)))
        result = report["layernorm"]
        result["vectors"] += 1
        result["elements"] += len(x)
        if error > result["max_abs"]:
            result["max_abs"], result["worst_case"] = error, label
        if error > LAYERNORM_ABS:
            raise AssertionError(f"LayerNorm {label}: abs error {error}")

    def check_softmax(x, mask, label):
        raw = softmax_int(x, mask)
        fixed = raw.astype(np.float64) / PROB_SCALE
        gold = softmax_high(x, mask)
        error = float(np.max(np.abs(fixed - gold)))
        l1 = float(np.sum(np.abs(fixed - gold)))
        result = report["softmax"]
        result["vectors"] += 1
        result["elements"] += len(x)
        if error > result["max_abs"]:
            result["max_abs"], result["worst_case"] = error, label
        result["max_l1"] = max(result["max_l1"], l1)
        if (error > SOFTMAX_ABS or l1 > np.count_nonzero(mask) / PROB_SCALE + 1 / 1024
                or np.any(raw[~mask] != 0)
                or int(raw.astype(np.uint64).sum()) != (PROB_SCALE if np.any(mask) else 0)):
            raise AssertionError(f"softmax {label}: abs={error}, L1={l1}")

    for length in (1, 2, 3, 15, 16, 17, 64, 767, 768, 769, 1023, 1024, 3071, 3072):
        for mode in ("zeros", "constant_min", "constant_max", "near_constant",
                     "alternating", "one_outlier"):
            x = np.zeros(length, dtype=np.int32)
            if mode == "constant_min":
                x.fill(-32768)
            elif mode in ("constant_max", "near_constant"):
                x.fill(32767)
                if mode == "near_constant":
                    x[-1] -= 1
            elif mode == "alternating":
                x[::2], x[1::2] = -32768, 32767
            elif mode == "one_outlier":
                x[-1] = 32767
            for gain in (-32768, -4096, 0, 4096, 32767):
                check_ln(x, np.full(length, gain, dtype=np.int32),
                         np.zeros(length, dtype=np.int32), f"{length}/{mode}/g{gain}")
        if length <= 1024:
            for mode in ("uniform", "extremes", "cutoff", "near_equal", "dominant"):
                x = np.zeros(length, dtype=np.int32)
                if mode == "extremes":
                    x.fill(-32768)
                    x[-1] = 32767
                elif mode == "cutoff":
                    x.fill(-4096)
                    x[-1] = 0
                elif mode == "near_equal":
                    x = np.arange(length, dtype=np.int32) % 16
                elif mode == "dominant":
                    x[-1] = 512
                for masking in ("none", "prefix", "sparse", "all"):
                    mask = np.ones(length, dtype=bool)
                    if masking == "prefix":
                        mask[length // 2:] = False
                    elif masking == "sparse":
                        mask[1::2] = False
                    elif masking == "all":
                        mask[:] = False
                    check_softmax(x, mask, f"{length}/{mode}/{masking}")

    for index in range(random_cases):
        length = int(rng.integers(1, 3073))
        spread = (1, 2, 8, 256, 4096, 32768)[index % 6]
        x = rng.integers(-spread, spread, length, dtype=np.int32)
        gain = rng.integers(-32768, 32768, length, dtype=np.int32)
        bias = rng.integers(-32768, 32768, length, dtype=np.int32)
        check_ln(x, gain, bias, f"random/{index}/spread{spread}")
        multiplier, shift = dynamic_int8_parameters(x)
        converted = requantize_int8(x, multiplier, shift)
        if np.any(converted == -128):
            raise AssertionError("symmetric amax/127 conversion unexpectedly used -128")
        ideal_codes = np.clip(x.astype(np.float64) * multiplier / (1 << shift), -128, 127)
        code_error = float(np.max(np.abs(converted.astype(np.float64) - ideal_codes)))
        if code_error > 0.5:
            raise AssertionError("requantization exceeds half-code error")
        report["requantization"]["max_code_error"] = max(
            report["requantization"]["max_code_error"], code_error)
        report["requantization"]["vectors"] += 1
        length = int(rng.integers(1, 1025))
        x = rng.integers(-spread, spread, length, dtype=np.int32)
        mask = rng.random(length) > ((index % 10) / 10)
        check_softmax(x, mask, f"random/{index}/spread{spread}")
        # Exercise full-width products and bias cancellation without using the
        # same rounding function to construct the independent error bound.
        values = rng.integers(-(1 << 31), 1 << 31, 16, dtype=np.int64)
        scales = rng.integers(0, 1 << 31, 16, dtype=np.int64)
        shift = index % 32
        denominator = 1 << shift
        biases = []
        for value, scale in zip(values, scales):
            center = -(int(value) * int(scale) // denominator)
            biases.append(max(-(1 << 31), min((1 << 31) - 1,
                          center + int(rng.integers(-32768, 32768)))))
        fixed = affine_int(values, scales, biases, shift)
        clipped_numerators = []
        for value, scale, bias, observed in zip(values, scales, biases, fixed):
            numerator = int(value) * int(scale) + bias * denominator
            clipped = max(-32768 * denominator, min(32767 * denominator, numerator))
            clipped_numerators.append(clipped)
            if 2 * abs(int(observed) * denominator - clipped) > denominator:
                raise AssertionError("affine exceeds exact rational half-LSB bound")
        continuous = np.asarray(clipped_numerators, dtype=np.float64) / denominator / ACT_SCALE
        fused_error = float(np.max(np.abs(gelu_int(fixed).astype(np.float64) / ACT_SCALE -
                                         gelu_high(continuous))))
        if fused_error > 1 / 128:
            raise AssertionError("affine-GELU exceeds frozen error budget")
        report["affine"]["vectors"] += 1
        report["affine_gelu"]["vectors"] += 1
        report["affine_gelu"]["max_abs"] = max(report["affine_gelu"]["max_abs"], fused_error)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--random-cases", type=int, default=1000)
    args = parser.parse_args()
    if args.random_cases < 1000:
        parser.error("qualification requires at least 1000 random cases per vector op")
    report = qualify(args.random_cases)
    encoded = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
