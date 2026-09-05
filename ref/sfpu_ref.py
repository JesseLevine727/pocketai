#!/usr/bin/env python3
"""M3 numerical contract v1; see docs/NUMERICS.md and M3_ARCHITECTURE.md.

High-precision float64 and bit-exact integer functions are deliberately separate.
Integer activation storage uses a 2^-8 scale; LayerNorm gain uses 2^-12;
softmax returns unsigned probability units of 2^-15. This is operator arithmetic,
not a claim of full-model GPT-2 quantization accuracy.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

ACT_SCALE = 256
GAIN_SCALE = 4096
PROB_SCALE = 32768
MAX_VECTOR = 3072
MAX_SOFTMAX = 1024
EPSILON = 1e-5


def rne_div(numerator: int, denominator: int) -> int:
    """Round rational to nearest integer, exact halfway ties to even."""
    if denominator <= 0:
        raise ValueError("denominator must be positive")
    magnitude = abs(int(numerator))
    quotient, remainder = divmod(magnitude, int(denominator))
    if 2 * remainder > denominator or (2 * remainder == denominator and quotient & 1):
        quotient += 1
    return -quotient if numerator < 0 else quotient


def sat16(value: int) -> int:
    return max(-32768, min(32767, int(value)))


def checked_vector(values: Sequence[int], maximum: int = MAX_VECTOR,
                   lower: int = -32768, upper: int = 32767) -> list[int]:
    array = np.asarray(values)
    if array.ndim != 1 or not 1 <= len(array) <= maximum:
        raise ValueError(f"expected vector length 1..{maximum}")
    if not np.issubdtype(array.dtype, np.integer):
        raise TypeError("integer input required")
    if np.any(array < lower) or np.any(array > upper):
        raise ValueError("input outside declared range")
    return [int(x) for x in array]


def gelu_high(x):
    x = np.asarray(x, dtype=np.float64)
    return 0.5 * x * (1.0 + np.tanh(math.sqrt(2.0 / math.pi) * (x + 0.044715 * x**3)))


# Positive-domain exact-grid GELU, using oddness of tanh for the negative half.
# Runtime fabric will read a generated/pinned ROM, not evaluate transcendental
# functions. |x| >= 8 has a negligible tail at the declared output resolution.
GELU_TABLE = tuple(int(round(float(gelu_high(i / ACT_SCALE)) * ACT_SCALE))
                   for i in range(8 * ACT_SCALE + 1))
# exp(-d), step=1/16 over [0,16], unsigned scale 2^24. Linear interpolation uses
# the four low raw-score bits. Entry zero needs 25 bits to represent 1 exactly.
EXP_TABLE = tuple(int(round(math.exp(-i / 16) * (1 << 24))) for i in range(257))


def gelu_int(values: Sequence[int]) -> np.ndarray:
    x = checked_vector(values)
    result = []
    for raw in x:
        magnitude = abs(raw)
        positive = GELU_TABLE[magnitude] if magnitude <= 2048 else magnitude
        result.append(positive if raw >= 0 else positive - magnitude)
    return np.asarray(result, dtype=np.int16)


def layernorm_high(values: Sequence[int], gain: Sequence[int], bias: Sequence[int]):
    x = np.asarray(values, dtype=np.float64) / ACT_SCALE
    g = np.asarray(gain, dtype=np.float64) / GAIN_SCALE
    b = np.asarray(bias, dtype=np.float64) / ACT_SCALE
    centered = x - np.mean(x)
    result = centered / np.sqrt(np.mean(centered * centered) + EPSILON) * g + b
    return np.clip(result, -128.0, 32767 / ACT_SCALE)


def layernorm_int(values: Sequence[int], gain: Sequence[int], bias: Sequence[int]):
    x = checked_vector(values)
    g = checked_vector(gain)
    b = checked_vector(bias)
    if len(x) != len(g) or len(x) != len(b):
        raise ValueError("LayerNorm plane lengths differ")
    length = len(x)
    total = sum(x)
    squares = sum(v * v for v in x)
    variance_numerator = length * squares - total * total
    # D = floor(4096*sqrt(L*T-S^2 + epsilon*256^2*L^2)).
    # A rounded Q24 radicand preserves fractional epsilon without subtractive
    # cancellation. Maximum radicand fits unsigned 80 bits for L <= 3072.
    epsilon_term = rne_div(length * length * (1 << 40), 100000)
    denominator = math.isqrt((variance_numerator << 24) + epsilon_term)
    if denominator <= 0:
        raise AssertionError("positive epsilon must produce a positive denominator")
    # The gain's 2^-12 cancels the denominator's 2^12. Round once directly
    # into 2^-8 output units, add the already-quantized bias, then saturate.
    result = [sat16(rne_div((length * raw - total) * scale * ACT_SCALE,
                           denominator) + offset)
              for raw, scale, offset in zip(x, g, b)]
    return np.asarray(result, dtype=np.int16)


def exp_negative_int(difference: int) -> int:
    if difference < 0:
        raise ValueError("max-subtracted difference must be nonnegative")
    if difference >= 4096:
        return 0
    index, fraction = divmod(int(difference), 16)
    return rne_div(EXP_TABLE[index] * (16 - fraction) +
                   EXP_TABLE[index + 1] * fraction, 16)


def softmax_high(values: Sequence[int], valid: Sequence[bool]):
    x = np.asarray(values, dtype=np.float64) / ACT_SCALE
    mask = np.asarray(valid, dtype=bool)
    out = np.zeros_like(x)
    if np.any(mask):
        weights = np.exp(x[mask] - np.max(x[mask]))
        out[mask] = weights / np.sum(weights)
    return out


def softmax_int(values: Sequence[int], valid: Sequence[bool]):
    x = checked_vector(values, maximum=MAX_SOFTMAX)
    mask = np.asarray(valid)
    if mask.dtype != np.bool_ or mask.shape != (len(x),):
        raise ValueError("one boolean validity bit per score required")
    if not np.any(mask):
        return np.zeros(len(x), dtype=np.uint16)
    maximum = max(raw for raw, keep in zip(x, mask) if keep)
    weights = [exp_negative_int(maximum - raw) if keep else 0 for raw, keep in zip(x, mask)]
    total = sum(weights)
    quantized = [weight * PROB_SCALE // total for weight in weights]
    remainder = PROB_SCALE - sum(quantized)
    # Deterministic mass correction: +1 to the first remainder nonzero weights.
    # Each entry differs from its exact LUT-normalized probability by <1 LSB;
    # masked entries stay zero, and total mass is exactly 32768.
    for index, weight in enumerate(weights):
        if weight and remainder:
            quantized[index] += 1
            remainder -= 1
    if remainder:
        raise AssertionError("normalization correction must fit valid entries")
    return np.asarray(quantized, dtype=np.uint16)


def add_int(values: Sequence[int], other: Sequence[int]) -> np.ndarray:
    x, y = checked_vector(values), checked_vector(other)
    if len(x) != len(y):
        raise ValueError("addition plane lengths differ")
    return np.asarray([sat16(a + b) for a, b in zip(x, y)], dtype=np.int16)


def affine_int(values: Sequence[int], multipliers: Sequence[int],
               biases: Sequence[int], shift: int) -> np.ndarray:
    x = checked_vector(values, lower=-(1 << 31), upper=(1 << 31) - 1)
    scales = checked_vector(multipliers, lower=0, upper=(1 << 31) - 1)
    b = checked_vector(biases, lower=-(1 << 31), upper=(1 << 31) - 1)
    if not 0 <= shift <= 31 or len(x) != len(scales) or len(x) != len(b):
        raise ValueError("invalid affine planes/shift")
    return np.asarray([sat16(rne_div(raw * scale, 1 << shift) + bias)
                       for raw, scale, bias in zip(x, scales, b)], dtype=np.int16)


def requantize_int8(values: Sequence[int], multiplier: int, shift: int):
    # int32 accepts signed activation words AND unsigned Q0.15 probability
    # words (1.0 == 32768). Never reinterpret the latter as signed int16.
    x = checked_vector(values, lower=-(1 << 31), upper=(1 << 31) - 1)
    if not 0 <= multiplier < (1 << 31) or not 0 <= shift <= 31:
        raise ValueError("invalid requantization multiplier/shift")
    return np.asarray([max(-128, min(127, rne_div(raw * multiplier, 1 << shift)))
                       for raw in x], dtype=np.int8)


def dynamic_int8_parameters(values: Sequence[int]) -> tuple[int, int]:
    """Symmetric activation conversion, fixed shift=24, zero point=0.

    This policy introduces W8A8 arithmetic despite int16 activation storage.
    Model calibration and model-level accuracy remain separate M4 concerns.
    """
    # Also accept the unsigned probability endpoint 32768. This function is
    # for represented activation/probability vectors, not arbitrary wide sums.
    x = checked_vector(values, upper=32768)
    maximum = max(abs(raw) for raw in x)
    return (rne_div(127 << 24, maximum) if maximum else 0, 24)
