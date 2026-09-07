/* Exact magnitude reduction for projection range selection. The model uses
 * binary64; do not approximate its ordered product or nonzero-bias addition.
 * Both zero signs can skip addition because only the magnitude maximum is
 * observed here. Ignore NaNs exactly as original `logical > maximum` did. */
static uint64_t pa_iter_magnitude_bits(double value) {
  union { double floating; uint64_t bits; } data = {.floating = value};
  return data.bits & UINT64_C(0x7fffffffffffffff);
}
static double pa_iter_range_term(int32_t sum, double scale, double bias,
                                 const int16_t *residual, uint32_t exponent) {
  double logical = (double)sum * scale;
  if (pa_iter_magnitude_bits(bias)) logical += bias;
  if (residual) {
    /* int16 -> binary64, times 2^e / 256 is exact for every allowed e. */
    double old = pa_fast_scale_power2((double)*residual, (int)exponent-8);
    union { uint64_t bits; double floating; } magnitude = {
        .bits = pa_iter_magnitude_bits(logical)}, old_magnitude = {
        .bits = pa_iter_magnitude_bits(old)};
    logical = magnitude.floating + old_magnitude.floating;
  }
  return logical;
}
static uint64_t pa_iter_range_max(uint64_t maximum, double logical) {
  uint64_t magnitude = pa_iter_magnitude_bits(logical);
  return magnitude <= UINT64_C(0x7ff0000000000000) && magnitude > maximum ? magnitude : maximum;
}
