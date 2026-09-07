#ifndef PA_M5_SCALAR_AFFINE_ROUND_H
#define PA_M5_SCALAR_AFFINE_ROUND_H
#include <stdint.h>

/* Positive finite binary64 * 2^shift, shift<=31, rounded to nearest/even.
 * Affine metadata only distinguishes [0,2^31) from invalid >=2^31, so the
 * latter is a sentinel. No generic uint64 shifting/masking is needed. */
static inline uint32_t pa_scalar_rne_scaled32(uint64_t bits, uint32_t shift) {
  uint32_t high = (uint32_t)(bits >> 32), low = (uint32_t)bits;
  uint32_t encoded = (high >> 20) & 2047u;
  if (!encoded) return 0; /* Even scaled subnormals are below 0.5. */
  int exponent = (int)encoded - 1023 + (int)shift;
  if (exponent < -1) return 0;
  if (exponent == -1) return (high & UINT32_C(0xfffff)) || low;
  if (exponent >= 31) return UINT32_C(0x80000000);
  uint32_t mantissa_high = (high & UINT32_C(0xfffff)) | UINT32_C(0x100000);
  uint32_t right = (uint32_t)(52-exponent), quotient, remainder, half;
  if (right < 32) {
    quotient = (mantissa_high << (32-right)) | (low >> right);
    remainder = low & ((UINT32_C(1) << right)-1u);
    half = UINT32_C(1) << (right-1u);
    return quotient + (remainder > half || (remainder == half && (quotient & 1u)));
  }
  if (right == 32) {
    quotient = mantissa_high;
    remainder = low; half = UINT32_C(0x80000000);
    return quotient + (remainder > half || (remainder == half && (quotient & 1u)));
  }
  right -= 32;
  quotient = mantissa_high >> right;
  remainder = mantissa_high & ((UINT32_C(1) << right)-1u);
  half = UINT32_C(1) << (right-1u);
  return quotient + (remainder > half ||
                     (remainder == half && (low || (quotient & 1u))));
}
#endif
