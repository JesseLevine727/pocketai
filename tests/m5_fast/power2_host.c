#include <stdint.h>
#include "../../runtime/m5_fast/exact_power2.c.inc"
double pa_fast_test_scale(double value, int exponent) {
  return pa_fast_scale_power2(value, exponent);
}
double pa_fast_reference_scale(double value, int exponent) {
  union { uint64_t bits; double value; } factor = {.bits = (uint64_t)(exponent+1023) << 52};
  return value * factor.value;
}
