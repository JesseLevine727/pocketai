/* Exact binary64 scaling on the normal-to-normal domain. The original
 * arithmetic remains the fallback for subnormals, signed zero and specials. */
static double pa_fast_scale_power2(double value, int exponent) {
  union { double floating; uint64_t bits; } data = {.floating = value};
  uint32_t encoded = (uint32_t)((data.bits >> 52) & 2047u);
  int shifted = (int)encoded + exponent;
  if (encoded && encoded < 2047 && shifted > 0 && shifted < 2047) {
    data.bits = (data.bits & UINT64_C(0x800fffffffffffff)) | (uint64_t)shifted << 52;
    return data.floating;
  }
  union { double floating; uint64_t bits; } factor = {
      .bits = (uint64_t)(exponent + 1023) << 52};
  return value * factor.floating;
}
