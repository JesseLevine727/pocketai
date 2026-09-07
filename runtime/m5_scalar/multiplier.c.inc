uint32_t pa_m5_dynamic_multiplier(uint32_t maximum) {
  if (!maximum) return 0;
  /* N < 2^31. q*maximum <= N, so quotient, product and remainder all
   * fit uint32_t, for EVERY nonzero uint32_t denominator. */
  const uint32_t numerator = UINT32_C(127) << 24;
  uint32_t quotient = numerator / maximum;
#ifdef __riscv
  /* GCC otherwise folds N-q*d back to REMU, running the iterative divider
   * twice. This zero-instruction value barrier keeps the fast MUL remainder. */
  __asm__ volatile("" : "+r"(quotient));
#endif
  uint32_t remainder = numerator - quotient * maximum;
  return quotient + (remainder > maximum - remainder ||
                    (remainder == maximum - remainder && (quotient & 1u)));
}
