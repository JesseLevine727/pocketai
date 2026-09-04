#!/usr/bin/env python3
"""Unit tests for the authoritative M2 GEMM and packet contract."""

from __future__ import annotations

import unittest

import numpy as np

from ref.gemm_ref import (
    Descriptor,
    MAX_INT16,
    MIN_INT16,
    evaluate_packed,
    gemm_int8_int16,
    pack_output_words,
    unpack_output_words,
)


class GemmReferenceTest(unittest.TestCase):
    def test_signed_dot_product(self) -> None:
        a = np.array([[-128, -3, 0, 7, 127]], dtype=np.int8)
        b = np.array([[127], [-9], [4], [-11], [-128]], dtype=np.int8)
        expected = -128 * 127 + -3 * -9 + 7 * -11 + 127 * -128
        self.assertEqual(int(gemm_int8_int16(a, b)[0, 0]), expected)

    def test_saturates_once_after_wide_accumulation(self) -> None:
        positive = gemm_int8_int16(
            np.full((1, 768), 127, dtype=np.int8),
            np.full((768, 1), 127, dtype=np.int8),
        )
        negative = gemm_int8_int16(
            np.full((1, 768), -128, dtype=np.int8),
            np.full((768, 1), 127, dtype=np.int8),
        )
        self.assertEqual(int(positive[0, 0]), MAX_INT16)
        self.assertEqual(int(negative[0, 0]), MIN_INT16)

    def test_row_padding_and_round_trip(self) -> None:
        descriptor = Descriptor(m=3, n=5, k=7, tag=0x1234)
        a = np.arange(21, dtype=np.int16).reshape(3, 7).astype(np.int8) - 10
        b = np.arange(35, dtype=np.int16).reshape(7, 5).astype(np.int8) - 17
        input_words, output_words = evaluate_packed(descriptor, a, b)
        self.assertEqual(len(input_words), 3 * 2 + 7 * 4)
        self.assertEqual(len(output_words), 3 * 8)
        expected = gemm_int8_int16(a, b)
        np.testing.assert_array_equal(
            unpack_output_words(descriptor, output_words), expected
        )
        padded = np.array(output_words, dtype=np.uint32).view(np.int16).reshape(3, 16)
        np.testing.assert_array_equal(padded[:, 5:], 0)

    def test_output_is_little_endian_lane_order(self) -> None:
        descriptor = Descriptor(m=1, n=2, k=1)
        words = pack_output_words(
            descriptor, np.array([[-2, 0x1234]], dtype=np.int16)
        )
        self.assertEqual(words[0], 0x1234FFFE)

    def test_invalid_descriptors_are_rejected(self) -> None:
        for descriptor in (
            Descriptor(0, 1, 1),
            Descriptor(17, 1, 1),
            Descriptor(1, 0, 1),
            Descriptor(1, 17, 1),
            Descriptor(1, 1, 0),
            Descriptor(1, 1, 769),
            Descriptor(1, 1, 1, flags=1),
        ):
            with self.assertRaises(ValueError):
                descriptor.validate()


if __name__ == "__main__":
    unittest.main()
