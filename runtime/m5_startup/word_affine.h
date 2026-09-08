#ifndef PA_M5_STARTUP_WORD_AFFINE_H
#define PA_M5_STARTUP_WORD_AFFINE_H
#include <stdint.h>
/* Exact magnitude product and RNE. Accept only a signed result strictly within
 * +/-2^29; the caller retains its original wider fallback otherwise. Using
 * explicit words avoids generic RV32 64-bit shifts/sign reconstruction. */
static inline int startup_word_affine(int32_t value, uint32_t magnitude,
    uint32_t multiplier, uint32_t shift, int32_t *output) {
  if (!shift || shift > 31) return 0;
  uint64_t product = (uint64_t)magnitude*multiplier;
  uint32_t low = (uint32_t)product, high = (uint32_t)(product>>32);
  if (high>>shift) return 0;
  uint32_t q = (low>>shift)|(high<<(32-shift));
  uint32_t remainder = low&((UINT32_C(1)<<shift)-1), half = UINT32_C(1)<<(shift-1);
  if (q >= (UINT32_C(1)<<29)) return 0;
  q += remainder > half || (remainder == half && (q&1u));
  if (q >= (UINT32_C(1)<<29)) return 0;
  *output = value < 0 ? -(int32_t)q : (int32_t)q;
  return 1;
}
#endif
