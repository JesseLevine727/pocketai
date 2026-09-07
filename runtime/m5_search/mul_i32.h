#ifndef PA_M5_SEARCH_MUL_I32_H
#define PA_M5_SEARCH_MUL_I32_H
#include <stdint.h>

/* Exact binary64 ((double)value)*scale, specialized to an int32 operand.
 * The integer conversion is exact. A normal scale has a 53-bit significand;
 * multiply it by the unsigned magnitude in two native 32x32 products, retaining
 * every product bit, then round once to nearest/even. Specials/subnormals use
 * the original arithmetic; this is not reduced-precision floating point. */
static inline double pa_search_mul_i32(int32_t value, double scale) {
  union { double floating; uint64_t bits; } input = {.floating = scale}, output;
  uint32_t encoded = (uint32_t)((input.bits >> 52) & 2047u);
  if (!encoded || encoded == 2047) return (double)value * scale;
  uint32_t magnitude = value < 0 ? 0u-(uint32_t)value : (uint32_t)value;
  uint64_t sign = (input.bits & UINT64_C(0x8000000000000000)) ^
                  (value < 0 ? UINT64_C(0x8000000000000000) : 0);
  if (!magnitude) { output.bits = sign; return output.floating; }
  uint32_t upper = (uint32_t)((input.bits >> 32) & UINT32_C(0xfffff)) | UINT32_C(0x100000);
  uint64_t product0 = (uint64_t)(uint32_t)input.bits * magnitude;
  uint64_t product1 = (uint64_t)upper * magnitude;
  uint64_t low = product0 + (product1 << 32);
  uint32_t high = (uint32_t)(product1 >> 32) + (low < product0);
  /* Product >=2^52 and <2^84. The CLZ operands are therefore nonzero. */
  uint32_t highest = high ? 95u-(uint32_t)__builtin_clz(high) :
                           63u-(uint32_t)__builtin_clz((uint32_t)(low >> 32));
  uint32_t shift = highest-52u; /* 0..31 */
  uint64_t rounded = low;
  if (shift) {
    rounded = (low >> shift) | ((uint64_t)high << (64u-shift));
    uint32_t remainder = (uint32_t)low & ((UINT32_C(1) << shift)-1u);
    uint32_t half = UINT32_C(1) << (shift-1u);
    rounded += remainder > half || (remainder == half && (rounded & 1u));
  }
  encoded += shift;
  if (rounded & (UINT64_C(1) << 53)) { rounded >>= 1; ++encoded; }
  output.bits = encoded >= 2047 ? sign | UINT64_C(0x7ff0000000000000) :
                sign | ((uint64_t)encoded << 52) | (rounded & UINT64_C(0xfffffffffffff));
  return output.floating;
}
#endif
