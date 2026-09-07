#ifndef PA_M5_TENTH_MUL_FACTOR_H
#define PA_M5_TENTH_MUL_FACTOR_H
#include <stdint.h>

typedef struct { double value; uint32_t low, high, exponent, sign; } pa_tenth_factor;
static inline pa_tenth_factor pa_tenth_prepare_factor(double value) {
  union { double floating; uint64_t bits; } data = {.floating = value};
  return (pa_tenth_factor){value, (uint32_t)data.bits,
      (uint32_t)((data.bits >> 32) & UINT32_C(0xfffff)) | UINT32_C(0x100000),
      (uint32_t)((data.bits >> 52) & 2047u), (uint32_t)(data.bits >> 63)};
}

/* Exact binary64 product; decode the row-constant operand once. Four full
 * native 32x32 products retain all 106 significant bits, then round once.
 * Special inputs and under/overflow edges retain the original operation. */
static inline double pa_tenth_mul_factor(const pa_tenth_factor *factor, double value) {
  union { double floating; uint64_t bits; } input = {.floating = value}, output;
  uint32_t encoded = (uint32_t)((input.bits >> 52) & 2047u);
  if (!encoded || encoded == 2047 || !factor->exponent || factor->exponent == 2047)
    return factor->value * value;
  uint32_t low = (uint32_t)input.bits;
  uint32_t high = (uint32_t)((input.bits >> 32) & UINT32_C(0xfffff)) | UINT32_C(0x100000);
  uint64_t p00 = (uint64_t)factor->low * low;
  uint64_t p01 = (uint64_t)factor->low * high;
  uint64_t p10 = (uint64_t)factor->high * low;
  uint64_t p11 = (uint64_t)factor->high * high;
  uint64_t lo0 = p00 + (p01 << 32);
  uint64_t lo = lo0 + (p10 << 32);
  uint64_t hi = p11 + (p01 >> 32) + (p10 >> 32) + (lo0 < p00) + (lo < lo0);
  uint32_t leading = (uint32_t)(hi >> 41); /* product high bit: 104 or 105 */
  uint32_t shift = 52u+leading;
  uint64_t rounded = (hi << (64u-shift)) | (lo >> shift);
  uint64_t remainder = lo & ((UINT64_C(1) << shift)-1);
  uint64_t half = UINT64_C(1) << (shift-1);
  rounded += remainder > half || (remainder == half && (rounded & 1u));
  int exponent = (int)factor->exponent + (int)encoded - 1023 + (int)leading;
  if (rounded & (UINT64_C(1) << 53)) { rounded >>= 1; ++exponent; }
  if (exponent <= 0 || exponent >= 2047) return factor->value * value;
  output.bits = ((uint64_t)(factor->sign ^ (uint32_t)(input.bits >> 63)) << 63) |
                ((uint64_t)exponent << 52) | (rounded & UINT64_C(0xfffffffffffff));
  return output.floating;
}
#endif
