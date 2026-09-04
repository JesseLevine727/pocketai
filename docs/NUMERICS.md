# PocketAI-T numerical contracts

This document is the hardware/software numerical contract. RTL, firmware,
Python references, simulation vectors, and board tests must agree with it
exactly. A milestone may extend this file only before implementing the affected
datapath.

## M2 GEMM

For one descriptor, the accelerator computes

`C[M,N] = sat16(A[M,K] x B[K,N])`.

- `A` and `B` elements are two's-complement signed int8 (`-128..127`).
- Every product is an exact signed 8x8 multiplication yielding signed int16.
- Products accumulate in signed 25-bit registers. This covers the maximum M2
  dot-product magnitude, `768 * 128 * 128 = 12,582,912`, within the signed
  25-bit range `-16,777,216..16,777,215`.
- No saturation, truncation, wrapping, or rounding occurs between products.
- After the complete K-term dot product, the result saturates once to signed
  int16: values below `-32768` become `-32768`; values above `32767` become
  `32767`.
- There is no scaling, zero point, bias, rounding, or unsigned mode in M2.
- Legal dimensions are `1 <= M <= 16`, `1 <= N <= 16`, and
  `1 <= K <= 768`. All descriptor flag bits are reserved and must be zero.
- Partial M and N values compute only active output elements. Padded input bytes
  are ignored and padded output lanes are exactly zero.

The authoritative executable definition is `ref/gemm_ref.py`, which promotes
both inputs to signed int64 for the NumPy matrix product and then clips once to
int16. The extra software width prevents NumPy dtype behavior from silently
changing the hardware contract.

## M2 stream representation

All stream words are 32-bit and all four byte lanes are valid. Byte and halfword
lanes are little-endian within each word.

An input packet contains A followed immediately by B:

1. A is signed-int8 row-major. Each of its M rows is independently padded with
   zero bytes to a 32-bit boundary. Its length is `M * ceil(K/4)` words.
2. B is signed-int8 row-major. Every one of its K rows occupies exactly four
   words (16 columns); columns `N..15` are zero padding. Its length is `4*K`
   words.
3. AXI Stream `TLAST` is asserted only on the final B word. `TKEEP` is `0xf`
   on every word.

The total input length is `M*ceil(K/4) + 4*K` words.

An output packet contains C in signed-int16 row-major form. Every active row
occupies eight words (16 columns); columns `N..15` are zero. The low halfword is
the earlier column. `TLAST` is asserted only on the final word. The total output
length is `8*M` words.

Saturation is part of the compute operation. Packing and unpacking never alter
active numerical values.
