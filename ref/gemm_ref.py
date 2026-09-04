#!/usr/bin/env python3
"""Authoritative M2 signed-int8 GEMM model and stream packing helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


MAX_M = 16
MAX_N = 16
MAX_K = 768
MIN_INT16 = -(1 << 15)
MAX_INT16 = (1 << 15) - 1


@dataclass(frozen=True)
class Descriptor:
    """One hardware tile: C[M,N] = sat16(A[M,K] @ B[K,N])."""

    m: int
    n: int
    k: int
    tag: int = 0
    flags: int = 0

    def validate(self) -> None:
        if not 1 <= self.m <= MAX_M:
            raise ValueError(f"m must be in [1, {MAX_M}], got {self.m}")
        if not 1 <= self.n <= MAX_N:
            raise ValueError(f"n must be in [1, {MAX_N}], got {self.n}")
        if not 1 <= self.k <= MAX_K:
            raise ValueError(f"k must be in [1, {MAX_K}], got {self.k}")
        if self.flags != 0:
            raise ValueError(f"M2 flags are reserved and must be zero, got {self.flags}")

    @property
    def a_words_per_row(self) -> int:
        return (self.k + 3) // 4

    @property
    def input_words(self) -> int:
        # A rows are padded to words. Every B row is padded to 16 columns.
        return self.m * self.a_words_per_row + self.k * 4

    @property
    def output_words(self) -> int:
        # Every C row carries 16 int16 lanes, including zero-padded columns.
        return self.m * 8

    @property
    def macs(self) -> int:
        return self.m * self.n * self.k


def _as_int8_matrix(value: np.ndarray, shape: tuple[int, int], name: str) -> np.ndarray:
    array = np.asarray(value)
    if array.shape != shape:
        raise ValueError(f"{name} must have shape {shape}, got {array.shape}")
    if not np.issubdtype(array.dtype, np.signedinteger):
        raise TypeError(f"{name} must contain signed integers, got {array.dtype}")
    if np.any(array < -128) or np.any(array > 127):
        raise ValueError(f"{name} contains a value outside signed int8")
    return array.astype(np.int8, copy=False)


def gemm_int8_int16(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Multiply in exact int64, then saturate once to signed int16."""

    a_array = np.asarray(a)
    b_array = np.asarray(b)
    if a_array.ndim != 2 or b_array.ndim != 2:
        raise ValueError("A and B must both be rank-2 matrices")
    if a_array.shape[1] != b_array.shape[0]:
        raise ValueError(f"inner dimensions differ: {a_array.shape} and {b_array.shape}")
    descriptor = Descriptor(a_array.shape[0], b_array.shape[1], a_array.shape[1])
    descriptor.validate()
    a_i8 = _as_int8_matrix(a_array, (descriptor.m, descriptor.k), "A")
    b_i8 = _as_int8_matrix(b_array, (descriptor.k, descriptor.n), "B")
    accumulated = a_i8.astype(np.int64) @ b_i8.astype(np.int64)
    return np.clip(accumulated, MIN_INT16, MAX_INT16).astype(np.int16)


def _pack_i8_word(values: Iterable[int]) -> int:
    word = 0
    for lane, value in enumerate(values):
        word |= (int(value) & 0xFF) << (8 * lane)
    return word


def pack_input_words(descriptor: Descriptor, a: np.ndarray, b: np.ndarray) -> list[int]:
    """Pack the exact little-endian A-then-B M2 input stream."""

    descriptor.validate()
    a_i8 = _as_int8_matrix(a, (descriptor.m, descriptor.k), "A")
    b_i8 = _as_int8_matrix(b, (descriptor.k, descriptor.n), "B")
    words: list[int] = []

    for row in range(descriptor.m):
        for base in range(0, descriptor.a_words_per_row * 4, 4):
            lanes = [int(a_i8[row, column]) if column < descriptor.k else 0
                     for column in range(base, base + 4)]
            words.append(_pack_i8_word(lanes))

    for inner in range(descriptor.k):
        for base in range(0, MAX_N, 4):
            lanes = [int(b_i8[inner, column]) if column < descriptor.n else 0
                     for column in range(base, base + 4)]
            words.append(_pack_i8_word(lanes))

    if len(words) != descriptor.input_words:
        raise AssertionError("internal input word-count mismatch")
    return words


def pack_output_words(descriptor: Descriptor, result: np.ndarray) -> list[int]:
    """Pack C as two little-endian int16 lanes per word, padding each row to 16."""

    descriptor.validate()
    result_array = np.asarray(result)
    if result_array.shape != (descriptor.m, descriptor.n):
        raise ValueError(
            f"result must have shape {(descriptor.m, descriptor.n)}, got {result_array.shape}"
        )
    if np.any(result_array < MIN_INT16) or np.any(result_array > MAX_INT16):
        raise ValueError("result contains a value outside signed int16")
    result_i16 = result_array.astype(np.int16, copy=False)
    words: list[int] = []
    for row in range(descriptor.m):
        for base in range(0, MAX_N, 2):
            lo = int(result_i16[row, base]) if base < descriptor.n else 0
            hi = int(result_i16[row, base + 1]) if base + 1 < descriptor.n else 0
            words.append((lo & 0xFFFF) | ((hi & 0xFFFF) << 16))
    if len(words) != descriptor.output_words:
        raise AssertionError("internal output word-count mismatch")
    return words


def unpack_output_words(descriptor: Descriptor, words: Iterable[int]) -> np.ndarray:
    """Decode a padded output packet and return only its active MxN matrix."""

    descriptor.validate()
    packed = list(words)
    if len(packed) != descriptor.output_words:
        raise ValueError(f"expected {descriptor.output_words} words, got {len(packed)}")
    padded = np.zeros((descriptor.m, MAX_N), dtype=np.int16)
    word_index = 0
    for row in range(descriptor.m):
        for base in range(0, MAX_N, 2):
            word = int(packed[word_index])
            padded[row, base] = np.array(word & 0xFFFF, dtype=np.uint16).view(np.int16)
            padded[row, base + 1] = np.array((word >> 16) & 0xFFFF, dtype=np.uint16).view(np.int16)
            word_index += 1
    return padded[:, : descriptor.n].copy()


def evaluate_packed(
    descriptor: Descriptor, a: np.ndarray, b: np.ndarray
) -> tuple[list[int], list[int]]:
    """Return a complete input packet and its exact expected output packet."""

    return (
        pack_input_words(descriptor, a, b),
        pack_output_words(descriptor, gemm_int8_int16(a, b)),
    )
