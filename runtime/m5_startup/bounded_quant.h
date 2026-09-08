#ifndef PA_M5_STARTUP_BOUNDED_QUANT_H
#define PA_M5_STARTUP_BOUNDED_QUANT_H
#include <stdint.h>
/* Contract: abs(value)<=maximum<=32768 and
 * multiplier=RNE((127<<24)/maximum), or both maximum and multiplier are zero.
 * Then abs(value)*multiplier <= (127<<24)+16384 < 2^31. The complete product
 * and rounding addition fit uint32: no high bits or precision are discarded.
 * Cold V scanning and each exact maximum update establish this contract. */
static inline int8_t pa_startup_bounded_quant(int32_t value, uint32_t multiplier) {
  uint32_t absolute = value < 0 ? 0u-(uint32_t)value : (uint32_t)value;
  uint32_t product = absolute*multiplier;
  uint32_t rounded = (product+UINT32_C(0x7fffff)+((product>>24)&1u))>>24;
  return (int8_t)(value < 0 ? -(int32_t)rounded : (int32_t)rounded);
}
/* Same proven domain, with signed RNE represented in two's-complement bits.
 * The magnitude bound above also proves signed product plus rounding stays
 * in int32. Arithmetic right shift is provided by both qualified compilers.
 * This avoids separate negative lanes, without a truncated full product. */
static inline int8_t pa_startup_signed_quant(int32_t value, uint32_t multiplier) {
  uint32_t product = (uint32_t)value*multiplier;
  product += UINT32_C(0x7fffff)+((product>>24)&1u);
  return (int8_t)((int32_t)product >> 24);
}
#endif
